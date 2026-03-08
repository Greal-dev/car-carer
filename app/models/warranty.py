"""Warranty tracking model for maintenance items."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Integer, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Warranty(Base):
    __tablename__ = "warranties"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("maintenance_items.id", ondelete="CASCADE"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(String(200))
    duration_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_km: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    item = relationship("MaintenanceItem", back_populates="warranties")
    vehicle = relationship("Vehicle", back_populates="warranties")
