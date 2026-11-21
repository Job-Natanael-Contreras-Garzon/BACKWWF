"""Lotes y subida no bloqueante a la cola (HU-08, FL-08, DD-12; CB-16, CB-30..36, CB-50..59).

Subir es rápido: se valida, se guarda el temporal, se crea la fila ``queued`` y se avisa a la
cola. El análisis lo hace el worker (HU-11). Un archivo inválido no tumba el lote: responde 200
con el error del ítem y no entra en la cola.
"""

import asyncio
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.enums import BatchStatus, ClassificationSource, ClassificationStatus
from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    GoneError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
)
from app.core.logging import log_step, logger
from app.core.responses import Pagination
from app.db.uow import UnitOfWork
from app.integrations.queue import TaskQueue
from app.models.camera_station import CameraStation
from app.models.classification import Classification, ClassificationBatch
from app.schemas.batch import (
    BatchCounts,
    BatchCreate,
    BatchItem,
    BatchQueue,
    BatchRead,
    ItemError,
    QueueInfo,
)
from app.services import media_validator
from app.services.media_validator import AsyncReadable, MediaRejected
from app.services.policies import Owner
from app.worker import dispatcher

_ITEM_MESSAGES = {
    "CANCELLED_BY_USER": "Cancelaste este archivo.",
    "CAMERA_DELETED": "La cámara se eliminó; el archivo no se analizó.",
    "ACCOUNT_DISABLED": "La cuenta se desactivó; el archivo no se analizó.",
    "PROCESSING_EXPIRED": "El archivo estuvo demasiado tiempo en cola.",
    "AI_UNAVAILABLE": "El servicio de análisis no respondió.",
    "AI_TIMEOUT": "El análisis tardó demasiado.",
    "AI_NOT_READY": "El servicio de análisis se está iniciando.",
    "AI_BAD_RESPONSE": "El servicio de análisis respondió algo inesperado.",
    "MEDIA_DECODE_FAILED": "El archivo está dañado o incompleto.",
    "STORAGE_WRITE_FAILED": "No se pudo guardar el fotograma.",
}


async def _anon_retain(uow: UnitOfWork, owner: Owner) -> bool | None:
    """CB-42/43: la retención se fija al subir, no al terminar."""
    if not owner.is_anonymous:
        return None
    return bool(await uow.settings.get_value("anon_data_retention", True))


async def _own_camera(uow: UnitOfWork, owner: Owner, camera_id: uuid.UUID) -> CameraStation:
    camera = await uow.camera_stations.get_owned(camera_id, owner)
    if camera is not None:
        return camera  # retirada también vale (CB-16)
    if await uow.camera_stations.get_visible(camera_id, owner) is not None:
        raise ForbiddenError("FORBIDDEN", "Solo puedes subir archivos a tus propias cámaras.")
    raise NotFoundError("CAMERA_NOT_FOUND", "La cámara no existe o no tienes acceso a ella.")


async def _own_batch(
    uow: UnitOfWork, owner: Owner, batch_id: uuid.UUID, *, for_update: bool = False
) -> ClassificationBatch:
    batch = await uow.batches.get_owned(batch_id, owner, for_update=for_update)
    if batch is None:  # los lotes nunca son públicos: lo ajeno no existe (S1)
        raise NotFoundError("BATCH_NOT_FOUND", "El lote no existe.")
    return batch


async def _check_pending_limit(uow: UnitOfWork, owner: Owner, adding: int) -> None:
    """CB-34: tope de pendientes por usuario; para el anónimo, además, ANON_MAX_FILES."""
    pending = await uow.classifications.count_pending(owner)
    if pending + adding > settings.QUEUE_MAX_PENDING_PER_USER:
        raise RateLimitError(
            "QUEUE_USER_LIMIT",
            f"Tienes {pending} archivos en espera; espera a que avancen.",
            context={"pending": pending, "limit": settings.QUEUE_MAX_PENDING_PER_USER},
        )
    if owner.is_anonymous:
        used = await uow.classifications.count_active_files(owner)
        if used + adding > settings.ANON_MAX_FILES:
            remaining = max(settings.ANON_MAX_FILES - used, 0)
            raise BusinessRuleError(
                "ANON_LIMIT_REACHED",
                f"Sin cuenta puedes clasificar hasta {settings.ANON_MAX_FILES} archivos. "
                f"Te quedan {remaining}. Crea una cuenta gratis para seguir.",
                context={"limit": settings.ANON_MAX_FILES, "remaining": remaining},
            )


