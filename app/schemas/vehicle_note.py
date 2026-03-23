from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class VehicleNoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    pinned: bool = False


class VehicleNoteUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1, max_length=5000)
    pinned: Optional[bool] = None


class VehicleNoteOut(BaseModel):
    id: int
    vehicle_id: int
    content: str
    pinned: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
