import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import String, Numeric, ForeignKey, CheckConstraint, Boolean, func, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from app.models.base import Base

class Species(Base):
    __tablename__ = "species"
    __table_args__ = (CheckConstraint("confidence_score >= 0 AND confidence_score <= 1", name="check_confidence_score"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("camera_stations.id", ondelete="CASCADE"), nullable=False)
    video_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"))
    common_name: Mapped[str] = mapped_column(String(100), nullable=False)
    scientific_name: Mapped[Optional[str]] = mapped_column(String(150))
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    detection_timestamp: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    url_img: Mapped[Optional[str]] = mapped_column(String(500))
    
    # NUEVO CAMPO: Para la verificación manual
    is_verified: Mapped[Optional[bool]] = mapped_column(Boolean, default=None)
    
    created_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    station: Mapped["CameraStation"] = relationship(back_populates="species", lazy="raise")
    video: Mapped[Optional["Video"]] = relationship(back_populates="species_list", lazy="raise")
    individuals: Mapped[List["Individual"]] = relationship(back_populates="species", lazy="raise")
