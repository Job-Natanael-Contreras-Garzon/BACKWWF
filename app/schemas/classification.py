"""``Classification`` (§1.8) y los cuerpos de validación y ráfagas (§8.6–8.8)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    CaptureSource,
    Category,
    ClassificationSource,
    ClassificationStatus,
    CorrectionSource,
    MediaType,
    Rank,
    ValidationStatus,
)


class TaxonomyRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label_id: str | None
    class_: str | None = Field(serialization_alias="class")
    order: str | None
    family: str | None
    genus: str | None
    species: str | None
    scientific_name: str | None
    common_name: str | None
    rank: Rank | None


class ErrorInfo(BaseModel):
    code: str
    message: str


class QueueRef(BaseModel):
    position: int
    estimated_wait_seconds: int


class EvidenceRead(BaseModel):
    url: str
    frame_index: int | None
    timestamp_seconds: float | None
    timestamp_label: str | None
    bbox: list[float] | None
    width: int | None
    height: int | None


class ValidationRead(BaseModel):
    status: ValidationStatus
    correction_source: CorrectionSource | None
    corrected_taxonomy: TaxonomyRead | None
    suggested_name: str | None
    repeat_of: uuid.UUID | None
    notes: str | None
    validated_by: uuid.UUID | None
    validated_at: datetime | None


class ModelRead(BaseModel):
    detector: str | None
    classifier: str | None
    sampling: str | None
    pipeline_version: str | None


class ClassificationRead(BaseModel):
    id: uuid.UUID
    batch_id: uuid.UUID | None
    camera_station_id: uuid.UUID
    source: ClassificationSource
    file_name: str
    file_sha256: str
    media_type: MediaType
    duration_seconds: float | None
    captured_at: datetime | None
    captured_at_source: CaptureSource | None
    status: ClassificationStatus
    error: ErrorInfo | None
    warnings: list[dict[str, Any]]
    queue: QueueRef | None
    category: Category | None
    taxonomy: TaxonomyRead | None
    confidence: float | None
    alternatives: list[dict[str, Any]] | None
    frames_analyzed: int | None
    evidence: EvidenceRead | None
    validation: ValidationRead
    effective_taxonomy: TaxonomyRead | None
    model: ModelRead | None
    low_evidence: bool
    created_at: datetime
    validation_history: list[dict[str, Any]] | None = None


class MoveRequest(BaseModel):
    camera_station_id: uuid.UUID


ValidationAction = Literal[
    "confirm", "correct", "correct_unlisted", "reject", "discard_repeat", "reset"
]


class ValidationRequest(BaseModel):
    action: ValidationAction
    label_id: str | None = Field(default=None, max_length=64)
    correction_source: Literal["alternative", "catalog"] | None = None
    suggested_name: str | None = Field(default=None, min_length=3, max_length=120)
    repeat_of: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ValidationBatchRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)  # CB-67
    action: Literal["confirm", "reject", "reset"]
    notes: str | None = Field(default=None, max_length=2000)


class Skipped(BaseModel):
    id: uuid.UUID
    code: str


class ValidationBatchResult(BaseModel):
    updated: int
    skipped: list[Skipped]


class BurstItem(BaseModel):
    id: uuid.UUID
    file_name: str
    captured_at: datetime
    confidence: float | None
    validation_status: ValidationStatus
    evidence_url: str | None


class BurstTaxonomy(BaseModel):
    scientific_name: str | None
    common_name: str | None
    rank: Rank | None


class BurstGroup(BaseModel):
    group_key: str
    camera_station_id: uuid.UUID
    camera_station_code: str
    taxonomy: BurstTaxonomy
    start: datetime
    end: datetime
    span_seconds: int
    suggested_keep_id: uuid.UUID
    items: list[BurstItem]


class RepeatBatchRequest(BaseModel):
    keep_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    discard_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class RepeatBatchResult(BaseModel):
    kept: int
    discarded: int


class DismissRequest(BaseModel):
    group_key: str = Field(min_length=1, max_length=300)
    window_minutes: int | None = Field(default=None, ge=1, le=60)


class DismissResult(BaseModel):
    dismissed: int
