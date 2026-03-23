from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class FuelRecordCreate(BaseModel):
    date: date
    mileage: Optional[int] = Field(None, ge=0)
    liters: float = Field(..., gt=0)
    price_total: float = Field(..., ge=0)
    price_per_liter: Optional[float] = Field(None, ge=0)
    station_name: Optional[str] = Field(None, max_length=255)
    fuel_type: Optional[str] = Field(None, max_length=50)
    is_full_tank: bool = True
    notes: Optional[str] = Field(None, max_length=2000)
    document_id: Optional[int] = None


class FuelRecordUpdate(BaseModel):
    date: Optional[date] = None
    mileage: Optional[int] = Field(None, ge=0)
    liters: Optional[float] = Field(None, gt=0)
    price_total: Optional[float] = Field(None, ge=0)
    price_per_liter: Optional[float] = Field(None, ge=0)
    station_name: Optional[str] = Field(None, max_length=255)
    fuel_type: Optional[str] = Field(None, max_length=50)
    is_full_tank: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=2000)
    document_id: Optional[int] = None


class FuelRecordOut(BaseModel):
    id: int
    vehicle_id: int
    date: date
    mileage: Optional[int]
    liters: float
    price_total: float
    price_per_liter: Optional[float]
    station_name: Optional[str]
    fuel_type: Optional[str]
    is_full_tank: bool
    notes: Optional[str]
    document_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}
