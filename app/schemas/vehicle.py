from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class VehicleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    brand: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    year: Optional[int] = Field(None, ge=1886, le=2030)
    plate_number: Optional[str] = Field(None, max_length=20)
    vin: Optional[str] = Field(None, max_length=17)
    fuel_type: Optional[str] = Field(None, max_length=50)
    initial_mileage: Optional[int] = Field(None, ge=0)
    purchase_date: Optional[date] = None


class VehicleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    brand: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    year: Optional[int] = Field(None, ge=1886, le=2030)
    plate_number: Optional[str] = Field(None, max_length=20)
    vin: Optional[str] = Field(None, max_length=17)
    fuel_type: Optional[str] = Field(None, max_length=50)
    initial_mileage: Optional[int] = Field(None, ge=0)
    purchase_date: Optional[date] = None


class VehicleOut(BaseModel):
    id: int
    name: str
    brand: Optional[str]
    model: Optional[str]
    year: Optional[int]
    plate_number: Optional[str]
    vin: Optional[str]
    fuel_type: Optional[str]
    initial_mileage: Optional[int]
    purchase_date: Optional[date]
    photo_path: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VehicleSummary(BaseModel):
    id: int
    name: str
    brand: Optional[str]
    model: Optional[str]
    year: Optional[int]
    plate_number: Optional[str]
    last_mileage: Optional[int]
    last_maintenance_date: Optional[date]
    total_spent: float
    document_count: int
    ct_count: int

    model_config = {"from_attributes": True}
