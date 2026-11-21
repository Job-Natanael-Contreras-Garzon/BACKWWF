"""Importación de paquetes ``.wwm.zip`` de escritorio (HU-10, FL-23, §12, CB-80..87).

Vista previa: valida todo **sin escribir clasificaciones** y guarda el zip 1 h en
``TMP_UPLOAD_PATH/imports``. Confirmar vuelve a validar ese mismo archivo (no se confía en lo que
quedó en memoria), recodifica los fotogramas sin EXIF y crea un lote ``desktop`` ya terminado.
"""

import asyncio
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.enums import (
    BatchSource,
    BatchStatus,
    CaptureSource,
    ClassificationSource,
    ClassificationStatus,
    ImportStatus,
)
from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    GoneError,
    NotFoundError,
)
from app.core.logging import log_step, logger
from app.core.responses import Pagination
from app.db.uow import UnitOfWork
from app.integrations.ia_contract.package import CameraInfo, PackageLine
from app.integrations.storage.base import StorageBackend
from app.models.camera_station import CameraStation
from app.models.classification import Classification, ClassificationBatch
from app.models.desktop_import import DesktopImport
from app.schemas.camera_station import CameraStationCreate
from app.schemas.imports import (
    ImportCamera,
    ImportConfirm,
    ImportListItem,
    ImportPreview,
    ImportResult,
)
from app.services import camera_station_service, evidence, media_validator
from app.services.catalog_service import get_catalog
from app.services.package_validator import Issue, PackageTooLarge, ParsedPackage, parse
from app.services.policies import Owner

PREVIEW_TTL = timedelta(hours=1)
MAX_ISSUES = 200
_CHUNK = 1024 * 1024
_NOT_FOUND = "No encontramos esa importación."


def imports_dir() -> Path:
    # Subcarpeta propia: la limpieza de huérfanos (FL-31) solo mira archivos sueltos de la raíz.
    return Path(settings.TMP_UPLOAD_PATH) / "imports"


async def _store(upload: Any) -> Path:
    path = imports_dir() / f"{uuid.uuid4().hex}.wwm.zip"
    await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    limit, size = settings.IMPORT_MAX_MB * 1024 * 1024, 0
    handle = await asyncio.to_thread(path.open, "wb")
    try:
        while chunk := await upload.read(_CHUNK):
            size += len(chunk)
            if size > limit:
                raise PackageTooLarge(
                    "IMPORT_TOO_LARGE", f"El paquete supera {settings.IMPORT_MAX_MB} MB."
                )
            await asyncio.to_thread(handle.write, chunk)
    except BaseException:
        await asyncio.to_thread(handle.close)
        await media_validator.discard(path)
        raise
    await asyncio.to_thread(handle.close)
    return path


async def _parse(path: Path) -> ParsedPackage:
    return await asyncio.to_thread(parse, path, get_catalog().by_id.keys())


def _naive(value: datetime | None) -> datetime | None:
    """La hora de la cámara se guarda sin zona (como en la subida web)."""
    return value.replace(tzinfo=None) if value is not None else None


async def _own_camera(uow: UnitOfWork, owner: Owner, camera_id: uuid.UUID) -> CameraStation:
    camera = await uow.camera_stations.get_owned(camera_id, owner)
    if camera is not None:
        return camera
    if await uow.camera_stations.get_visible(camera_id, owner) is not None:
        raise ForbiddenError("CAMERA_NOT_OWNED", "Solo puedes importar en tus propias cámaras.")
    raise NotFoundError("CAMERA_NOT_FOUND", "No encontramos esa cámara.")


@dataclass
class _Window:
    deployed_at: datetime | None
    retrieved_at: datetime | None


def _outside(line: PackageLine, window: _Window) -> bool:
    """CB-17/CB-81: fecha de captura fuera de colocación–retiro (solo advierte)."""
    captured = _naive(line.captured_at)
    if captured is None or window.deployed_at is None:
        return False
    return captured < window.deployed_at or (
        window.retrieved_at is not None and captured > window.retrieved_at
    )


