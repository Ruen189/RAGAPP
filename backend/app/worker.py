import asyncio
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Conversation, GenerationJob, JobStatus, Message, MessageRole
from app.services.context_service import ContextService
from app.services.llama_client import LlamaClient, LlamaServerUnavailable
from app.services.pipeline_logger import write_pipeline_log
from app.services.prompt_templates import RETRIEVAL_AWARE_PROMPT, build_system_prompt
from app.services.queue_service import QueueService
from app.services.rag_service import RagService
from app.services.token_estimator import TokenEstimator


logger = logging.getLogger("worker")


ROLE_PREFIX_RE = re.compile(r"^\s*(assistant|ассистент)\s*:\s*", re.IGNORECASE)
NEXT_TURN_RE = re.compile(r"\n\s*(user|пользователь|USER)\s*:\s*", re.IGNORECASE)
DEFAULT_CONVERSATION_TITLE = "Новый диалог"
THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
THINK_OPEN_RE = re.compile(r"<think\b[^>]*>", re.IGNORECASE)
THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)
REASONING_MARKERS_RE = re.compile(
    r"^\s*(thinking process|analy[sz]e the request|drafting the response|review against constraints|final check)\s*:",
    re.IGNORECASE,
)


def render_history(messages: list[Message]) -> str:
    rendered = []
    for idx, message in enumerate(messages, start=1):
        role = "Пользователь" if message.role == MessageRole.user else "Ассистент"
        rendered.append(f"<message {idx} role=\"{role}\">\n{message.content}\n</message>")
    return "\n\n".join(rendered)


def clean_assistant_answer(answer: str) -> str:
    cleaned = THINK_BLOCK_RE.sub("", answer)
    open_match = THINK_OPEN_RE.search(cleaned)
    if open_match:
        # If the model was cut off before </think>, discard everything after the opening tag.
        cleaned = cleaned[: open_match.start()]
    cleaned = THINK_CLOSE_RE.sub("", cleaned)
    cleaned = ROLE_PREFIX_RE.sub("", cleaned.strip())
    if REASONING_MARKERS_RE.search(cleaned):
        return ""
    next_turn_match = NEXT_TURN_RE.search(cleaned)
    if next_turn_match:
        cleaned = cleaned[: next_turn_match.start()].rstrip()
    return cleaned


def build_llama_image_data(attachments: list[dict]) -> tuple[list[dict], str]:
    image_data: list[dict] = []
    prompt_refs: list[str] = []
    for index, attachment in enumerate(attachments, start=1):
        if attachment.get("kind") != "image":
            continue
        value = str(attachment.get("value") or "")
        if not value:
            continue
        content_type = attachment.get("content_type", "image/png")
        raw_base64 = value.split(",", 1)[1] if "," in value else value
        image_url = value if value.startswith("data:") else f"data:{content_type};base64,{raw_base64}"
        image_id = index
        image_data.append({"id": image_id, "data": raw_base64, "url": image_url})
        prompt_refs.append(
            f"image/{index} ({content_type})"
        )
    if not prompt_refs:
        return [], "-"
    return image_data, "\n".join(prompt_refs)


def generate_conversation_title(message: Message) -> str:
    if message.attachments and not message.content.strip():
        return "Изображение"

    text = re.sub(r"\s+", " ", message.content.strip())
    text = re.sub(
        r"^(расскажи|объясни|поясни|что такое|что значит|как работает|напиши|помоги|сделай|покажи)\s+(про\s+|о\s+)?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.strip(" ?!.,:;\"'«»")
    if not text:
        return "Новый вопрос"

    words = text.split()
    title = " ".join(words[:6])
    return title[:60].strip(" ?!.,:;\"'«»") or "Новый вопрос"


