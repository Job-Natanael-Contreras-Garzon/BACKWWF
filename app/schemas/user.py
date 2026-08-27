from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator

from app.core.enums import CameraStationStatus, ProjectStatus, UserGender


class UserBase(BaseModel):
    full_name: str
    email: str
    institucion: Optional[str] = None
    sexo: Optional[str] = None

    @field_validator("sexo", mode="before")
    @classmethod
    def validate_sexo(cls, v):
        if v is None:
            return None
        if isinstance(v, UserGender):
            return v.value
        s = str(v).strip()
        if not s:
            return None
        if s.upper() in ("M", "MASCULINO", "MALE"):
            return UserGender.MALE.value
        if s.upper() in ("F", "FEMENINO", "FEMALE"):
            return UserGender.FEMALE.value
        return s


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