@dataclass
class _Plan:
    """Qué pasa con cada línea: importar, saltar por duplicado o por inválida."""

    to_import: list[tuple[PackageLine, bool]]  # (línea, fuera de rango)
    issues: list[Issue]
    duplicates: int
    invalid: int
    outside: int
    by_category: Counter[str]


async def _plan(
    uow: UnitOfWork,
    parsed: ParsedPackage,
    camera_id: uuid.UUID | None,
    window: _Window,
    include_warnings: bool = True,
) -> _Plan:
    valid = [p for p in parsed.lines if p.valid and p.line is not None]
    shas = [p.line.file_sha256 for p in valid if p.line is not None]
    existing = await uow.classifications.active_shas(camera_id, shas) if camera_id else set()
    issues = [i for p in parsed.lines for i in p.issues]
    seen: set[str] = set()
    plan = _Plan([], issues, 0, sum(not p.valid for p in parsed.lines), 0, Counter())
    for p in valid:
        line = p.line
        if line is None:  # pragma: no cover - filtrado en ``valid``
            continue
        if line.file_sha256 in existing or line.file_sha256 in seen:  # CB-55, CB-83
            plan.duplicates += 1
            continue
        seen.add(line.file_sha256)
        outside = _outside(line, window)
        if outside:
            plan.outside += 1
            issues.append(
                Issue(
                    p.number,
                    line.file_name,
                    "warning",
                    "CAPTURE_OUTSIDE_DEPLOYMENT",
                    "La fecha de captura queda fuera del período de la cámara.",
                )
            )
            if not include_warnings:
                continue
        plan.by_category[line.category.value if line.category else "error"] += 1
        plan.to_import.append((line, outside))
    plan.issues.sort(key=lambda i: i.line)
    return plan


def _counts(parsed: ParsedPackage, plan: _Plan) -> dict[str, Any]:
    return {
        "lines": len(parsed.lines),
        "new": len(plan.to_import),
        "duplicates": plan.duplicates,
        "invalid": plan.invalid,
        "outside_deployment_range": plan.outside,
        "by_category": dict(plan.by_category),
    }


def _camera_from_package(info: CameraInfo | None) -> dict[str, Any] | None:
    if info is None:
        return None
    return {**info.model_dump(mode="json"), "complete": info.is_complete}


def _package_info(parsed: ParsedPackage) -> dict[str, Any]:
    m = parsed.manifest
    return {
        "format_version": m.format_version,
        "app_version": m.app_version,
        "camera_code": m.camera_code,
        "created_at": m.created_at.isoformat(),
        "model": m.model.model_dump(mode="json"),
    }


def _camera_read(camera: CameraStation | None) -> ImportCamera | None:
    if camera is None:
        return None
    return ImportCamera(
        id=camera.id,
        code=camera.code,
        deployed_at=camera.deployed_at,
        retrieved_at=camera.retrieved_at,
    )


async def _check_not_imported(uow: UnitOfWork, camera_id: uuid.UUID, sha: str) -> None:
    previous = await uow.desktop_imports.find_completed(camera_id, sha)
    if previous is not None:  # CB-82
        raise ConflictError(
            "IMPORT_ALREADY_IMPORTED",
            "Este paquete ya se importó en esa cámara.",
            details=[{"context": {"import_id": str(previous.id)}}],
        )


