from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(20))  # invoice, ct_report, quote
    file_path: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(50))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string

    vehicle = relationship("Vehicle", back_populates="documents")
    maintenance_event = relationship("MaintenanceEvent", back_populates="document", uselist=False)
    ct_report = relationship("CTReport", back_populates="document", uselist=False)
