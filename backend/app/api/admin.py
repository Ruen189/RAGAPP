from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_admin
from app.models import PipelineLog, User, UserRole
from app.schemas import MakeAdminRequest

router = APIRouter()


@router.post("/make-admin")
async def make_admin(payload: MakeAdminRequest, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    target = await db.get(User, payload.target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.role = UserRole.admin
    await db.commit()
    return {"status": "ok", "target_user_id": str(target.id), "new_role": target.role.value}


@router.get("/users")
async def list_users(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    query = await db.execute(select(User).order_by(User.created_at.asc()))
    rows = query.scalars().all()
    return [{"id": str(row.id), "login": row.login, "role": row.role.value, "created_at": row.created_at.isoformat()} for row in rows]


@router.get("/logs")
async def get_logs(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db), limit: int = 100):
    query = await db.execute(select(PipelineLog).order_by(PipelineLog.created_at.desc()).limit(limit))
    rows = query.scalars().all()
    return [
        {
            "trace_id": row.trace_id,
            "user_id": str(row.user_id),
            "conversation_id": str(row.conversation_id),
            "message_id": str(row.message_id),
            "payload": row.payload,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
