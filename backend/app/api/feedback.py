from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import Feedback, User
from app.schemas import FeedbackCreateRequest
from app.timezone_util import now_gmt5

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: FeedbackCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    feedback = Feedback(user_id=user.id, content=payload.content, created_at=now_gmt5())
    db.add(feedback)
    await db.commit()
    return {"status": "ok"}
