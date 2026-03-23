from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel

from app.enums import WorkType


class MaintenanceItemOut(BaseModel):
    id: int
    description: str
    category: Optional[str]
    part_name: Optional[str]
    quantity: Optional[float]
    unit_price: Optional[float]
    labor_cost: Optional[float]
    total_price: Optional[float]

    model_config = {"from_attributes": True}


class MaintenanceEventOut(BaseModel):
    id: int
    vehicle_id: int
    document_id: Optional[int]
    date: date
    mileage: Optional[int]
    garage_name: Optional[str]
    total_cost: Optional[float]
    notes: Optional[str]
    event_type: str
    work_type: Optional[WorkType] = None
    created_at: datetime
    items: list[MaintenanceItemOut] = []

    model_config = {"from_attributes": True}
