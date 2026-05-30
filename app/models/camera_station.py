import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Any
from sqlalchemy import String, Integer, Numeric, Date, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from app.models.base import Base

class CameraStation(Base):
    __tablename__ = "camera_stations"
    __table_args__ = (CheckConstraint("status IN ('active', 'maintenance', 'retrieved')", name="check_station_status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    station_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    location_name: Mapped[Optional[str]] = mapped_column(String(150))
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6))
    altitude_meters: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    camera_brand: Mapped[Optional[str]] = mapped_column(String(100))
    camera_model: Mapped[Optional[str]] = mapped_column(String(100))
    serial_number: Mapped[Optional[str]] = mapped_column(String(100))
    trigger_speed_ms: Mapped[Optional[int]] = mapped_column(Integer)
    ir_range_meters: Mapped[Optional[int]] = mapped_column(Integer)
    deployment_date: Mapped[Optional[datetime]] = mapped_column(Date)
    retrieval_date: Mapped[Optional[datetime]] = mapped_column(Date)
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default='active')
    meta_data: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB) 
    created_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="camera_stations", lazy="selectin")
    videos: Mapped[List["Video"]] = relationship(back_populates="station", cascade="all, delete-orphan", lazy="selectin")
    species: Mapped[List["Species"]] = relationship(back_populates="station", cascade="all, delete-orphan", lazy="selectin")