async def preview(
    uow: UnitOfWork,
    owner: Owner,
    upload: Any,
    *,
    camera_station_id: uuid.UUID | None,
    create_camera: bool,
) -> ImportPreview:
    """§12.1: si el paquete es inválido se rechaza entero y no queda nada escrito (CA-1)."""
    with log_step("import.preview"):
        if (camera_station_id is None) == (not create_camera):
            raise BusinessRuleError(
                "VALIDATION_ERROR",
                "Indica una cámara propia o create_camera=true (solo uno).",
                details=[{"field": "camera_station_id"}],
            )
        camera = await _own_camera(uow, owner, camera_station_id) if camera_station_id else None
        path = await _store(upload)
        try:
            parsed = await _parse(path)
            if camera is not None:
                await _check_not_imported(uow, camera.id, parsed.sha256)
        except BaseException:
            await media_validator.discard(path)
            raise
        info = parsed.manifest.camera
        window = (
            _Window(camera.deployed_at, camera.retrieved_at)
            if camera
            else _Window(_naive(info.deployed_at), _naive(info.retrieved_at))
            if info
            else _Window(None, None)
        )
        plan = await _plan(uow, parsed, camera.id if camera else None, window)
        code = parsed.manifest.camera_code or (info.code if info else None)
        match = await uow.camera_stations.find_active_by_code(owner, code) if code else None
        counts = _counts(parsed, plan)
        record = DesktopImport(
            owner_user_id=owner.user_id,
            camera_station_id=camera.id if camera else None,  # None = crear al confirmar
            package_sha256=parsed.sha256,
            manifest=parsed.manifest.model_dump(mode="json", by_alias=True),
            status=ImportStatus.PREVIEW,
            counts=counts,
            tmp_key=path.name,
            expires_at=datetime.now(UTC) + PREVIEW_TTL,
        )
        uow.desktop_imports.add(record)
        await uow.commit()
        return ImportPreview(
            import_id=record.id,
            status=record.status,
            expires_at=record.expires_at,
            camera_station=_camera_read(camera),
            package=_package_info(parsed),
            counts=counts,
            camera_code_matches=(
                (code or "").strip().lower() == camera.code.lower() if camera else None
            ),
            camera_from_package=_camera_from_package(info),
            matching_camera_station_id=match.id if match else None,  # CB-87
            issues=[i.as_dict() for i in plan.issues[:MAX_ISSUES]],
        )


async def _record(uow: UnitOfWork, owner: Owner, import_id: uuid.UUID) -> DesktopImport:
    record = (
        await uow.desktop_imports.get_owned(import_id, owner.user_id) if owner.user_id else None
    )
    if record is None:
        raise NotFoundError("IMPORT_NOT_FOUND", _NOT_FOUND)
    return record


async def _expire(uow: UnitOfWork, record: DesktopImport) -> None:
    record.status = ImportStatus.EXPIRED
    tmp, record.tmp_key = record.tmp_key, None
    await uow.commit()
    if tmp:
        await media_validator.discard(imports_dir() / tmp)


def _camera_input(
    info: CameraInfo | None, override: CameraStationCreate | None
) -> CameraStationCreate:
    if override is not None:
        return override
    if info is None or not info.is_complete:
        raise BusinessRuleError(
            "VALIDATION_ERROR",
            "Faltan datos de la cámara en el paquete: complétalos para crearla.",
            details=[{"field": "camera"}],
        )
    return CameraStationCreate(
        code=info.code or "",
        name=info.name,
        latitude=info.latitude or 0.0,
        longitude=info.longitude or 0.0,
        deployed_at=_naive(info.deployed_at) or datetime.now(UTC).replace(tzinfo=None),
        retrieved_at=_naive(info.retrieved_at),
        still_installed=bool(info.still_installed),
        observations=info.observations,
    )


