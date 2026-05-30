from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from uuid import UUID
from datetime import datetime
from decimal import Decimal

class SpeciesBase(BaseModel):
    common_name: str
    scientific_name: Optional[str] = None
    confidence_score: Optional[Decimal] = None
    detection_timestamp: Optional[datetime] = None
    ai_raw_response: Optional[dict[str, Any]] = None
    is_verified: Optional[bool] = None

class SpeciesCreate(SpeciesBase):
    station_id: UUID
    video_id: Optional[UUID] = None

class SpeciesUpdate(BaseModel):
    common_name: Optional[str] = None
    scientific_name: Optional[str] = None

class SpeciesRead(SpeciesBase):
    id: UUID
    station_id: UUID
    video_id: Optional[UUID]
    created_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)
