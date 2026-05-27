import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PipelineLog


logger = logging.getLogger("pipeline")


async def write_pipeline_log(
    db: AsyncSession,
    trace_id: str,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: dict,
) -> None:
    row = PipelineLog(
        trace_id=trace_id,
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        payload=payload,
    )
    db.add(row)
    await db.commit()
    logger.info(
        "pipeline_event",
        extra={
            "extra_payload": {
                "trace_id": trace_id,
                "user_id": str(user_id),
                "conversation_id": str(conversation_id),
                "message_id": str(message_id),
                "created_at": datetime.now(timezone.utc).isoformat(),
                **payload,
            }
        },
    )
