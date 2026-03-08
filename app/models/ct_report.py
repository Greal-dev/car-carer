from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Integer, Date, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class CTReport(Base):
    __tablename__ = "ct_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date)
    mileage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    center_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    result: Mapped[str] = mapped_column(String(30))  # favorable, defavorable, contre_visite
    next_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    vehicle = relationship("Vehicle", back_populates="ct_reports")
    document = relationship("Document", back_populates="ct_report")
    defects = relationship("CTDefect", back_populates="ct_report", cascade="all, delete-orphan")


class CTDefect(Base):
    __tablename__ = "ct_defects"

    id: Mapped[int] = mapped_column(primary_key=True)
    ct_report_id: Mapped[int] = mapped_column(ForeignKey("ct_reports.id"))
    code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    description: Mapped[str] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(20))  # mineur, majeur, critique, a_surveiller
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    ct_report = relationship("CTReport", back_populates="defects")
