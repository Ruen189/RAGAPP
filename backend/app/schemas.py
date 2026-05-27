import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models import JobStatus, MessageRole, UserRole


class LoginRequest(BaseModel):
    login: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    login: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)


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


class KnowledgeUploadRequest(BaseModel):
    title: str
    content: str
    source_uri: str | None = None
    metadata_json: dict = Field(default_factory=dict)


class KnowledgeDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    source_type: str
    source_uri: str | None
    created_at: datetime


class MakeAdminRequest(BaseModel):
    target_user_id: uuid.UUID