def _classification(
    line: PackageLine,
    *,
    owner: Owner,
    camera_id: uuid.UUID,
    batch_id: uuid.UUID,
    index: int,
    model: Any,
    outside: bool,
) -> Classification:
    done = line.status.value == "done"
    tax = line.taxonomy
    capture = (
        CaptureSource(line.captured_at_source.value)
        if line.captured_at_source.value != "none"
        else None
    )
    now = datetime.now(UTC)
    row = Classification(
        id=uuid.uuid4(),
        batch_id=batch_id,
        client_index=index,
        camera_station_id=camera_id,
        source=ClassificationSource.DESKTOP,
        file_name=line.file_name[:255],
        file_sha256=line.file_sha256,
        file_size_bytes=line.file_size_bytes,
        media_type=line.media_type,
        duration_seconds=line.duration_seconds,
        captured_at=_naive(line.captured_at),
        captured_at_source=capture,
        category=line.category if done else None,
        label_id=tax.label_id if tax else None,
        label_raw=tax.label_raw if tax else None,
        class_=tax.class_ if tax else None,
        order_=tax.order if tax else None,
        family=tax.family if tax else None,
        genus=tax.genus if tax else None,
        species=tax.species if tax else None,
        scientific_name=tax.scientific_name if tax else None,
        common_name=tax.common_name if tax else None,
        rank=tax.rank if tax else None,
        confidence=line.confidence,
        alternatives=[a.model_dump(mode="json") for a in line.alternatives],
        frames_analyzed=line.frames_analyzed,
        model_detector=model.detector,
        model_classifier=model.classifier,
        model_sampling=model.sampling,
        pipeline_version=model.pipeline_version,
        status=ClassificationStatus.DONE if done else ClassificationStatus.ERROR,
        error_code=line.error_code,
        warnings=(
            [
                {
                    "code": "CAPTURE_OUTSIDE_DEPLOYMENT",
                    "message": "La fecha de captura queda fuera del período de la cámara.",
                    "context": {},
                }
            ]
            if outside
            else []
        ),
        queued_at=now,
        finished_at=now,
    )
    owner.assign_to(row, anon_retain=True)
    return row


async def confirm(
    uow: UnitOfWork,
    storage: StorageBackend,
    owner: Owner,
    import_id: uuid.UUID,
    body: ImportConfirm,
) -> ImportResult:
    """§12.2 / CA-3: crea la cámara si hacía falta, guarda fotogramas y filas, borra el zip."""
    with log_step("import.confirm", import_id=str(import_id)):
        record = await _record(uow, owner, import_id)
        if record.status == ImportStatus.COMPLETED:
            raise ConflictError("IMPORT_ALREADY_IMPORTED", "Esta importación ya se confirmó.")
        if record.status != ImportStatus.PREVIEW:
            raise NotFoundError("IMPORT_NOT_FOUND", _NOT_FOUND)
        if record.expires_at is None or record.expires_at < datetime.now(UTC) or not record.tmp_key:
            await _expire(uow, record)
            raise GoneError("IMPORT_PREVIEW_EXPIRED", "La vista previa venció: vuelve a subirlo.")
        path = imports_dir() / record.tmp_key
        parsed = await _parse(path)  # se valida de nuevo el archivo guardado
        if record.camera_station_id is not None:
            camera = await _own_camera(uow, owner, record.camera_station_id)
        else:
            data = _camera_input(parsed.manifest.camera, body.camera)
            created, _ = await camera_station_service.create_camera(uow, owner, data)
            camera = await _own_camera(uow, owner, created.id)
        await _check_not_imported(uow, camera.id, parsed.sha256)
        plan = await _plan(
            uow,
            parsed,
            camera.id,
            _Window(camera.deployed_at, camera.retrieved_at),
            include_warnings=body.include_warnings,
        )
        batch = ClassificationBatch(
            camera_station_id=camera.id,
            source=BatchSource.DESKTOP_IMPORT,
            status=BatchStatus.COMPLETED,
            expected_files=max(len(plan.to_import), 1),
            total=len(plan.to_import),
            closed_at=datetime.now(UTC),
        )
        owner.assign_to(batch, anon_retain=True)
        uow.batches.add(batch)
        await uow.batches.flush()

        written: list[str] = []
        rows: list[Classification] = []
        try:
            for index, (line, outside) in enumerate(plan.to_import):
                row = _classification(
                    line,
                    owner=owner,
                    camera_id=camera.id,
                    batch_id=batch.id,
                    index=index,
                    model=parsed.manifest.model,
                    outside=outside,
                )
                if line.evidence is not None:
                    raw = await asyncio.to_thread(_read, path, line.evidence.file)
                    jpeg, width, height = await asyncio.to_thread(evidence.reencode_bytes, raw)
                    key = evidence.evidence_key(row.id, datetime.now(UTC))
                    await storage.put(key, jpeg, "image/jpeg")  # primero el archivo (DD-3)
                    written.append(key)
                    row.evidence_key, row.evidence_width, row.evidence_height = key, width, height
                    row.evidence_frame_index = line.evidence.frame_index
                    row.evidence_timestamp_seconds = line.evidence.timestamp_seconds
                    row.evidence_bbox = list(line.evidence.bbox)
                rows.append(row)
            for row in rows:
                uow.classifications.add(row)
            batch.done = sum(r.status == ClassificationStatus.DONE for r in rows)
            batch.failed = len(rows) - batch.done
            if batch.failed:
                batch.status = BatchStatus.COMPLETED_WITH_ERRORS
            record.camera_station_id = camera.id
            record.status = ImportStatus.COMPLETED
            record.counts = {
                **_counts(parsed, plan),
                "imported": len(rows),
                "batch_id": str(batch.id),
            }
            tmp, record.tmp_key = record.tmp_key, None
            await uow.commit()
        except BaseException:
            for key in written:  # no dejar fotogramas sin fila
                await storage.delete(key)
            raise
        await media_validator.discard(imports_dir() / tmp)
        logger.info(
            "Importación confirmada",
            extra={"event": "import.confirm.completed", "imported": len(rows)},
        )
        return ImportResult(
            import_id=record.id,
            status=record.status,
            batch_id=batch.id,
            imported=len(rows),
            skipped_duplicates=plan.duplicates,
            skipped_invalid=plan.invalid,
        )