def _disk_usage_ratio(path: str) -> float:
    Path(path).mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(path)
    return usage.used / usage.total if usage.total else 0.0


async def _check_capacity(uow: UnitOfWork, queue: TaskQueue) -> None:
    """CB-35 (cola global o disco temporal llenos) y CB-36 (Redis caído)."""
    full = ServiceUnavailableError(
        "QUEUE_FULL", "El servidor está muy ocupado; reintentaremos en un minuto."
    )
    if await uow.classifications.count_queued_global() >= settings.QUEUE_MAX_GLOBAL:
        raise full
    if await asyncio.to_thread(_disk_usage_ratio, settings.TMP_UPLOAD_PATH) >= (
        settings.TMP_DISK_MAX_USAGE
    ):
        raise full
    await queue.ping()


def _rejected_item(file_name: str, client_index: int, error: MediaRejected) -> BatchItem:
    details = [{"context": error.context}] if error.context else []
    return BatchItem(
        client_index=client_index,
        file_name=file_name,
        status=ClassificationStatus.ERROR,
        classification_id=None,
        error=ItemError(code=error.code, message=error.message, details=details),
        updated_at=datetime.now(UTC),
    )


def _item(row: Classification, positions: dict[uuid.UUID, int]) -> BatchItem:
    queue = None
    if row.status == ClassificationStatus.QUEUED and row.id in positions:
        position = positions[row.id]
        queue = QueueInfo(
            position=position,
            estimated_wait_seconds=dispatcher.estimated_wait_seconds(position),
        )
    error = None
    if row.status in (ClassificationStatus.ERROR, ClassificationStatus.CANCELLED):
        code = row.error_code or "INTERNAL_ERROR"
        error = ItemError(
            code=code, message=_ITEM_MESSAGES.get(code, "No se pudo procesar el archivo.")
        )
    return BatchItem(
        client_index=row.client_index,
        file_name=row.file_name,
        status=row.status,
        classification_id=row.id,
        queue=queue,
        error=error,
        warnings=row.warnings or [],
        updated_at=row.updated_at,
    )


async def _reads(
    uow: UnitOfWork,
    batches: list[ClassificationBatch],
    *,
    with_items: bool,
    since: datetime | None = None,
) -> list[BatchRead]:
    ids = [b.id for b in batches]
    counts = await uow.classifications.status_counts(ids)
    rows = await uow.classifications.items_of_batches(ids)
    queued_ids = [r.id for r in rows if r.status == ClassificationStatus.QUEUED]
    positions = await dispatcher.queue_positions(uow, queued_ids)
    cameras = await uow.camera_stations.codes_by_ids([b.camera_station_id for b in batches])

    reads: list[BatchRead] = []
    for batch in batches:
        by_status = counts.get(batch.id, {})
        own_rows = [r for r in rows if r.batch_id == batch.id]
        own_positions = [positions[r.id] for r in own_rows if r.id in positions]
        next_position = min(own_positions) if own_positions else None
        reads.append(
            BatchRead(
                id=batch.id,
                camera_station_id=batch.camera_station_id,
                camera_station_code=cameras.get(batch.camera_station_id, ""),
                source=batch.source,
                status=batch.status,
                expected_files=batch.expected_files,
                counts=BatchCounts(
                    received=sum(by_status.values()) + batch.failed,
                    queued=by_status.get(ClassificationStatus.QUEUED, 0),
                    processing=by_status.get(ClassificationStatus.PROCESSING, 0),
                    done=by_status.get(ClassificationStatus.DONE, 0),
                    failed=by_status.get(ClassificationStatus.ERROR, 0) + batch.failed,
                    cancelled=by_status.get(ClassificationStatus.CANCELLED, 0),
                ),
                queue=BatchQueue(
                    next_position=next_position,
                    estimated_wait_seconds=(
                        dispatcher.estimated_wait_seconds(next_position) if next_position else None
                    ),
                ),
                created_at=batch.created_at,
                completed_at=batch.closed_at,
                items=(
                    [_item(r, positions) for r in own_rows if since is None or r.updated_at > since]
                    if with_items
                    else None
                ),
            )
        )
    return reads


