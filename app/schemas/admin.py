"""Panel admin (§13). El admin nunca recibe contenido privado: solo conteos (CB-96)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.enums import AnonSessionStatus, Visibility
from app.schemas.auth import UserRead
from app.schemas.classification import ClassificationRead
from app.schemas.stats import Stats

AdminEntity = Literal["classifications", "camera-stations", "projects", "anon-sessions"]


class AdminStats(BaseModel):
    users: dict[str, Any]
    anon_sessions: dict[str, Any]
    content: dict[str, Any]
    model_feedback: dict[str, Any]
    anon_retention: dict[str, Any]
    fauna: Stats
    fauna_map: list[dict[str, Any]]


class AdminOwner(BaseModel):
    type: Literal["user", "anonymous"]
    display_name: str


class AdminCamera(BaseModel):
    id: uuid.UUID
    code: str
    name: str | None
    latitude: float
    longitude: float
    location_precision: Literal["exact", "approx_1km"]
    visibility: Visibility
    deployed_at: datetime
    retrieved_at: datetime | None
    still_installed: bool
    owner: AdminOwner
    anon_session_id: uuid.UUID | None
    is_deleted: bool
    deleted_at: datetime | None
    deleted_reason: str | None
    created_at: datetime


class AdminClassification(ClassificationRead):
    is_deleted: bool
    deleted_at: datetime | None
    deleted_reason: str | None
    owner_type: Literal["user", "anonymous"]


class AdminAnonSession(BaseModel):
    id: uuid.UUID
    label: str
    status: AnonSessionStatus
    created_at: datetime
    last_activity_at: datetime
    counts: dict[str, int]
    retained: bool
    is_deleted: bool


class ReasonBody(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class DeleteBatchBody(BaseModel):
    entity: AdminEntity
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    reason: str | None = Field(default=None, max_length=1000)


class CascadeCounts(BaseModel):
    classifications: int = 0
    camera_stations: int = 0
    projects: int = 0


class DeleteResult(BaseModel):
    deleted: CascadeCounts


class RestoreResult(BaseModel):
    restored: CascadeCounts


class Skipped(BaseModel):
    id: uuid.UUID
    code: str


class DeleteBatchResult(BaseModel):
    deleted: CascadeCounts
    skipped: list[Skipped]


class AdminUser(UserRead):
    counts: dict[str, int]


class ResetLink(BaseModel):
    reset_url: str
    expires_at: datetime


class SettingValue(BaseModel):
    value: Any
    updated_by: str | None
    updated_at: datetime | None


class AdminSettings(BaseModel):
    anon_data_retention: SettingValue


class SettingsUpdate(BaseModel):
    anon_data_retention: Any
    reason: str | None = Field(default=None, max_length=1000)


class AuditEntry(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: str | None
    old_value: Any
    new_value: Any
    reason: str | None
    created_at: datetime
    request_id: str | None
