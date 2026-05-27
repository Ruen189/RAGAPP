import json
import uuid

from redis.asyncio import Redis
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import GenerationJob, JobStatus
from app.services.queue_policy import check_queue_capacity


class QueueFullError(Exception):
    pass


class QueueService:
    def __init__(self, redis_client: Redis) -> None:
        self.settings = get_settings()
        self.redis = redis_client

    async def enqueue(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        request_message_id: uuid.UUID,
        trace_id: str,
    ) -> tuple[GenerationJob, int, int]:
        query = await db.execute(
            select(func.count())
            .select_from(GenerationJob)
            .where(
                and_(
                    GenerationJob.user_id == user_id,
                    GenerationJob.conversation_id == conversation_id,
                    GenerationJob.status.in_([JobStatus.queued, JobStatus.thinking, JobStatus.retrieving, JobStatus.responding]),
                )
            )
        )
        active_size = query.scalar_one()
        allowed, queue_position = check_queue_capacity(active_size, self.settings.max_queue_size)
        if not allowed:
            raise QueueFullError("Queue limit reached")

        job = GenerationJob(
            user_id=user_id,
            conversation_id=conversation_id,
            request_message_id=request_message_id,
            status=JobStatus.queued,
            trace_id=trace_id,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        await self.publish_status(str(job.id), JobStatus.queued, queue_position, active_size + 1)
        return job, queue_position, active_size + 1

    async def get_scope_queue_metrics(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        job: GenerationJob,
    ) -> tuple[int, int]:
        active_jobs = await db.execute(
            select(GenerationJob)
            .where(
                and_(
                    GenerationJob.user_id == user_id,
                    GenerationJob.conversation_id == conversation_id,
                    GenerationJob.status.in_([JobStatus.queued, JobStatus.thinking, JobStatus.retrieving, JobStatus.responding]),
                )
            )
            .order_by(GenerationJob.created_at.asc())
        )
        jobs = list(active_jobs.scalars().all())
        queue_size = len(jobs)
        queue_position = next((idx + 1 for idx, item in enumerate(jobs) if item.id == job.id), 0)
        return queue_position, queue_size

    async def publish_status(self, job_id: str, status: JobStatus, position: int, size: int, payload: dict | None = None) -> None:
        message = {
            "job_id": job_id,
            "status": status.value,
            "queue_position": position,
            "queue_size": size,
            "payload": payload or {},
        }
        await self.redis.publish(f"job:{job_id}", json.dumps(message, ensure_ascii=False))
