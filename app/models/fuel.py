"""Fuel entry model for consumption tracking."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Date, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class FuelEntry(Base):
    __tablename__ = "fuel_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    mileage: Mapped[int] = mapped_column(Integer)
    liters: Mapped[float] = mapped_column(Float)
    price_per_liter: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    station: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fuel_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    full_tank: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    vehicle = relationship("Vehicle", back_populates="fuel_entries")