class ThinkBlockFilter:
    def __init__(self) -> None:
        self.in_think = False
        self.buffer = ""

    def feed(self, token: str) -> str:
        self.buffer += token
        visible_parts: list[str] = []

        while self.buffer:
            if self.in_think:
                close_match = THINK_CLOSE_RE.search(self.buffer)
                if close_match is None:
                    # Keep only a small tail in case the closing tag is split across tokens.
                    self.buffer = self.buffer[-16:]
                    return "".join(visible_parts)
                self.buffer = self.buffer[close_match.end() :]
                self.in_think = False
                continue

            open_match = THINK_OPEN_RE.search(self.buffer)
            if open_match is None:
                # Do not flush a possible partial "<think" suffix yet.
                lower_buffer = self.buffer.lower()
                partial_index = max(lower_buffer.rfind("<"), lower_buffer.rfind("<think"))
                if partial_index >= 0 and lower_buffer[partial_index:].startswith("<think"[: len(lower_buffer) - partial_index]):
                    visible_parts.append(self.buffer[:partial_index])
                    self.buffer = self.buffer[partial_index:]
                else:
                    visible_parts.append(self.buffer)
                    self.buffer = ""
                return "".join(visible_parts)

            visible_parts.append(self.buffer[: open_match.start()])
            self.buffer = self.buffer[open_match.end() :]
            self.in_think = True

        return "".join(visible_parts)

    def flush(self) -> str:
        if self.in_think:
            self.buffer = ""
            return ""
        visible = self.buffer
        self.buffer = ""
        return visible


