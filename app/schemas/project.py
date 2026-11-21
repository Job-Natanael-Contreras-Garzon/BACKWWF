"""Schemas de proyectos (API_BACK_FRONT §1.6, §6)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import Visibility
from app.schemas.camera_station import CameraStationRead, OwnerView


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("El nombre del proyecto no puede estar vacío.")
    return cleaned


class ProjectCounts(BaseModel):
    camera_stations: int = 0
    classifications: int = 0
    sightings: int = 0
    species: int = 0


class ProjectRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    visibility: Visibility
    owner: OwnerView
    camera_station_ids: list[uuid.UUID]
    counts: ProjectCounts
    version: int  # para If-Match en PATCH (CB-15)
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectRead):
    camera_stations: list[CameraStationRead]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    visibility: Visibility = Visibility.PRIVATE
    camera_station_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str | None:
        return _clean_name(value)


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    visibility: Visibility | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return _clean_name(value)


class AssociateCameraRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_station_id: uuid.UUID
