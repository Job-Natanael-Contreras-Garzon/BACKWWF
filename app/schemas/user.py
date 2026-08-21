from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from app.core.enums import CameraStationStatus, ProjectStatus, UserGender


class UserBase(BaseModel):
    full_name: str
    email: str
    institucion: Optional[str] = None
    sexo: Optional[UserGender] = None


class UserCreate(UserBase):
    password: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    institucion: Optional[str] = None
    sexo: Optional[UserGender] = None
    is_active: Optional[bool] = None


class UserRead(UserBase):
    id: UUID
    is_active: bool = True
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ClaimRequest(BaseModel):
    anon_session_id: UUID


class ClaimResponseData(BaseModel):
    claimed_projects_count: int
    claimed_stations_count: int
    anon_session_id: str
    claimed_by_user_id: str


class ProjectSummaryItem(BaseModel):
    id: UUID
    title: str
    status: Optional[ProjectStatus] = ProjectStatus.PUBLIC
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class StationSummaryItem(BaseModel):
    id: UUID
    station_code: str
    location_name: Optional[str] = None
    status: Optional[CameraStationStatus] = CameraStationStatus.ACTIVE
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class UserHistoryResponseData(BaseModel):
    projects: List[ProjectSummaryItem]
    camera_stations: List[StationSummaryItem]
