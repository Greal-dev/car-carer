from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class VehicleCreate(BaseModel):
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate_number: Optional[str] = None
    vin: Optional[str] = None
    fuel_type: Optional[str] = None
    initial_mileage: Optional[int] = None
    purchase_date: Optional[date] = None


class VehicleUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate_number: Optional[str] = None
    vin: Optional[str] = None
    fuel_type: Optional[str] = None
    initial_mileage: Optional[int] = None
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


class FuelEntryCreate(BaseModel):
    date: date
    mileage: int
    liters: float
    price_per_liter: Optional[float] = None
    total_cost: Optional[float] = None
    station: Optional[str] = None
    fuel_type: Optional[str] = None
    full_tank: bool = True

    @field_validator("mileage")
    @classmethod
    def mileage_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Le kilometrage doit etre >= 0")
        return v

    @field_validator("liters")
    @classmethod
    def liters_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Le volume de carburant doit etre > 0")
        return v

    @field_validator("price_per_liter")
    @classmethod
    def price_per_liter_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("Le prix au litre doit etre > 0")
        return v


class FuelEntryOut(BaseModel):
    id: int
    date: date
    mileage: int
    liters: float
    price_per_liter: Optional[float]
    total_cost: Optional[float]
    station: Optional[str]
    fuel_type: Optional[str]
    full_tank: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WarrantyCreate(BaseModel):
    item_id: int
    description: str
    duration_months: Optional[int] = None
    max_km: Optional[int] = None
    start_date: date
    end_date: Optional[date] = None


class WarrantyOut(BaseModel):
    id: int
    item_id: int
    vehicle_id: int
    description: str
    duration_months: Optional[int]
    max_km: Optional[int]
    start_date: date
    end_date: Optional[date]
    created_at: datetime

    model_config = {"from_attributes": True}
