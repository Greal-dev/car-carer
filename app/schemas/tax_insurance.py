from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.enums import TaxInsuranceType, RenewalFrequency


class TaxInsuranceCreate(BaseModel):
    record_type: TaxInsuranceType
    name: str = Field(..., min_length=1, max_length=255)
    provider: Optional[str] = Field(None, max_length=255)
    date: date
    cost: float = Field(..., ge=0)
    next_renewal_date: Optional[date] = None
    renewal_frequency: Optional[RenewalFrequency] = None
    notes: Optional[str] = Field(None, max_length=2000)
    document_id: Optional[int] = None


class TaxInsuranceUpdate(BaseModel):
    record_type: Optional[TaxInsuranceType] = None
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    provider: Optional[str] = Field(None, max_length=255)
    date: Optional[date] = None
    cost: Optional[float] = Field(None, ge=0)
    next_renewal_date: Optional[date] = None
    renewal_frequency: Optional[RenewalFrequency] = None
    notes: Optional[str] = Field(None, max_length=2000)
    document_id: Optional[int] = None


class TaxInsuranceOut(BaseModel):
    id: int
    vehicle_id: int
    record_type: str
    name: str
    provider: Optional[str]
    date: date
    cost: float
    next_renewal_date: Optional[date]
    renewal_frequency: Optional[str]
    notes: Optional[str]
    document_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}
