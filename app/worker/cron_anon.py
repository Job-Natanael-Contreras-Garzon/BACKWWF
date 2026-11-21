from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import settings
from app.core.logging import flow_var, logger
from app.db.uow import UnitOfWork
from app.integrations.storage.base import StorageBackend
from app.integrations.storage.local import LocalStorage
from app.models.admin import AnonPurgeRun

# shortcut: scheduled via manual CLI until HU-08 introduces arq hourly cron;
# never run background loops inside API workers (--workers 2).


@dataclass(frozen=True, slots=True)
class AnonPurgeSummary:
    sessions: int
    classifications: int
    classification_batches: int
    camera_stations: int
    projects: int
    frames: int
    retained: int
    storage_failures: int


async def _delete_frames_post_commit(
    storage: StorageBackend, evidence_keys: list[str]
) -> tuple[int, int]:
    frames_deleted = 0
    storage_failures = 0
    for key in evidence_keys:
        try:
            existed = await storage.exists(key)
            await storage.delete(key)
            if existed:
                frames_deleted += 1
        except FileNotFoundError:
            continue
        except Exception as exc:
            storage_failures += 1
            logger.warning(
                "No se pudo borrar fotograma en purga FL-30",
                extra={
                    "event": "anon.purge.frame_delete_failed",
                    "key": key,
                    "error": type(exc).__name__,
                },
            )
    return frames_deleted, storage_failures


async def purge_anon_sessions(
    uow_factory: Callable[[], UnitOfWork] = UnitOfWork,
    storage: StorageBackend | None = None,
    now: datetime | None = None,
) -> AnonPurgeSummary:
    """FL-30: expira sesiones vencidas, purga anon_retain=false y borra sus fotogramas."""
    flow_token = flow_var.set("FL-30")
    try:
        current_time = now or datetime.now(UTC)
        store: StorageBackend = storage or LocalStorage(settings.STORAGE_LOCAL_PATH)

        async with uow_factory() as uow:
            while True:
                batch = await uow.anon_sessions.list_expirable(current_time, limit=500)
                if not batch:
                    break
                await uow.anon_sessions.mark_expired([s.id for s in batch])
                if len(batch) < 500:
                    break

            evidence_keys = await uow.anon_sessions.list_expired_evidence_keys_to_purge()
            retained = await uow.anon_sessions.count_retained_in_expired()
            (
                purged_sessions,
                cls_del,
                batch_del,
                proj_del,
                cam_del,
            ) = await uow.anon_sessions.purge_non_retained_in_expired()
            await uow.commit()

        frames_deleted, storage_failures = await _delete_frames_post_commit(store, evidence_keys)

        if cls_del + batch_del + proj_del + cam_del > 0:
            async with uow_factory() as uow:
                uow.purge_runs.add(
                    AnonPurgeRun(
                        run_at=current_time,
                        sessions=purged_sessions,
                        classifications=cls_del,
                        camera_stations=cam_del,
                        projects=proj_del,
                        frames=frames_deleted,
                    )
                )
                await uow.commit()

        logger.info(
            "Purga de sesiones anónimas completada",
            extra={
                "event": "anon.purge.completed",
                "retained": retained,
                "purged": {
                    "sessions": purged_sessions,
                    "classifications": cls_del,
                    "classification_batches": batch_del,
                    "camera_stations": cam_del,
                    "projects": proj_del,
                    "frames": frames_deleted,
                },
                "storage_failures": storage_failures,
            },
        )
        return AnonPurgeSummary(
            sessions=purged_sessions,
            classifications=cls_del,
            classification_batches=batch_del,
            camera_stations=cam_del,
            projects=proj_del,
            frames=frames_deleted,
            retained=retained,
            storage_failures=storage_failures,
        )
    finally:
        flow_var.reset(flow_token)
