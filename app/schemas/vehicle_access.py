from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.enums import VehicleRole


class VehicleAccessCreate(BaseModel):
    email: str = Field(..., max_length=255)  # invite by email
    role: VehicleRole


class VehicleAccessUpdate(BaseModel):
    role: VehicleRole


class VehicleAccessOut(BaseModel):
    id: int
    vehicle_id: int
    user_id: int
    user_email: Optional[str] = None
    role: str
    granted_by_user_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}
