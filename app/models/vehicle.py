from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Integer, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100))  # "Ma Clio"
    brand: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    plate_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    vin: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    fuel_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    owner_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    initial_mileage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    purchase_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    photo_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner = relationship("User", back_populates="vehicles")
    documents = relationship("Document", back_populates="vehicle", cascade="all, delete-orphan")
    maintenance_events = relationship("MaintenanceEvent", back_populates="vehicle", cascade="all, delete-orphan")
    ct_reports = relationship("CTReport", back_populates="vehicle", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="vehicle", cascade="all, delete-orphan")
