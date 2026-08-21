import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import String, Numeric, ForeignKey, CheckConstraint, Boolean, func, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from app.models.base import Base


class Species(Base):
    """
    Modelo ORM para Detecciones Taxonómicas de Especies en Cámaras Trampa.
    Incluye jerarquía taxonómica completa (family, genus, scientific_name, common_name).
    """
    __tablename__ = "species"
    __table_args__ = (
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 1", name="check_confidence_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("camera_stations.id", ondelete="CASCADE"), nullable=False, index=True)
    media_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True, index=True)
    video_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"), nullable=True)
    
    # Jerarquía Taxonómica
    family: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    genus: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    scientific_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, index=True)
    common_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    detection_timestamp: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    url_img: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_verified: Mapped[Optional[bool]] = mapped_column(Boolean, default=None, nullable=True)
    
    # Auditoría y Soft Delete
    created_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    station: Mapped["CameraStation"] = relationship(back_populates="species", lazy="raise")
    media_file: Mapped[Optional["MediaFile"]] = relationship(back_populates="species_list", lazy="selectin")
    video: Mapped[Optional["Video"]] = relationship(back_populates="species_list", lazy="raise")
    individuals: Mapped[List["Individual"]] = relationship(back_populates="species", lazy="raise")
