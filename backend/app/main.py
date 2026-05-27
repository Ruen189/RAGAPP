import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import select

from app.api import admin, auth, chat, knowledge, profile
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.logging import configure_logging
from app.models import ModelCapability, User, UserRole
from app.security import hash_password


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings = get_settings()
    async with SessionLocal() as session:
        query = await session.execute(select(User).where(User.login == settings.admin_login))
        admin_user = query.scalar_one_or_none()
        if not admin_user:
            session.add(
                User(
                    id=uuid.uuid4(),
                    login=settings.admin_login,
                    password_hash=hash_password(settings.admin_pass),
                    role=UserRole.admin,
                )
            )
        model_row = await session.execute(select(ModelCapability).where(ModelCapability.model_hf == settings.model_hf))
        model_capability = model_row.scalar_one_or_none()
        if not model_capability:
            session.add(ModelCapability(model_hf=settings.model_hf, multimodal=settings.model_multimodal))
        else:
            model_capability.multimodal = settings.model_multimodal
        await session.commit()
    yield


app = FastAPI(title="Проектный менеджер", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.redis = Redis.from_url(get_settings().redis_url, decode_responses=True)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])


@app.get("/health")
async def health():
    return {"status": "ok"}
