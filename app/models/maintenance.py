from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Date, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date)
    mileage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    garage_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    total_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(String(20), default="invoice")  # invoice, quote
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    vehicle = relationship("Vehicle", back_populates="maintenance_events")
    document = relationship("Document", back_populates="maintenance_event")
    items = relationship("MaintenanceItem", back_populates="event", cascade="all, delete-orphan")


class MaintenanceItem(Base):
    __tablename__ = "maintenance_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("maintenance_events.id"), index=True)
    description: Mapped[str] = mapped_column(String(500))
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    part_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    labor_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    event = relationship("MaintenanceEvent", back_populates="items")
