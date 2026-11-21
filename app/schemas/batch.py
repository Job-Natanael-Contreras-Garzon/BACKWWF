"""Schemas de lotes y subida (API_BACK_FRONT §1.9, §7)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import BatchSource, BatchStatus, ClassificationStatus


class BatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Opcional en el schema para responder CAMERA_REQUIRED (y no un VALIDATION_ERROR genérico).
    camera_station_id: uuid.UUID | None = None
    expected_files: int = Field(ge=1, le=500)


class BatchCounts(BaseModel):
    received: int = 0
    queued: int = 0
    processing: int = 0
    done: int = 0
    failed: int = 0
    cancelled: int = 0


class QueueInfo(BaseModel):
    position: int
    estimated_wait_seconds: int


class BatchQueue(BaseModel):
    next_position: int | None = None
    estimated_wait_seconds: int | None = None


class ItemError(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class BatchItem(BaseModel):
    client_index: int | None
    file_name: str
    status: ClassificationStatus
    classification_id: uuid.UUID | None
    queue: QueueInfo | None = None
    classification: dict[str, Any] | None = None  # el Classification completo llega con HU-11/12
    error: ItemError | None = None
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime


class BatchRead(BaseModel):
    id: uuid.UUID
    camera_station_id: uuid.UUID
    camera_station_code: str
    source: BatchSource
    status: BatchStatus
    expected_files: int
    counts: BatchCounts
    queue: BatchQueue
    created_at: datetime
    completed_at: datetime | None
    items: list[BatchItem] | None  # §7.5: los listados van sin items
