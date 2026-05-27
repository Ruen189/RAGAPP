import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import User, UserRole


auth_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(auth_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    settings = get_settings()
    try:
        payload = jwt.decode(token.credentials, settings.jwt_secret, algorithms=["HS256"])
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    query = await db.execute(select(User).where(User.id == user_id))
    user = query.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return current_user
