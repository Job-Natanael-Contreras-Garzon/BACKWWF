import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional
from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from app.models.base import BaseEntity


class MediaFile(BaseEntity):
    """
    Modelo ORM para Archivos Multimedia (Videos e Imágenes) capturados en Estaciones de Cámaras.
    Hereda de BaseEntity (id, created_at, updated_at, is_deleted, deleted_at).
    """
    __tablename__ = "media_files"

    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("camera_stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "video" | "image"
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size_mb: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    capture_date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    metadata_extra: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata_extra", JSONB, nullable=True)

    station = relationship("CameraStation", back_populates="media_files", lazy="selectin")
    species_list = relationship("Species", back_populates="media_file", cascade="all, delete-orphan", lazy="selectin")
