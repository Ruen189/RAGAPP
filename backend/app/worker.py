import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Conversation, GenerationJob, JobStatus, Message, MessageRole
from app.services.context_service import ContextService
from app.services.llama_client import LlamaClient
from app.services.pipeline_logger import write_pipeline_log
from app.services.prompt_templates import RETRIEVAL_AWARE_PROMPT, build_system_prompt
from app.services.queue_service import QueueService
from app.services.rag_service import RagService
from app.services.token_estimator import TokenEstimator


logger = logging.getLogger("worker")


async def claim_next_job():
    async with SessionLocal() as db:
        result = await db.execute(
            select(GenerationJob)
            .where(GenerationJob.status == JobStatus.queued)
            .order_by(GenerationJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if not job:
            return None
        job.status = JobStatus.thinking
        await db.commit()
        await db.refresh(job)
        return job


async def process_job(redis_client: Redis, job_id: uuid.UUID) -> None:
    queue = QueueService(redis_client)
    rag = RagService()
    context_service = ContextService()
    llama = LlamaClient()
    settings = get_settings()

    async with SessionLocal() as db:
        job = await db.get(GenerationJob, job_id)
        if not job:
            return

        lock_key = f"lock:{job.user_id}:{job.conversation_id}"
        lock_acquired = await redis_client.set(lock_key, str(job.id), ex=600, nx=True)
        if not lock_acquired:
            job.status = JobStatus.queued
            await db.commit()
            return

        try:
            position, size = await queue.get_scope_queue_metrics(db, job.user_id, job.conversation_id, job)
            await queue.publish_status(str(job.id), JobStatus.thinking, position, size)

            request_message = await db.get(Message, job.request_message_id)
            conversation = await db.get(Conversation, job.conversation_id)
            if not request_message or not conversation:
                job.status = JobStatus.error
                job.error_message = "Missing message/conversation"
                await db.commit()
                return

            compression_info = await context_service.maybe_compress(db, conversation)
            use_rag = rag.should_use_rag(request_message.content)
            retrieved = []
            if use_rag:
                position, size = await queue.get_scope_queue_metrics(db, job.user_id, job.conversation_id, job)
                await queue.publish_status(str(job.id), JobStatus.retrieving, position, size)
                retrieved = rag.retrieve(request_message.content, top_k=5)

            system_prompt = build_system_prompt(use_retrieval=bool(retrieved), multimodal=settings.model_multimodal)
            context_window = await context_service.build_context_window(db, str(job.conversation_id), system_prompt=system_prompt)
            if retrieved:
                rag_instruction = RETRIEVAL_AWARE_PROMPT.strip()
            else:
                rag_instruction = "Режим: обычный ответ без factual grounding из базы знаний."
            rag_part = "\n\n".join(
                f"[doc={chunk.document_id} chunk={chunk.chunk_id} score={chunk.score:.3f}] {chunk.text}" for chunk in retrieved
            )
            messages_part = "\n".join(f"{m.role.value}: {m.content}" for m in context_window.selected_messages)
            prompt = (
                f"{context_window.system_prompt}\n\n"
                f"{rag_instruction}\n\n"
                f"SUMMARY:\n{context_window.summary_text or '-'}\n\n"
                f"RAG_CONTEXT:\n{rag_part or '-'}\n\n"
                f"HISTORY:\n{messages_part}\n\n"
                f"USER:\n{request_message.content}\n"
            )
            position, size = await queue.get_scope_queue_metrics(db, job.user_id, job.conversation_id, job)
            await queue.publish_status(
                str(job.id),
                JobStatus.responding,
                position,
                size,
                payload={"thinking_notice": "Рассуждаю, подождите..."},
            )

            chunks: list[str] = []
            started = time.perf_counter()
            async for token in llama.generate_stream(prompt):
                if token:
                    chunks.append(token)
                    await queue.publish_status(str(job.id), JobStatus.responding, position, size, payload={"delta": token})

            answer = "".join(chunks).strip()
            latency_ms = int((time.perf_counter() - started) * 1000)
            answer_message = Message(
                conversation_id=job.conversation_id,
                user_id=job.user_id,
                role=MessageRole.assistant,
                content=answer,
                attachments=[],
                token_count=TokenEstimator.count(answer),
            )
            db.add(answer_message)
            await db.flush()
            conversation.updated_at = datetime.utcnow()
            job.response_message_id = answer_message.id
            job.status = JobStatus.done
            await db.commit()

            payload = {
                "trace_id": job.trace_id,
                "user_id": str(job.user_id),
                "conversation_id": str(job.conversation_id),
                "message_id": str(job.request_message_id),
                "inbound": {
                    "channel": "web",
                    "text": request_message.content,
                    "received_at": request_message.created_at.replace(tzinfo=timezone.utc).isoformat(),
                    "attachments": request_message.attachments,
                },
                "context_window": {
                    "messages": [
                        {"id": str(m.id), "role": m.role.value, "tokens": m.token_count} for m in context_window.raw_messages
                    ],
                    "total_tokens": context_window.total_tokens,
                },
                "compression": {
                    **(compression_info or {"strategy": "summary+state", "input_chars": 0, "output_chars": 0}),
                    "summary_text": conversation.summary_text or "",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                "retrieval": {
                    "used": bool(retrieved),
                    "query": request_message.content,
                    "top_k": 5,
                    "results": [
                        {"document_id": c.document_id, "chunk_id": c.chunk_id, "score": c.score} for c in retrieved
                    ],
                },
                "llm_call": {
                    "model": settings.model_hf,
                    "prompt": prompt,
                    "response": answer,
                    "prompt_tokens": TokenEstimator.count(prompt),
                    "completion_tokens": TokenEstimator.count(answer),
                    "latency_ms": latency_ms,
                },
                "queue": {"position": position, "size": size},
            }
            await write_pipeline_log(
                db=db,
                trace_id=job.trace_id,
                user_id=job.user_id,
                conversation_id=job.conversation_id,
                message_id=job.request_message_id,
                payload=payload,
            )
            await queue.publish_status(
                str(job.id),
                JobStatus.done,
                0,
                0,
                payload={
                    "message": answer,
                    "retrieval_results": [
                        {"document_id": c.document_id, "chunk_id": c.chunk_id, "score": c.score} for c in retrieved
                    ],
                    "mode": "rag" if retrieved else "general",
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("job_failed")
            job.status = JobStatus.error
            job.error_message = str(exc)
            await db.commit()
            await queue.publish_status(str(job.id), JobStatus.error, 0, 0, payload={"error": str(exc)})
        finally:
            await redis_client.delete(lock_key)


async def recover_stuck_jobs() -> None:
    async with SessionLocal() as db:
        result = await db.execute(
            select(GenerationJob).where(GenerationJob.status.in_([JobStatus.thinking, JobStatus.retrieving, JobStatus.responding]))
        )
        for job in result.scalars().all():
            job.status = JobStatus.queued
        await db.commit()


async def worker_loop() -> None:
    settings = get_settings()
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    await recover_stuck_jobs()
    while True:
        job = await claim_next_job()
        if not job:
            await asyncio.sleep(0.5)
            continue
        await process_job(redis_client, job.id)


if __name__ == "__main__":
    asyncio.run(worker_loop())
