import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.enums import AnonSessionStatus


class AnonResourceCounts(BaseModel):
    classifications: int
    camera_stations: int
    projects: int


class AnonSessionLimits(BaseModel):
    max_files: int
    max_camera_stations: int
    used_files: int
    used_camera_stations: int


class AnonSessionAuthHint(BaseModel):
    has_data: bool
    counts: AnonResourceCounts


class AnonSessionCreateData(BaseModel):
    anon_token: str
    expires_at: datetime
    data_retention: bool


class AnonSessionCurrentData(BaseModel):
    status: AnonSessionStatus
    expires_at: datetime
    data_retention: bool
    counts: AnonResourceCounts
    limits: AnonSessionLimits


class RenamedCameraStation(BaseModel):
    id: uuid.UUID
    old_code: str
    new_code: str


class ClaimAnonSessionData(BaseModel):
    claimed: AnonResourceCounts
    renamed_camera_stations: list[RenamedCameraStation]


class CloseAnonSessionData(BaseModel):
    status: Literal["expired"] = "expired"
    data_retained: bool
