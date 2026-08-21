from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from app.core.enums import CameraStationStatus


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
    status: Optional[CameraStationStatus] = CameraStationStatus.ACTIVE
    meta_data: Optional[Dict[str, Any]] = None


class CameraStationCreate(CameraStationBase):
    project_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    anon_session_id: Optional[UUID] = None


class CameraStationUpdate(BaseModel):
    station_code: Optional[str] = None
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
    status: Optional[CameraStationStatus] = None
    meta_data: Optional[Dict[str, Any]] = None


class CameraStationRead(CameraStationBase):
    id: UUID
    project_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    anon_session_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    dias_activos: Optional[int] = None
    n_clips: Optional[int] = None
    seg_grabados: Optional[int] = None
    horas_grabadas: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class StationSummaryResponse(BaseModel):
    station_id: UUID
    distinct_species_count: int
    total_detections_count: int
    frequency_by_species: List[Dict[str, Any]] = []
    frequency_by_family: List[Dict[str, Any]] = []
    frequency_by_genus: List[Dict[str, Any]] = []
