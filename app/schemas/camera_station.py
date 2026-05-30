from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal

class CameraStationBase(BaseModel):
    station_code: str
    location_name: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    altitude_meters: Optional[Decimal] = None
    camera_brand: Optional[str] = None
    camera_model: Optional[str] = None
    serial_number: Optional[str] = None
    trigger_speed_ms: Optional[int] = None
    ir_range_meters: Optional[int] = None
    deployment_date: Optional[date] = None
    retrieval_date: Optional[date] = None
    status: Optional[str] = 'active'
    meta_data: Optional[dict[str, Any]] = None

class CameraStationCreate(CameraStationBase):
    project_id: UUID

class CameraStationUpdate(BaseModel):
    station_code: Optional[str] = None
    status: Optional[str] = None

class CameraStationRead(CameraStationBase):
    id: UUID
    project_id: UUID
    created_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)
