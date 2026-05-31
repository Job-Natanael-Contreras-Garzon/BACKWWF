from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

class SpeciesBase(BaseModel):
    common_name: str
    scientific_name: Optional[str] = None
    confidence_score: Optional[Decimal] = None
    detection_timestamp: Optional[datetime] = None
    url_img: Optional[str] = None
    is_verified: Optional[bool] = None

class SpeciesCreate(SpeciesBase):
    station_id: UUID
    video_id: Optional[UUID] = None

class SpeciesUpdate(BaseModel):
    common_name: Optional[str] = None
    scientific_name: Optional[str] = None

class SpeciesRead(SpeciesBase):
    id: int
    station_id: UUID
    video_id: Optional[UUID]
    created_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)

class SpeciesDataResponse(BaseModel):
    id_deteccion: int
    id_camara: str
    url_img: Optional[str]
    fecha_hora: Optional[datetime]
    fecha: Optional[str]
    hora: Optional[str]
    periodo_dia: Optional[str]
    especie: str
    duracion_clip_seg: Optional[int]
    latitud: Optional[float]
    longitud: Optional[float]
    temp_media: Optional[float]
    min_desde_anterior: Optional[float]
    dist_anterior_km: Optional[float]
    velocidad_kmh: Optional[float]
    periodo_weckel: Optional[float]
    evento_independiente: Optional[int]
    periodoweckel: Optional[str]
