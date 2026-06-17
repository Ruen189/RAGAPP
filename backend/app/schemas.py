import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models import JobStatus, MessageRole, UserRole

_PASSWORD_LETTER_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ]")
_PASSWORD_DIGIT_RE = re.compile(r"\d")


class LoginRequest(BaseModel):
    login: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    login: str = Field(min_length=3, max_length=100)
    password: str = Field(max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Пароль должен содержать не менее 8 символов")
        if not _PASSWORD_LETTER_RE.search(value):
            raise ValueError("Пароль должен содержать хотя бы одну букву")
        if not _PASSWORD_DIGIT_RE.search(value):
            raise ValueError("Пароль должен содержать хотя бы одну цифру")
        return value


class UserOut(BaseModel):
    id: uuid.UUID
    login: str
    role: UserRole


class ProfileOut(BaseModel):
    user_id: uuid.UUID
    login: str
    role: UserRole
    full_name: str
    university_group: str
    phone: str
    telegram: str
    avatar_data_url: str | None = None


class ProfileUpdate(BaseModel):
    full_name: str = Field(default="-", max_length=255)
    university_group: str = Field(default="-", max_length=120)
    phone: str = Field(default="-", max_length=64)
    telegram: str = Field(default="-", max_length=120)
    avatar_data_url: str | None = None


class ConversationCreate(BaseModel):
    title: str = "Новый диалог"


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class Attachment(BaseModel):
    kind: str
    content_type: str
    value: str


class MessageCreate(BaseModel):
    content: str
    attachments: list[Attachment] = Field(default_factory=list)


class MessageOut(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    attachments: list[dict]
    created_at: datetime


class EnqueueResponse(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    queue_size: int
    queue_position: int


class KnowledgeDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    file_name: str
    source_type: str
    created_at: datetime
    visible_to_users: bool


class ChangeRoleRequest(BaseModel):
    target_user_id: uuid.UUID


class MakeAdminRequest(ChangeRoleRequest):
    """Deprecated alias for backwards compatibility."""


class FeedbackCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Сообщение не может быть пустым")
        if len(trimmed) > 500:
            raise ValueError("Сообщение не должно превышать 500 символов")
        return trimmed


class FeedbackOut(BaseModel):
    id: uuid.UUID
    login: str
    content: str
    created_at: datetime


class PipelineLogOut(BaseModel):
    trace_id: str
    user_id: str
    conversation_id: str
    message_id: str
    payload: dict
    created_at: str


class PaginatedPipelineLogsOut(BaseModel):
    items: list[PipelineLogOut]
    total: int
    page: int
    page_size: int
    total_pages: int