async def create_batch(uow: UnitOfWork, owner: Owner, data: BatchCreate) -> BatchRead:
    with log_step("batch.create"):
        if data.camera_station_id is None:  # D7: también el anónimo sube a una cámara registrada
            raise BusinessRuleError(
                "CAMERA_REQUIRED", "Elige la cámara trampa donde se tomaron los archivos."
            )
        camera = await _own_camera(uow, owner, data.camera_station_id)
        await _check_pending_limit(uow, owner, data.expected_files)
        batch = ClassificationBatch(
            camera_station_id=camera.id,
            expected_files=data.expected_files,
            status=BatchStatus.OPEN,
        )
        owner.assign_to(batch, anon_retain=bool(await _anon_retain(uow, owner)))
        uow.batches.add(batch)
        await uow.commit()
        await uow.batches.refresh(batch)
        return (await _reads(uow, [batch], with_items=True))[0]


async def list_batches(
    uow: UnitOfWork,
    owner: Owner,
    *,
    active: bool,
    page: int,
    page_size: int,
    camera_station_id: uuid.UUID | None,
    status: BatchStatus | None,
) -> tuple[list[BatchRead], Pagination | None]:
    with log_step("batch.list"):
        if active:
            since = datetime.now(UTC) - timedelta(minutes=settings.BATCH_RECENT_MINUTES)
            batches = await uow.batches.list_active_or_recent(owner, since)
            return await _reads(uow, batches, with_items=False), None
        batches, total = await uow.batches.list_history(
            owner,
            page=page,
            page_size=page_size,
            camera_station_id=camera_station_id,
            status=status,
        )
        size = max(1, min(page_size, 200))
        pagination = Pagination(
            page=page, page_size=size, total=total, total_pages=ceil(total / size) if total else 0
        )
        return await _reads(uow, batches, with_items=False), pagination


async def _existing_item(
    uow: UnitOfWork, batch: ClassificationBatch, client_index: int
) -> tuple[BatchItem, int] | None:
    """Volver a subir el mismo client_index: si sigue vivo, se devuelve igual (idempotente);
    si quedó en error o cancelado, se reemplaza (§7.2)."""
    existing = await uow.classifications.get_by_client_index(batch.id, client_index)
    if existing is None:
        return None
    if existing.status in (ClassificationStatus.ERROR, ClassificationStatus.CANCELLED):
        existing.is_deleted = True
        existing.deleted_at = datetime.now(UTC)
        return None
    positions = await dispatcher.queue_positions(uow, [existing.id])
    code = 202 if existing.status == ClassificationStatus.QUEUED else 200
    return _item(existing, positions), code


