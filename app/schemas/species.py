from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal


class SpeciesBase(BaseModel):
    common_name: str
    scientific_name: Optional[str] = None
    family: Optional[str] = None
    genus: Optional[str] = None
    confidence_score: Optional[Decimal] = None
    detection_timestamp: Optional[datetime] = None
    url_img: Optional[str] = None
    is_verified: Optional[bool] = None


class SpeciesCreate(SpeciesBase):
    station_id: UUID
    media_file_id: Optional[UUID] = None
    video_id: Optional[UUID] = None


class SpeciesUpdate(BaseModel):
    common_name: Optional[str] = None
    scientific_name: Optional[str] = None
    family: Optional[str] = None
    genus: Optional[str] = None
    confidence_score: Optional[Decimal] = None
    is_verified: Optional[bool] = None


class SpeciesRead(SpeciesBase):
    id: int
    station_id: UUID
    media_file_id: Optional[UUID] = None
    video_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SpeciesDataResponse(BaseModel):
    id_deteccion: int
    id_camara: str
    url_img: Optional[str] = None
    fecha_hora: Optional[datetime] = None
    fecha: Optional[str] = None
    hora: Optional[str] = None
    periodo_dia: Optional[str] = None
    especie: str
    duracion_clip_seg: Optional[int] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    temp_media: Optional[float] = None
    min_desde_anterior: Optional[float] = None
    dist_anterior_km: Optional[float] = None
    velocidad_kmh: Optional[float] = None
    periodo_weckel: Optional[float] = None
    evento_independiente: Optional[int] = None
    periodoweckel: Optional[str] = None
