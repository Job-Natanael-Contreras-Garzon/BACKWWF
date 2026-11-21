"""Importación de paquetes de escritorio (§12)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.core.enums import ImportStatus
from app.schemas.camera_station import CameraStationCreate


class ImportCamera(BaseModel):
    id: uuid.UUID
    code: str
    deployed_at: datetime
    retrieved_at: datetime | None


class ImportPreview(BaseModel):
    import_id: uuid.UUID
    status: ImportStatus
    expires_at: datetime | None
    camera_station: ImportCamera | None
    package: dict[str, Any]
    counts: dict[str, Any]
    camera_code_matches: bool | None
    camera_from_package: dict[str, Any] | None
    matching_camera_station_id: uuid.UUID | None
    issues: list[dict[str, Any]]


class ImportConfirm(BaseModel):
    include_warnings: bool = True
    camera: CameraStationCreate | None = None


class ImportResult(BaseModel):
    batch_id: uuid.UUID
    imported: int
    skipped_duplicates: int
    skipped_invalid: int


class ImportListItem(BaseModel):
    import_id: uuid.UUID
    status: ImportStatus
    camera_station_id: uuid.UUID | None
    camera_code: str | None
    package_created_at: datetime | None
    imported: int | None
    created_at: datetime


class ImportDetail(BaseModel):
    """D10: estado de una importación (``processing`` → ``completed`` o ``failed``)."""

    import_id: uuid.UUID
    status: ImportStatus
    camera_station_id: uuid.UUID | None
    camera_code: str | None
    expires_at: datetime | None
    counts: dict[str, Any]
    result: ImportResult | None
    error: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
