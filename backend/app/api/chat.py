import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Conversation, GenerationJob, JobStatus, Message, MessageRole, ModelCapability, User
from app.schemas import ConversationCreate, ConversationOut, ConversationRename, EnqueueResponse, MessageCreate, MessageOut
from app.services.queue_service import QueueFullError, QueueService
from app.services.token_estimator import TokenEstimator

router = APIRouter()


@router.get("/capabilities")
async def get_capabilities(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    del user
    settings = get_settings()
    model_caps_row = await db.execute(select(ModelCapability).where(ModelCapability.model_hf == settings.model_hf))
    model_caps = model_caps_row.scalar_one_or_none()
    multimodal_enabled = settings.model_multimodal and (model_caps.multimodal if model_caps else settings.model_multimodal)
    return {
        "model_hf": settings.model_hf,
        "multimodal": multimodal_enabled,
        "max_queue_size": settings.max_queue_size,
    }


@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(payload: ConversationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    conv = Conversation(user_id=user.id, title=payload.title)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationOut(id=conv.id, title=conv.title, created_at=conv.created_at, updated_at=conv.updated_at)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = await db.execute(
        select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())
    )
    rows = query.scalars().all()
    return [ConversationOut(id=row.id, title=row.title, created_at=row.created_at, updated_at=row.updated_at) for row in rows]


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationRename,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.title = payload.title.strip()
    await db.commit()
    await db.refresh(conv)
    return ConversationOut(id=conv.id, title=conv.title, created_at=conv.created_at, updated_at=conv.updated_at)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(conversation_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    query = await db.execute(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc()))
    rows = query.scalars().all()
    return [
        MessageOut(
            id=row.id,
            role=row.role,
            content=row.content,
            attachments=row.attachments,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/conversations/{conversation_id}/messages", response_model=EnqueueResponse)
async def send_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    model_caps_row = await db.execute(select(ModelCapability).where(ModelCapability.model_hf == settings.model_hf))
    model_caps = model_caps_row.scalar_one_or_none()
    multimodal_enabled = settings.model_multimodal and (model_caps.multimodal if model_caps else settings.model_multimodal)
    if payload.attachments and not multimodal_enabled:
        raise HTTPException(status_code=400, detail="Простите, я понимаю только текст")

    message = Message(
        conversation_id=conversation_id,
        user_id=user.id,
        role=MessageRole.user,
        content=payload.content,
        attachments=[item.model_dump() for item in payload.attachments],
        token_count=TokenEstimator.count(payload.content),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))
    queue = QueueService(request.app.state.redis)
    try:
        job, position, size = await queue.enqueue(
            db=db,
            user_id=user.id,
            conversation_id=conversation_id,
            request_message_id=message.id,
            trace_id=trace_id,
        )
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail="Очередь для этого диалога заполнена") from exc

    return EnqueueResponse(job_id=job.id, status=job.status, queue_size=size, queue_position=position)


@router.get("/stream/{job_id}")
async def stream_job(job_id: uuid.UUID, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await db.get(GenerationJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    redis_client = request.app.state.redis

    async def event_stream() -> AsyncGenerator[str, None]:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"job:{job_id}")
        try:
            current_job = await db.get(GenerationJob, job_id)
            if current_job:
                response_text = None
                if current_job.response_message_id:
                    response_message = await db.get(Message, current_job.response_message_id)
                    response_text = response_message.content if response_message else None
                initial_payload = {
                    "job_id": str(current_job.id),
                    "status": current_job.status.value,
                    "queue_position": 0,
                    "queue_size": 0,
                    "payload": {
                        **({"error": current_job.error_message} if current_job.error_message else {}),
                        **({"message": response_text} if response_text else {}),
                    },
                }
                yield f"data: {json.dumps(initial_payload, ensure_ascii=False)}\n\n"
                if current_job.status in {JobStatus.done, JobStatus.error}:
                    return
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    continue
                payload = message["data"]
                data = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
                yield f"data: {data}\n\n"
        finally:
            await pubsub.unsubscribe(f"job:{job_id}")
            await pubsub.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/jobs/{job_id}")
async def get_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await db.get(GenerationJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "conversation_id": str(job.conversation_id),
        "request_message_id": str(job.request_message_id),
        "response_message_id": str(job.response_message_id) if job.response_message_id else None,
        "error": job.error_message,
        "trace_id": job.trace_id,
    }
