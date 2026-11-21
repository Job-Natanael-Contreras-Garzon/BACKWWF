"""Schemas de cámaras trampa (API_BACK_FRONT §1.3–§1.5, §5)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import Visibility

LocationPrecision = Literal["exact", "approx_1km"]


def _naive(value: datetime | None) -> datetime | None:
    """Hora local de la cámara: sin zona horaria (las cámaras trampa no la registran)."""
    if value is not None and value.tzinfo is not None:
        raise ValueError("La fecha va en hora local de la cámara, sin zona horaria.")
    return value


def _clean_code(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("El código no puede estar vacío.")
    return cleaned


class OwnerView(BaseModel):
    type: Literal["user", "anonymous"]
    is_mine: bool
    display_name: str | None = None
    institution: str | None = None


class CameraCounts(BaseModel):
    classifications: int = 0
    sightings: int = 0
    species: int = 0
    pending_validation: int = 0


class CameraStationRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str | None
    latitude: float
    longitude: float
    deployed_at: datetime
    retrieved_at: datetime | None
    still_installed: bool
    observations: str | None
    visibility: Visibility
    owner: OwnerView
    project_ids: list[uuid.UUID]
    counts: CameraCounts
    last_capture_at: datetime | None
    location_precision: LocationPrecision
    previous_camera_station_id: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime


class CameraStationMapItem(BaseModel):
    id: uuid.UUID
    code: str
    name: str | None
    latitude: float
    longitude: float
    location_precision: LocationPrecision
    visibility: Visibility
    is_mine: bool
    still_installed: bool
    sightings: int
    species: int


class _CameraFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    observations: str | None = Field(default=None, max_length=2000)

    @field_validator("deployed_at", "retrieved_at", check_fields=False)
    @classmethod
    def no_timezone(cls, value: datetime | None) -> datetime | None:
        return _naive(value)

    @field_validator("code", check_fields=False)
    @classmethod
    def clean_code(cls, value: str | None) -> str | None:
        return _clean_code(value)


class CameraStationCreate(_CameraFields):
    code: str = Field(min_length=1, max_length=50)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    deployed_at: datetime
    still_installed: bool
    retrieved_at: datetime | None = None
    visibility: Visibility = Visibility.PRIVATE
    project_id: uuid.UUID | None = None


class CameraStationUpdate(_CameraFields):
    """PATCH parcial: se validan las mismas reglas sobre el resultado final (§1.5)."""

    code: str | None = Field(default=None, min_length=1, max_length=50)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    deployed_at: datetime | None = None
    still_installed: bool | None = None
    retrieved_at: datetime | None = None
    visibility: Visibility | None = None


class RedeployRequest(_CameraFields):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    deployed_at: datetime
    close_previous: bool = True
    previous_retrieved_at: datetime | None = None


class RedeployData(BaseModel):
    camera_station: CameraStationRead
    previous: CameraStationRead


class NearbyMine(BaseModel):
    id: uuid.UUID
    code: str
    name: str | None
    distance_m: float
    still_installed: bool
    deployed_at: datetime
    retrieved_at: datetime | None
    classifications: int
    same_location: bool
    overlapping_period: bool


class NearbyPublic(BaseModel):
    id: uuid.UUID
    code: str
    distance_band: str
    owner: OwnerView


class NearbyData(BaseModel):
    mine: list[NearbyMine]
    public_others: list[NearbyPublic]


class TimeOffsetRequest(BaseModel):
    """#15d / CB-18: corrige el reloj de la cámara sobre ``captured_at`` (hora local, sin zona)."""

    offset_seconds: int = Field(ge=-316224000, le=316224000)
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)


class TimeOffsetResult(BaseModel):
    updated: int
