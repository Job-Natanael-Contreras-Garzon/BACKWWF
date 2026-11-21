"""Crons de la cola (FL-33 reaper, FL-31 limpieza).

Funciones normales: el worker de arq (HU-11) las agenda, y también se corren a mano con
``python -m app.cli reaper`` o ``cleanup``. Son idempotentes: correrlas dos veces no hace daño.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import settings
from app.core.enums import BatchStatus, ClassificationStatus
from app.core.errors import ServiceUnavailableError
from app.core.logging import flow_var, logger
from app.db.uow import UnitOfWork
from app.integrations.queue import TaskQueue
from app.integrations.storage.base import StorageBackend
from app.services import batch_service, import_service, media_validator

_REWAKE_LIMIT = 1000


@dataclass(frozen=True, slots=True)
class ReaperSummary:
    requeued: int
    interrupted: int
    expired: int
    rewoken: int
    batches_closed: int
    batches_finished: int


@dataclass(frozen=True, slots=True)
class CleanupSummary:
    tmp_deleted: int
    retry_expired: int
    frames_deleted: int
    imports_expired: int = 0


async def reaper(
    queue: TaskQueue,
    uow_factory: Callable[[], UnitOfWork] = UnitOfWork,
    now: datetime | None = None,
) -> ReaperSummary:
    """FL-33 (cada 5 min): recupera ítems colgados (CB-38), vence los viejos (CB-39), vuelve a
    avisar a Redis lo que esté en cola (CB-36) y cierra lotes inactivos (CB-32)."""
    flow_token = flow_var.set("FL-33")
    try:
        current = now or datetime.now(UTC)
        requeued = interrupted = expired = 0
        async with uow_factory() as uow:
            stale = await uow.classifications.stale_processing(
                current - timedelta(minutes=settings.REAPER_HEARTBEAT_MINUTES)
            )
            for row in stale:
                row.heartbeat_at = None
                row.started_at = None
                if row.attempts >= settings.REAPER_MAX_ATTEMPTS:
                    row.status, row.error_code = (
                        ClassificationStatus.ERROR,
                        "PROCESSING_INTERRUPTED",
                    )
                    interrupted += 1
                else:
                    row.status = ClassificationStatus.QUEUED
                    requeued += 1

            old = await uow.classifications.queued_before(
                current - timedelta(hours=settings.TMP_UPLOAD_TTL_HOURS)
            )
            for row in old:
                row.status, row.error_code = ClassificationStatus.ERROR, "PROCESSING_EXPIRED"
                if row.tmp_key:
                    await media_validator.discard(Path(settings.TMP_UPLOAD_PATH) / row.tmp_key)
                    row.tmp_key = None
                expired += 1

            idle = await uow.batches.open_idle_since(
                current - timedelta(minutes=settings.BATCH_IDLE_CLOSE_MINUTES)
            )
            for batch in idle:  # nadie llamó a /complete: se cierra como incompleto
                batch.status, batch.closed_at = BatchStatus.INCOMPLETE, current
            finished = 0
            for batch in await uow.batches.processing_batches():
                await batch_service.refresh_batch_status(uow, batch)
                finished += batch.status != BatchStatus.PROCESSING
            await uow.commit()
            queued = await uow.classifications.queued_ids(_REWAKE_LIMIT)

        rewoken = 0
        for classification_id in queued:  # _job_id por archivo: no duplica avisos pendientes
            try:
                await queue.wake(classification_id)
            except ServiceUnavailableError:
                logger.warning("Redis sigue caído", extra={"event": "queue.reaper.redis_down"})
                break
            rewoken += 1

        summary = ReaperSummary(requeued, interrupted, expired, rewoken, len(idle), finished)
        logger.info(
            "Reaper completado", extra={"event": "queue.reaper.completed", **vars_of(summary)}
        )
        return summary
    finally:
        flow_var.reset(flow_token)


def vars_of(summary: ReaperSummary | CleanupSummary) -> dict[str, int]:
    return {name: getattr(summary, name) for name in summary.__slots__}


def _old_tmp_files(root: Path, cutoff: float) -> list[Path]:
    if not root.is_dir():
        return []
    return [p for p in root.iterdir() if p.is_file() and p.stat().st_mtime < cutoff]


async def cleanup(
    storage: StorageBackend,
    uow_factory: Callable[[], UnitOfWork] = UnitOfWork,
    now: datetime | None = None,
) -> CleanupSummary:
    """FL-31 (cada hora y al arrancar): temporales sin uso, errores ya no reintentables y
    fotogramas huérfanos (sin fila). Nunca toca fotogramas de registros borrados lógicamente."""
    flow_token = flow_var.set("FL-31")
    try:
        current = now or datetime.now(UTC)
        async with uow_factory() as uow:
            # Errores con más de TTL: ya no se pueden reintentar (RETRY_FILE_UNAVAILABLE).
            retry_expired = len(
                await uow.classifications.expire_error_tmp_keys(
                    current - timedelta(hours=settings.TMP_UPLOAD_TTL_HOURS)
                )
            )
            await uow.commit()
            live = await uow.classifications.live_tmp_keys()
        async with uow_factory() as uow:  # vistas previas de importación vencidas (HU-10)
            imports_expired = await import_service.expire_previews(uow, current)

        orphan_cutoff = (current - timedelta(minutes=settings.TMP_ORPHAN_MINUTES)).timestamp()
        tmp_root = Path(settings.TMP_UPLOAD_PATH)
        candidates = await asyncio.to_thread(_old_tmp_files, tmp_root, orphan_cutoff)
        tmp_deleted = 0
        for path in candidates:
            if path.name not in live:
                await media_validator.discard(path)
                tmp_deleted += 1

        frame_keys = await storage.list_keys_older_than("evidence", orphan_cutoff)
        async with uow_factory() as uow:
            known = await uow.classifications.known_evidence_keys(frame_keys)
        frames_deleted = 0
        for key in frame_keys:
            if key not in known:  # escrito el fotograma pero falló la fila (consistencia DD-3)
                await storage.delete(key)
                frames_deleted += 1

        summary = CleanupSummary(tmp_deleted, retry_expired, frames_deleted, imports_expired)
        logger.info(
            "Limpieza completada", extra={"event": "storage.cleanup.completed", **vars_of(summary)}
        )
        return summary
    finally:
        flow_var.reset(flow_token)
