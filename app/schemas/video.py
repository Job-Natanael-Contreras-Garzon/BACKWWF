from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from uuid import UUID
from datetime import datetime
from decimal import Decimal

class VideoBase(BaseModel):
    file_url: str
    original_filename: Optional[str] = None
    duration_seconds: Optional[int] = None
    file_size_mb: Optional[Decimal] = None
    # Añadimos los nuevos campos al esquema base
    capture_date: Optional[datetime] = None
    metadata_extra: Optional[dict[str, Any]] = None

class VideoCreate(VideoBase):
    station_id: UUID

class VideoUpdate(BaseModel):
    file_url: Optional[str] = None
    metadata_extra: Optional[dict[str, Any]] = None

class VideoRead(VideoBase):
    id: UUID
    station_id: UUID
    upload_date: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)
