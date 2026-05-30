from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.schemas.camera_station import CameraStationRead

class ProjectBase(BaseModel):
    title: str
    description: Optional[str] = None
    objectives: Optional[str] = None
    expected_results: Optional[str] = None
    status: Optional[str] = 'public'

class ProjectCreate(ProjectBase):
    user_id: UUID

class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None

class ProjectRead(ProjectBase):
    id: UUID
    user_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    camera_stations: List[CameraStationRead] = []
    model_config = ConfigDict(from_attributes=True)
