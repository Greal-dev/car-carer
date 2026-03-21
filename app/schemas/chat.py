from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    vehicle_id: Optional[int] = None


class ChatResponse(BaseModel):
    message: str
    conversation_id: int


class ConversationOut(BaseModel):
    id: int
    vehicle_id: Optional[int]
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}
