from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatSession(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    case_id: UUID | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatSessionCreate(BaseModel):
    case_id: UUID | None = None


class ChatMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class ChatMessageResponse(BaseModel):
    session_id: UUID
    role: str
    content: str
    case_id: UUID | None = None
    case_status: str | None = None