def _read(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as zf:
        return zf.read(name)


async def cancel(uow: UnitOfWork, owner: Owner, import_id: uuid.UUID) -> None:
    """§12.3: solo una vista previa se cancela; borra el temporal."""
    record = await _record(uow, owner, import_id)
    if record.status != ImportStatus.PREVIEW:
        raise NotFoundError("IMPORT_NOT_FOUND", _NOT_FOUND)
    record.status = ImportStatus.CANCELLED
    tmp, record.tmp_key = record.tmp_key, None
    await uow.commit()
    if tmp:
        await media_validator.discard(imports_dir() / tmp)


async def list_imports(
    uow: UnitOfWork,
    owner: Owner,
    camera_station_id: uuid.UUID | None,
    page: int,
    page_size: int,
) -> tuple[list[ImportListItem], Pagination]:
    if owner.user_id is None:  # pragma: no cover - el router exige Bearer
        return [], Pagination(page=page, page_size=page_size, total=0, total_pages=0)
    records, total = await uow.desktop_imports.list_owned(
        owner.user_id, camera_station_id, page, page_size
    )
    codes = await uow.camera_stations.codes_by_ids(
        [r.camera_station_id for r in records if r.camera_station_id]
    )
    items = [
        ImportListItem(
            import_id=r.id,
            status=r.status,
            camera_station_id=r.camera_station_id,
            camera_code=codes.get(r.camera_station_id) if r.camera_station_id else None,
            package_created_at=r.manifest.get("created_at"),
            imported=r.counts.get("imported"),
            created_at=r.created_at,
        )
        for r in records
    ]
    size = max(1, min(page_size, 200))
    return items, Pagination(
        page=page, page_size=size, total=total, total_pages=ceil(total / size) if total else 0
    )


async def expire_previews(uow: UnitOfWork, now: datetime) -> int:
    """FL-31: las vistas previas vencidas pasan a ``expired`` y se borra su zip."""
    records = await uow.desktop_imports.expired_previews(now)
    tmps = []
    for record in records:
        record.status = ImportStatus.EXPIRED
        if record.tmp_key:
            tmps.append(record.tmp_key)
        record.tmp_key = None
    await uow.commit()
    for tmp in tmps:
        await media_validator.discard(imports_dir() / tmp)
    return len(records)