async def upload_file(
    uow: UnitOfWork,
    queue: TaskQueue,
    owner: Owner,
    batch_id: uuid.UUID,
    *,
    upload: AsyncReadable,
    file_name: str,
    client_index: int,
    client_mtime: datetime | None,
) -> tuple[BatchItem, int]:
    """Devuelve el ítem y el HTTP: 202 en cola, 200 si el archivo no entra (error del ítem)."""
    with log_step("batch.upload", batch_id=str(batch_id), client_index=client_index):
        batch = await _own_batch(uow, owner, batch_id)
        if batch.status != BatchStatus.OPEN:
            raise ConflictError("BATCH_CLOSED", "Este lote ya no recibe archivos.")
        if client_index >= batch.expected_files:
            raise BusinessRuleError(
                "VALIDATION_ERROR",
                f"client_index debe ir de 0 a {batch.expected_files - 1}.",
            )
        existing = await uow.classifications.get_by_client_index(batch.id, client_index)
        if existing is not None and existing.status not in (
            ClassificationStatus.ERROR,
            ClassificationStatus.CANCELLED,
        ):
            positions = await dispatcher.queue_positions(uow, [existing.id])
            code = 202 if existing.status == ClassificationStatus.QUEUED else 200
            return _item(existing, positions), code
        await _check_pending_limit(uow, owner, 1)
        await _check_capacity(uow, queue)

        # Lo pesado (copiar, Pillow, ffprobe) va sin bloquear el lote: 3 subidas en paralelo.
        stored = None
        try:
            stored = await media_validator.store_upload(upload, file_name)
            info = await media_validator.inspect_media(stored, file_name, client_mtime)
            camera = await uow.camera_stations.get(batch.camera_station_id)
            if camera is None or camera.is_deleted:  # se borró mientras se subía
                raise NotFoundError("CAMERA_NOT_FOUND", "La cámara del lote ya no existe.")
            duplicate = await uow.classifications.find_active_by_sha256(camera.id, stored.sha256)
            if duplicate is not None:  # CB-50, CB-54
                raise MediaRejected(
                    "DUPLICATE_FILE",
                    "Este archivo ya está en esta cámara.",
                    {"classification_id": str(duplicate.id)},
                )
            elsewhere = await uow.classifications.find_sha256_in_other_cameras(
                owner, stored.sha256, camera.id
            )
            if elsewhere is not None:  # CB-51
                other = await uow.camera_stations.get(elsewhere.camera_station_id)
                code_other = other.code if other else ""
                raise MediaRejected(
                    "DUPLICATE_FILE_OTHER_CAMERA",
                    f"Ya está clasificado en {code_other}.",
                    {"classification_id": str(elsewhere.id), "camera_station_code": code_other},
                )
        except MediaRejected as rejected:
            if stored is not None:
                await media_validator.discard(stored.path)
            batch = await _own_batch(uow, owner, batch_id, for_update=True)
            batch.total += 1
            batch.failed += 1
            await uow.commit()
            logger.info(
                "Archivo rechazado al subir",
                extra={"event": "batch.upload.rejected", "error_code": rejected.code},
            )
            return _rejected_item(file_name, client_index, rejected), 200

        warnings = list(info.warnings)
        if info.captured_at < camera.deployed_at or (
            camera.retrieved_at is not None and info.captured_at > camera.retrieved_at
        ):  # CB-17: suele ser el reloj de la cámara mal configurado (CB-18)
            warnings.append(
                {
                    "code": "CAPTURE_OUTSIDE_DEPLOYMENT",
                    "message": "La fecha del archivo está fuera del periodo de instalación.",
                    "context": {"captured_at": info.captured_at.isoformat()},
                }
            )

        batch = await _own_batch(uow, owner, batch_id, for_update=True)
        if batch.status != BatchStatus.OPEN:
            await media_validator.discard(stored.path)
            raise ConflictError("BATCH_CLOSED", "Este lote ya no recibe archivos.")
        if (replaced := await _existing_item(uow, batch, client_index)) is not None:
            await media_validator.discard(stored.path)  # otra pestaña ganó la carrera
            return replaced

        row = Classification(
            batch_id=batch.id,
            client_index=client_index,
            camera_station_id=batch.camera_station_id,
            source=ClassificationSource.WEB,
            file_name=Path(file_name).name[:255],
            file_sha256=stored.sha256,
            file_size_bytes=stored.size_bytes,
            media_type=info.media_type,
            duration_seconds=info.duration_seconds,
            captured_at=info.captured_at,
            captured_at_source=info.captured_at_source,
            status=ClassificationStatus.QUEUED,
            warnings=warnings,
            tmp_key=stored.tmp_key,
            queued_at=datetime.now(UTC),
        )
        owner.assign_to(row, anon_retain=bool(await _anon_retain(uow, owner)))
        uow.classifications.add(row)
        batch.total += 1
        try:
            await uow.classifications.flush()
        except IntegrityError:  # mismo archivo, misma cámara, en paralelo (índice CB-50)
            await uow.session.rollback()
            await media_validator.discard(stored.path)
            return (
                _rejected_item(
                    file_name,
                    client_index,
                    MediaRejected("DUPLICATE_FILE", "Este archivo ya está en esta cámara."),
                ),
                200,
            )
        await uow.commit()
        await uow.classifications.refresh(row)
        try:
            await queue.wake(row.id)
        except ServiceUnavailableError:
            # La fila ya está en cola en la BD; el reaper (FL-33, HU-09) vuelve a avisar.
            logger.warning(
                "No se pudo avisar a la cola; queda para el reaper",
                extra={"event": "batch.upload.wake_failed", "classification_id": str(row.id)},
            )
        positions = await dispatcher.queue_positions(uow, [row.id])
        return _item(row, positions), 202


