from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.enums import TriggerMode


class ReminderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    trigger_mode: TriggerMode
    km_interval: Optional[int] = Field(None, gt=0)
    months_interval: Optional[int] = Field(None, gt=0)
    last_performed_km: Optional[int] = Field(None, ge=0)
    last_performed_date: Optional[date] = None
    is_recurring: bool = True
    active: bool = True


class ReminderUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    trigger_mode: Optional[TriggerMode] = None
    km_interval: Optional[int] = Field(None, gt=0)
    months_interval: Optional[int] = Field(None, gt=0)
    last_performed_km: Optional[int] = Field(None, ge=0)
    last_performed_date: Optional[date] = None
    is_recurring: Optional[bool] = None
    active: Optional[bool] = None


class ReminderOut(BaseModel):
    id: int
    vehicle_id: int
    title: str
    description: Optional[str]
    trigger_mode: str
    km_interval: Optional[int]
    months_interval: Optional[int]
    last_performed_km: Optional[int]
    last_performed_date: Optional[date]
    is_recurring: bool
    active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
