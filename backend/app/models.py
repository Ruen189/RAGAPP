import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.timezone_util import now_gmt5
from app.types import GUID


class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"


class MessageRole(str, enum.Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class JobStatus(str, enum.Enum):
    queued = "queued"
    thinking = "thinking"
    retrieving = "retrieving"
    responding = "responding"
    done = "done"
    error = "error"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    login: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.user, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), default="-", nullable=False)
    university_group: Mapped[str] = mapped_column(String(120), default="-", nullable=False)
    phone: Mapped[str] = mapped_column(String(64), default="-", nullable=False)
    telegram: Mapped[str] = mapped_column(String(120), default="-", nullable=False)
    avatar_data_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="Новый диалог", nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("conversations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[list[dict]] = mapped_column(JSON, default=list)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    summarized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("conversations.id"), nullable=False)
    request_message_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("messages.id"), nullable=False)
    response_message_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("messages.id"), nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Index("ix_generation_jobs_scope_status", GenerationJob.user_id, GenerationJob.conversation_id, GenerationJob.status)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), default="upload", nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    checksum: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_extension: Mapped[str | None] = mapped_column(String(16), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    visible_to_users: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("knowledge_documents.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    qdrant_point_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ModelCapability(Base):
    __tablename__ = "model_capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_hf: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    multimodal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_gmt5)