async def complete_batch(uow: UnitOfWork, owner: Owner, batch_id: uuid.UUID) -> BatchRead:
    """§7.3: el front terminó de enviar. Idempotente si el lote ya no está abierto."""
    with log_step("batch.complete", batch_id=str(batch_id)):
        batch = await _own_batch(uow, owner, batch_id, for_update=True)
        if batch.status == BatchStatus.OPEN:
            counts = (await uow.classifications.status_counts([batch.id])).get(batch.id, {})
            pending = counts.get(ClassificationStatus.QUEUED, 0) + counts.get(
                ClassificationStatus.PROCESSING, 0
            )
            errors = counts.get(ClassificationStatus.ERROR, 0) + batch.failed
            if pending:
                batch.status = BatchStatus.PROCESSING
            else:
                batch.status = (
                    BatchStatus.COMPLETED_WITH_ERRORS if errors else BatchStatus.COMPLETED
                )
                batch.closed_at = datetime.now(UTC)
            await uow.commit()
            await uow.batches.refresh(batch)
        return (await _reads(uow, [batch], with_items=True))[0]


def _finalize(batch: ClassificationBatch, counts: dict[ClassificationStatus, int]) -> None:
    """Un lote ``processing`` sin pendientes pasa a su estado final."""
    pending = counts.get(ClassificationStatus.QUEUED, 0) + counts.get(
        ClassificationStatus.PROCESSING, 0
    )
    if batch.status != BatchStatus.PROCESSING or pending:
        return
    errors = counts.get(ClassificationStatus.ERROR, 0) + batch.failed
    batch.status = BatchStatus.COMPLETED_WITH_ERRORS if errors else BatchStatus.COMPLETED
    batch.closed_at = datetime.now(UTC)


async def refresh_batch_status(uow: UnitOfWork, batch: ClassificationBatch) -> None:
    """Lo usan el reaper (HU-09) y el worker (HU-11) al terminar cada archivo."""
    counts = (await uow.classifications.status_counts([batch.id])).get(batch.id, {})
    _finalize(batch, counts)


async def get_batch(
    uow: UnitOfWork, owner: Owner, batch_id: uuid.UUID, since: datetime | None
) -> BatchRead:
    """§7.4: con ``since``, solo los ítems que cambiaron después (polling eficiente)."""
    with log_step("batch.get", batch_id=str(batch_id)):
        batch = await _own_batch(uow, owner, batch_id)
        return (await _reads(uow, [batch], with_items=True, since=since))[0]


async def _cancel_rows(uow: UnitOfWork, rows: list[Classification]) -> None:
    for row in rows:
        row.status = ClassificationStatus.CANCELLED
        row.error_code = "CANCELLED_BY_USER"
        if row.tmp_key:
            await media_validator.discard(Path(settings.TMP_UPLOAD_PATH) / row.tmp_key)
            row.tmp_key = None


