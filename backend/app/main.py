import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import select

from app.api import admin, auth, chat, feedback, knowledge, profile
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.db_migrations import ensure_knowledge_document_columns
from app.logging import configure_logging
from app.models import ModelCapability, User, UserRole
from app.security import hash_password
from app.services.ingestion_service import IngestionService
from app.services.rag_service import RagService

SEED_DIR = Path(__file__).resolve().parents[1] / "knowledge_seed"


async def seed_bundled_knowledge() -> None:
    if not SEED_DIR.exists():
        return

    rag = RagService()
    ingestion = IngestionService(rag)
    async with SessionLocal() as session:
        for file_path in sorted(SEED_DIR.glob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in {".md", ".txt", ".docx", ".pdf"}:
                continue
            await ingestion.upload_file(
                db=session,
                file_name=file_path.name,
                file_bytes=file_path.read_bytes(),
                metadata_json={"domain": "project-management", "seed": True},
                visible_to_users=True,
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_knowledge_document_columns(conn)

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
    await seed_bundled_knowledge()
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
app.include_router(feedback.router, prefix="/api/feedback", tags=["feedback"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])


@app.get("/health")
async def health():
    return {"status": "ok"}