EMPTY_GENERATION_FALLBACK = (
    "Не удалось сгенерировать ответ: модель вернула пустой результат. "
    "Попробуйте повторить запрос или переформулировать вопрос."
)


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
            pipeline_started = time.perf_counter()
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
            retrieval_latency_ms = 0
            if use_rag:
                position, size = await queue.get_scope_queue_metrics(db, job.user_id, job.conversation_id, job)
                await queue.publish_status(str(job.id), JobStatus.retrieving, position, size)
                retrieval_started = time.perf_counter()
                retrieved = rag.retrieve(request_message.content, top_k=5)
                retrieval_latency_ms = int((time.perf_counter() - retrieval_started) * 1000)

            system_prompt = build_system_prompt(use_retrieval=bool(retrieved), multimodal=settings.model_multimodal)
            context_window = await context_service.build_context_window(db, str(job.conversation_id), system_prompt=system_prompt)
            if retrieved:
                rag_instruction = RETRIEVAL_AWARE_PROMPT.strip()
            else:
                rag_instruction = "Режим: обычный ответ без factual grounding из базы знаний."
            rag_part = "\n\n".join(
                f"[doc={chunk.document_id} chunk={chunk.chunk_id} score={chunk.score:.3f}] {chunk.text}" for chunk in retrieved
            )
            history_messages = [message for message in context_window.selected_messages if message.id != request_message.id]
            messages_part = render_history(history_messages)
            llama_image_data, image_prompt_part = build_llama_image_data(request_message.attachments or [])
            image_instruction = ""
            if llama_image_data:
                image_instruction = (
                    "\nК текущему сообщению пользователя прикреплены изображения. "
                    "Они переданы в multimodal API как image_url части сообщения, а не только текстом. "
                    "Проанализируй их только если это нужно для ответа. "
                    "Если визуальной информации недостаточно, честно попроси уточнение.\n"
                )
            prompt = (
                f"{context_window.system_prompt}\n\n"
                f"{rag_instruction}\n\n"
                f"SUMMARY:\n{context_window.summary_text or '-'}\n\n"
                f"RAG_CONTEXT:\n{rag_part or '-'}\n\n"
                f"HISTORY:\n{messages_part or '-'}\n\n"
                f"ATTACHED_IMAGES:\n{image_prompt_part}\n"
                f"{image_instruction}\n"
                f"Текущий вопрос пользователя:\n{request_message.content}\n\n"
                "Ответь только финальным сообщением ассистента. Не добавляй имена ролей и не продолжай диалог за пользователя. "
                "Не выводи <think>, Thinking Process, анализ запроса или черновики. /no_think\n"
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
            first_token_at: float | None = None
            streamed_token_estimate = 0
            think_filter = ThinkBlockFilter()

            async def publish_model_loading(attempt: int, max_attempts: int, _: str) -> None:
                await queue.publish_status(
                    str(job.id),
                    JobStatus.thinking,
                    position,
                    size,
                    payload={
                        "thinking_notice": (
                            f"Модель загружается или еще не готова, подождите... "
                            f"попытка {attempt}/{max_attempts}"
                        )
                    },
                )

            async for token in llama.generate_stream(
                prompt,
                image_data=llama_image_data,
                on_retry=publish_model_loading,
            ):
                if token:
                    visible_token = think_filter.feed(token)
                    if visible_token:
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        chunks.append(visible_token)
                        streamed_token_estimate += TokenEstimator.count(visible_token)
                        await queue.publish_status(
                            str(job.id),
                            JobStatus.responding,
                            position,
                            size,
                            payload={"delta": visible_token},
                        )

            tail = think_filter.flush()
            if tail:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                chunks.append(tail)
                streamed_token_estimate += TokenEstimator.count(tail)
                await queue.publish_status(str(job.id), JobStatus.responding, position, size, payload={"delta": tail})

            generation_finished = time.perf_counter()
            latency_ms = int((generation_finished - started) * 1000)
            time_to_first_token_ms = int((first_token_at - started) * 1000) if first_token_at is not None else None
            generation_after_first_token_ms = (
                int((generation_finished - first_token_at) * 1000) if first_token_at is not None else 0
            )
            answer = clean_assistant_answer("".join(chunks))
            empty_generation_retry_used = False
            if not answer:
                empty_generation_retry_used = True
                retry_started = time.perf_counter()
                retry_prompt = (
                    f"{prompt}\n\n"
                    "Предыдущая генерация вернула пустой ответ. "
                    "Сгенерируй минимум одно содержательное предложение по текущему вопросу. "
                    "Не добавляй префиксы ролей. Не выводи <think> или Thinking Process. /no_think"
                )
                retry_answer = await llama.generate(retry_prompt, image_data=llama_image_data)
                retry_latency_ms = int((time.perf_counter() - retry_started) * 1000)
                answer = clean_assistant_answer(retry_answer) or EMPTY_GENERATION_FALLBACK
                latency_ms += retry_latency_ms
                generation_finished = time.perf_counter()

            completion_tokens = TokenEstimator.count(answer)
            tokens_per_second_after_first = (
                round(streamed_token_estimate / (generation_after_first_token_ms / 1000), 3)
                if generation_after_first_token_ms > 0
                else 0.0
            )
            total_request_latency_ms = int((generation_finished - pipeline_started) * 1000)
            total_from_received_ms = int(
                (datetime.now(timezone.utc) - request_message.created_at.replace(tzinfo=timezone.utc)).total_seconds() * 1000
            )
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
            auto_title = None
            if conversation.title == DEFAULT_CONVERSATION_TITLE:
                user_messages = await db.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation.id, Message.role == MessageRole.user)
                    .order_by(Message.created_at.asc())
                    .limit(2)
                )
                if len(list(user_messages.scalars().all())) == 1:
                    auto_title = generate_conversation_title(request_message)
                    conversation.title = auto_title
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
                    "latency_ms": retrieval_latency_ms,
                    "results": [
                        {"document_id": c.document_id, "chunk_id": c.chunk_id, "score": c.score} for c in retrieved
                    ],
                },
                "llm_call": {
                    "model": settings.model_hf,
                    "prompt": prompt,
                    "response": answer,
                    "prompt_tokens": TokenEstimator.count(prompt),
                    "completion_tokens": completion_tokens,
                    "latency_ms": latency_ms,
                    "time_to_first_token_ms": time_to_first_token_ms,
                    "generation_after_first_token_ms": generation_after_first_token_ms,
                    "tokens_per_second_after_first": tokens_per_second_after_first,
                    "empty_generation_retry_used": empty_generation_retry_used,
                    "image_count": len(llama_image_data),
                },
                "performance": {
                    "retrieval_latency_ms": retrieval_latency_ms,
                    "time_to_first_token_ms": time_to_first_token_ms,
                    "generation_latency_ms": latency_ms,
                    "generation_after_first_token_ms": generation_after_first_token_ms,
                    "tokens_per_second_after_first": tokens_per_second_after_first,
                    "total_pipeline_latency_ms": total_request_latency_ms,
                    "total_from_question_received_ms": total_from_received_ms,
                    "empty_generation_retry_used": empty_generation_retry_used,
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
                    "conversation_title": conversation.title,
                    "conversation_title_auto_generated": bool(auto_title),
                },
            )
        except LlamaServerUnavailable as exc:
            logger.warning("llama_server_unavailable: %s", exc)
            job.status = JobStatus.error
            job.error_message = str(exc)
            await db.commit()
            await queue.publish_status(str(job.id), JobStatus.error, 0, 0, payload={"error": str(exc)})
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
