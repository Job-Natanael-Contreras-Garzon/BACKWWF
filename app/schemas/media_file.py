from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from app.core.enums import MediaType


class MediaFileBase(BaseModel):
    station_id: UUID
    file_type: MediaType
    file_url: str
    original_filename: Optional[str] = None
    duration_seconds: Optional[int] = None
    file_size_mb: Optional[Decimal] = None
    capture_date: Optional[datetime] = None
    metadata_extra: Optional[Dict[str, Any]] = None


class MediaFileRead(MediaFileBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MediaUploadDetectionItem(BaseModel):
    id: Optional[int] = None
    common_name: str
    scientific_name: Optional[str] = None
    family: Optional[str] = None
    genus: Optional[str] = None
    confidence_score: Optional[float] = None
    url_img: Optional[str] = None


class MediaUploadResponseData(BaseModel):
    media_file_id: UUID
    station_id: UUID
    file_type: MediaType
    file_url: str
    file_size_mb: Optional[Decimal] = None
    detections_count: int
    detections: List[MediaUploadDetectionItem] = []
