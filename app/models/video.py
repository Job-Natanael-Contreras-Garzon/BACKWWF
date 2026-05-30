import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Any
from sqlalchemy import String, Integer, Numeric, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB
from app.models.base import Base

class Video(Base):
    __tablename__ = "videos"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("camera_stations.id", ondelete="CASCADE"), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    file_size_mb: Mapped[Optional[Decimal]] = mapped_column(Numeric)
    
    # NUEVOS CAMPOS AÑADIDOS
    capture_date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    metadata_extra: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    
    upload_date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    station: Mapped["CameraStation"] = relationship(back_populates="videos", lazy="selectin")
    species_list: Mapped[List["Species"]] = relationship(back_populates="video", lazy="selectin")