async def cancel_batch(uow: UnitOfWork, owner: Owner, batch_id: uuid.UUID) -> BatchRead:
    """§7.6: cancela los ``queued``; los ``processing`` terminan normalmente (CB-40)."""
    with log_step("batch.cancel", batch_id=str(batch_id)):
        batch = await _own_batch(uow, owner, batch_id, for_update=True)
        rows = await uow.classifications.items_of_batch(batch.id)
        await _cancel_rows(uow, [r for r in rows if r.status == ClassificationStatus.QUEUED])
        if batch.status in (BatchStatus.OPEN, BatchStatus.PROCESSING):
            batch.status = BatchStatus.CANCELLED
            batch.closed_at = datetime.now(UTC)
        await uow.commit()
        await uow.batches.refresh(batch)
        return (await _reads(uow, [batch], with_items=True))[0]


async def _own_item(
    uow: UnitOfWork, owner: Owner, batch_id: uuid.UUID, client_index: int
) -> tuple[ClassificationBatch, Classification]:
    batch = await _own_batch(uow, owner, batch_id, for_update=True)
    row = await uow.classifications.get_by_client_index(batch.id, client_index)
    if row is None:
        raise NotFoundError("CLASSIFICATION_NOT_FOUND", "Ese archivo no está en el lote.")
    return batch, row


async def cancel_item(
    uow: UnitOfWork, owner: Owner, batch_id: uuid.UUID, client_index: int
) -> None:
    """§7.7: solo un ítem ``queued`` se puede cancelar (CB-40)."""
    with log_step("batch.item.cancel", batch_id=str(batch_id), client_index=client_index):
        batch, row = await _own_item(uow, owner, batch_id, client_index)
        if row.status != ClassificationStatus.QUEUED:
            raise ConflictError(
                "ITEM_NOT_CANCELLABLE", "Este archivo ya se está analizando o terminó."
            )
        await _cancel_rows(uow, [row])
        await refresh_batch_status(uow, batch)
        await uow.commit()


async def retry_item(
    uow: UnitOfWork,
    queue: TaskQueue,
    owner: Owner,
    batch_id: uuid.UUID,
    client_index: int,
) -> tuple[BatchItem, int]:
    """§7.8: vuelve a la cola un ítem en ``error`` si su temporal sigue disponible (CB-37/39).

    Idempotente: un ítem que ya está en cola, procesando o listo se devuelve tal cual.
    """
    with log_step("batch.item.retry", batch_id=str(batch_id), client_index=client_index):
        batch, row = await _own_item(uow, owner, batch_id, client_index)
        if row.status != ClassificationStatus.ERROR:
            positions = await dispatcher.queue_positions(uow, [row.id])
            code = 202 if row.status == ClassificationStatus.QUEUED else 200
            return _item(row, positions), code
        tmp = Path(settings.TMP_UPLOAD_PATH) / row.tmp_key if row.tmp_key else None
        if tmp is None or not await asyncio.to_thread(tmp.is_file):
            raise GoneError(
                "RETRY_FILE_UNAVAILABLE",
                "El archivo ya no está en el servidor; vuelve a subirlo.",
            )
        await _check_pending_limit(uow, owner, 1)
        await _check_capacity(uow, queue)
        row.status = ClassificationStatus.QUEUED
        row.error_code = None
        row.queued_at = datetime.now(UTC)
        row.started_at = None
        row.heartbeat_at = None
        if batch.status not in (BatchStatus.OPEN, BatchStatus.PROCESSING):
            batch.status, batch.closed_at = BatchStatus.PROCESSING, None
        try:
            await uow.classifications.flush()
        except IntegrityError as exc:  # el mismo archivo ya volvió a la cola por otra vía
            raise ConflictError("DUPLICATE_FILE", "Este archivo ya está en esta cámara.") from exc
        await uow.commit()
        await uow.classifications.refresh(row)
        try:
            await queue.wake(row.id)
        except ServiceUnavailableError:
            logger.warning(
                "No se pudo avisar a la cola; queda para el reaper",
                extra={"event": "batch.retry.wake_failed", "classification_id": str(row.id)},
            )
        positions = await dispatcher.queue_positions(uow, [row.id])
        return _item(row, positions), 202
