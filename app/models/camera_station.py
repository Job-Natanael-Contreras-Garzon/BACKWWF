import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Any
from sqlalchemy import String, Integer, Numeric, Date, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import BaseEntity


class CameraStation(BaseEntity):
    """
    Modelo ORM para Estaciones de Cámaras Trampa.
    Hereda de BaseEntity (id, created_at, updated_at, is_deleted, deleted_at).
    """
    __tablename__ = "camera_stations"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'maintenance', 'retrieved')", name="check_station_status"),
    )

    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    anon_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("anon_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    station_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    location_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6), nullable=True)
    altitude_meters: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    camera_brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    camera_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    trigger_speed_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ir_range_meters: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    deployment_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    retrieval_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default="active")
    meta_data: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    # Estadísticas de telemetría y videos
    dias_activos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    n_clips: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seg_grabados: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    horas_grabadas: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    user = relationship("User", lazy="selectin")
    project_stations = relationship(
        "ProjectStation",
        back_populates="station",
        cascade="all, delete-orphan",
        lazy="selectin",
        overlaps="camera_stations,projects",
    )
    projects: Mapped[List["Project"]] = relationship(
        "Project",
        secondary="project_stations",
        back_populates="camera_stations",
        lazy="selectin",
        overlaps="project_stations,station,project",
    )
    media_files = relationship("MediaFile", back_populates="station", cascade="all, delete-orphan", lazy="selectin")
    videos = relationship("Video", back_populates="station", cascade="all, delete-orphan", lazy="raise")
    species = relationship("Species", back_populates="station", cascade="all, delete-orphan", lazy="raise")
