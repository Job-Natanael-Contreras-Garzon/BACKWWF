"""Estadísticas ecológicas (§10.2). Cada sección es opcional según ``?sections=``."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import ClassificationSource

StatsSection = Literal[
    "totals", "richness", "non_animal", "taxa", "by_camera", "by_month", "by_hour", "effort"
]
ALL_SECTIONS: tuple[StatsSection, ...] = (
    "totals",
    "richness",
    "non_animal",
    "taxa",
    "by_camera",
    "by_month",
    "by_hour",
    "effort",
)


class StatsFilters(BaseModel):
    from_: date | None = Field(default=None, serialization_alias="from")
    to: date | None = None
    only_validated: bool = False
    source: ClassificationSource | None = None


class Totals(BaseModel):
    files_processed: int
    files_with_fauna: int
    files_without_fauna: int
    files_error: int
    sightings: int
    validated: int
    corrected: int
    rejected: int
    discarded_repeat: int
    pending_validation: int


class Richness(BaseModel):
    species: int
    genera: int
    families: int


class NonAnimal(BaseModel):
    person: int
    vehicle: int
    blank: int


class SpeciesRow(BaseModel):
    label_id: str | None
    scientific_name: str | None
    common_name: str | None
    genus: str | None
    family: str | None
    count: int
    pct: float
    validated: int
    mean_confidence: float | None
    first_seen: datetime | None
    last_seen: datetime | None
    camera_stations: int


class GenusRow(BaseModel):
    label_id: str | None
    name: str
    family: str | None
    count: int
    pct: float


class FamilyRow(BaseModel):
    label_id: str | None
    name: str
    count: int
    pct: float


class Unidentified(BaseModel):
    genus: int
    family: int
    order: int
    class_: int = Field(serialization_alias="class")
    unlisted: int


class SpeciesCount(BaseModel):
    label_id: str | None
    count: int


class CameraRow(BaseModel):
    camera_station_id: uuid.UUID
    code: str
    sightings: int
    species: int
    species_counts: list[SpeciesCount]


class MonthRow(BaseModel):
    month: str
    sightings: int


class HourRow(BaseModel):
    hour: int
    sightings: int


class Effort(BaseModel):
    trap_days: float
    sightings_per_100_trap_days: float | None
    camera_stations_without_retrieval: int


class Stats(BaseModel):
    scope: Literal["camera_station", "project"]
    scope_id: uuid.UUID
    scope_name: str
    filters: StatsFilters
    generated_at: datetime
    totals: Totals | None = None
    richness: Richness | None = None
    non_animal: NonAnimal | None = None
    by_species: list[SpeciesRow] | None = None
    by_genus: list[GenusRow] | None = None
    by_family: list[FamilyRow] | None = None
    unidentified_to_species: Unidentified | None = None
    by_camera: list[CameraRow] | None = None
    by_month: list[MonthRow] | None = None
    by_hour: list[HourRow] | None = None
    effort: Effort | None = None
