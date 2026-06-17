from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_admin
from app.models import Feedback, PipelineLog, User, UserRole
from app.schemas import ChangeRoleRequest, FeedbackOut, MakeAdminRequest, PaginatedPipelineLogsOut, PipelineLogOut
from app.timezone_util import as_gmt5_aware

router = APIRouter()


def _toggle_user_role(target: User) -> UserRole:
    target.role = UserRole.user if target.role == UserRole.admin else UserRole.admin
    return target.role


@router.post("/change-role")
async def change_role(
    payload: ChangeRoleRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(User, payload.target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    new_role = _toggle_user_role(target)
    await db.commit()
    return {"status": "ok", "target_user_id": str(target.id), "new_role": new_role.value}


@router.post("/make-admin")
async def make_admin(
    payload: MakeAdminRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Deprecated alias: toggles role (user <-> admin)."""
    return await change_role(ChangeRoleRequest(target_user_id=payload.target_user_id), _, db)


@router.get("/feedback", response_model=list[FeedbackOut])
async def list_feedback(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    query = await db.execute(
        select(Feedback, User.login)
        .join(User, User.id == Feedback.user_id)
        .order_by(Feedback.created_at.desc())
    )
    return [
        FeedbackOut(
            id=feedback.id,
            login=login,
            content=feedback.content,
            created_at=as_gmt5_aware(feedback.created_at),
        )
        for feedback, login in query.all()
    ]


@router.get("/users")
async def list_users(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    query = await db.execute(select(User).order_by(User.created_at.asc()))
    rows = query.scalars().all()
    return [{"id": str(row.id), "login": row.login, "role": row.role.value, "created_at": row.created_at.isoformat()} for row in rows]


@router.get("/logs", response_model=PaginatedPipelineLogsOut)
async def get_logs(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
) -> PaginatedPipelineLogsOut:
    total = await db.scalar(select(func.count()).select_from(PipelineLog)) or 0
    offset = (page - 1) * page_size
    query = await db.execute(
        select(PipelineLog).order_by(PipelineLog.created_at.desc()).offset(offset).limit(page_size)
    )
    rows = query.scalars().all()
    total_pages = (total + page_size - 1) // page_size if total else 0
    return PaginatedPipelineLogsOut(
        items=[
            PipelineLogOut(
                trace_id=row.trace_id,
                user_id=str(row.user_id),
                conversation_id=str(row.conversation_id),
                message_id=str(row.message_id),
                payload=row.payload,
                created_at=row.created_at.isoformat(),
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
