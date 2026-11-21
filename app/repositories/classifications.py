import uuid
from datetime import datetime

from sqlalchemy import Select, func, or_, select, update

from app.core.enums import BatchStatus, ClassificationSource, ClassificationStatus
from app.models.camera_station import CameraStation
from app.models.classification import Classification, ClassificationBatch
from app.repositories.base import Repository
from app.services.policies import Owner, owned_by, visible_to

# Estados que ocupan el índice único CB-50: un archivo así ya está (o estará) contado.
ACTIVE_STATUSES = (
    ClassificationStatus.QUEUED,
    ClassificationStatus.PROCESSING,
    ClassificationStatus.DONE,
)


class ClassificationBatchRepository(Repository[ClassificationBatch]):
    model = ClassificationBatch

    async def get_owned(
        self, batch_id: uuid.UUID, owner: Owner, *, for_update: bool = False
    ) -> ClassificationBatch | None:
        stmt = select(ClassificationBatch).where(
            ClassificationBatch.id == batch_id,
            ClassificationBatch.is_deleted.is_(False),
            owned_by(ClassificationBatch, owner),
        )
        if for_update:  # serializa las subidas paralelas del mismo lote (contadores, client_index)
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self._first(stmt)

    async def list_active_or_recent(
        self, owner: Owner, closed_since: datetime
    ) -> list[ClassificationBatch]:
        """§7.5: abiertos o procesando, más los cerrados hace poco (para mostrar "Listo")."""
        stmt = (
            select(ClassificationBatch)
            .where(
                ClassificationBatch.is_deleted.is_(False),
                owned_by(ClassificationBatch, owner),
                or_(
                    ClassificationBatch.status.in_((BatchStatus.OPEN, BatchStatus.PROCESSING)),
                    ClassificationBatch.closed_at >= closed_since,
                ),
            )
            .order_by(ClassificationBatch.created_at.desc(), ClassificationBatch.id)
        )
        return list(await self.session.scalars(stmt))

    async def open_idle_since(self, cutoff: datetime) -> list[ClassificationBatch]:
        """CB-32: lotes abiertos sin archivos nuevos desde ``cutoff`` (se cierran incompletos)."""
        stmt = select(ClassificationBatch).where(
            ClassificationBatch.is_deleted.is_(False),
            ClassificationBatch.status == BatchStatus.OPEN,
            ClassificationBatch.updated_at < cutoff,
        )
        return list(await self.session.scalars(stmt))

    async def processing_batches(self) -> list[ClassificationBatch]:
        stmt = select(ClassificationBatch).where(
            ClassificationBatch.is_deleted.is_(False),
            ClassificationBatch.status == BatchStatus.PROCESSING,
        )
        return list(await self.session.scalars(stmt))

    async def list_history(
        self,
        owner: Owner,
        *,
        page: int,
        page_size: int,
        camera_station_id: uuid.UUID | None = None,
        status: BatchStatus | None = None,
    ) -> tuple[list[ClassificationBatch], int]:
        stmt: Select[tuple[ClassificationBatch]] = select(ClassificationBatch).where(
            ClassificationBatch.is_deleted.is_(False), owned_by(ClassificationBatch, owner)
        )
        if camera_station_id is not None:
            stmt = stmt.where(ClassificationBatch.camera_station_id == camera_station_id)
        if status is not None:
            stmt = stmt.where(ClassificationBatch.status == status)
        stmt = stmt.order_by(ClassificationBatch.created_at.desc(), ClassificationBatch.id)
        return await self._page(stmt, page, page_size)

    async def list_active(self, owner: Owner) -> list[ClassificationBatch]:
        stmt = (
            select(ClassificationBatch)
            .where(
                ClassificationBatch.is_deleted.is_(False),
                owned_by(ClassificationBatch, owner),
                ClassificationBatch.status.in_((BatchStatus.OPEN, BatchStatus.PROCESSING)),
            )
            .order_by(ClassificationBatch.created_at.desc())
        )
        return list(await self.session.scalars(stmt))


class ClassificationRepository(Repository[Classification]):
    model = Classification

    async def get_owned(self, classification_id: uuid.UUID, owner: Owner) -> Classification | None:
        stmt = select(Classification).where(
            Classification.id == classification_id,
            Classification.is_deleted.is_(False),
            owned_by(Classification, owner),
        )
        return await self._first(stmt)

    async def get_visible(
        self, classification_id: uuid.UUID, viewer: Owner | None
    ) -> Classification | None:
        """Una clasificación se ve si su cámara se ve (dueño o cámara pública)."""
        stmt = (
            select(Classification)
            .join(CameraStation, CameraStation.id == Classification.camera_station_id)
            .where(
                Classification.id == classification_id,
                Classification.is_deleted.is_(False),
                CameraStation.is_deleted.is_(False),
                visible_to(CameraStation, viewer),
            )
        )
        return await self._first(stmt)

    async def for_stats(
        self,
        camera_ids: list[uuid.UUID],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        source: ClassificationSource | None = None,
    ) -> list[Classification]:
        """Filas que cuentan en stats y reportes: terminadas (``done``/``error``), no borradas,
        de las cámaras dadas (el servicio ya filtró por visibilidad). ``from``/``to`` sobre
        ``captured_at`` (§10.1)."""
        if not camera_ids:
            return []
        stmt = select(Classification).where(
            Classification.camera_station_id.in_(camera_ids),
            Classification.is_deleted.is_(False),
            Classification.status.in_((ClassificationStatus.DONE, ClassificationStatus.ERROR)),
        )
        if start is not None:
            stmt = stmt.where(Classification.captured_at >= start)
        if end is not None:
            stmt = stmt.where(Classification.captured_at < end)
        if source is not None:
            stmt = stmt.where(Classification.source == source)
        return list(await self.session.scalars(stmt.order_by(Classification.captured_at)))

    async def find_active_by_sha256(
        self, camera_station_id: uuid.UUID, file_sha256: str
    ) -> Classification | None:
        """CB-50: el mismo archivo ya está en esta cámara (en cola, procesando o listo)."""
        stmt = select(Classification).where(
            Classification.camera_station_id == camera_station_id,
            Classification.file_sha256 == file_sha256,
            Classification.is_deleted.is_(False),
            Classification.status.in_(ACTIVE_STATUSES),
        )
        return await self._first(stmt)

    async def find_sha256_in_other_cameras(
        self, owner: Owner, file_sha256: str, camera_station_id: uuid.UUID
    ) -> Classification | None:
        """CB-51: el mismo archivo del mismo dueño ya está en otra cámara."""
        stmt = (
            select(Classification)
            .where(
                Classification.file_sha256 == file_sha256,
                Classification.camera_station_id != camera_station_id,
                Classification.is_deleted.is_(False),
                Classification.status.in_(ACTIVE_STATUSES),
                owned_by(Classification, owner),
            )
            .limit(1)
        )
        return await self._first(stmt)

    async def items_of_batches(self, batch_ids: list[uuid.UUID]) -> list[Classification]:
        if not batch_ids:
            return []
        stmt = (
            select(Classification)
            .where(Classification.batch_id.in_(batch_ids), Classification.is_deleted.is_(False))
            .order_by(Classification.client_index, Classification.created_at)
        )
        return list(await self.session.scalars(stmt))

    async def status_counts(
        self, batch_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[ClassificationStatus, int]]:
        if not batch_ids:
            return {}
        stmt = (
            select(Classification.batch_id, Classification.status, func.count())
            .where(Classification.batch_id.in_(batch_ids), Classification.is_deleted.is_(False))
            .group_by(Classification.batch_id, Classification.status)
        )
        result: dict[uuid.UUID, dict[ClassificationStatus, int]] = {}
        for batch_id, status, count in (await self.session.execute(stmt)).all():
            result.setdefault(batch_id, {})[status] = int(count)
        return result

    async def get_by_client_index(
        self, batch_id: uuid.UUID, client_index: int
    ) -> Classification | None:
        stmt = select(Classification).where(
            Classification.batch_id == batch_id,
            Classification.client_index == client_index,
            Classification.is_deleted.is_(False),
        )
        return await self._first(stmt)

    async def count_pending(self, owner: Owner) -> int:
        """CB-34: en cola o procesando, de este dueño."""
        stmt = select(func.count()).where(
            Classification.is_deleted.is_(False),
            owned_by(Classification, owner),
            Classification.status.in_(
                (ClassificationStatus.QUEUED, ClassificationStatus.PROCESSING)
            ),
        )
        return int(await self.session.scalar(stmt) or 0)

    async def count_active_files(self, owner: Owner) -> int:
        """Límite anónimo (ANON_MAX_FILES): archivos que ocupan cupo (cola, proceso o listos)."""
        stmt = select(func.count()).where(
            Classification.is_deleted.is_(False),
            owned_by(Classification, owner),
            Classification.status.in_(ACTIVE_STATUSES),
        )
        return int(await self.session.scalar(stmt) or 0)

    async def count_queued_global(self) -> int:
        stmt = select(func.count()).where(
            Classification.is_deleted.is_(False),
            Classification.status == ClassificationStatus.QUEUED,
        )
        return int(await self.session.scalar(stmt) or 0)

    async def items_of_batch(
        self, batch_id: uuid.UUID, *, since: datetime | None = None
    ) -> list[Classification]:
        stmt = select(Classification).where(
            Classification.batch_id == batch_id, Classification.is_deleted.is_(False)
        )
        if since is not None:
            stmt = stmt.where(Classification.updated_at > since)
        return list(await self.session.scalars(stmt.order_by(Classification.client_index)))

    async def stale_processing(self, heartbeat_before: datetime) -> list[Classification]:
        """CB-38: en proceso sin latido (worker caído o reiniciado)."""
        stmt = (
            select(Classification)
            .where(
                Classification.is_deleted.is_(False),
                Classification.status == ClassificationStatus.PROCESSING,
                or_(
                    Classification.heartbeat_at.is_(None),
                    Classification.heartbeat_at < heartbeat_before,
                ),
            )
            .with_for_update(skip_locked=True)
        )
        return list(await self.session.scalars(stmt))

    async def queued_before(self, queued_before: datetime) -> list[Classification]:
        """CB-39: en cola desde hace más de ``TMP_UPLOAD_TTL_HOURS``."""
        stmt = (
            select(Classification)
            .where(
                Classification.is_deleted.is_(False),
                Classification.status == ClassificationStatus.QUEUED,
                Classification.queued_at < queued_before,
            )
            .with_for_update(skip_locked=True)
        )
        return list(await self.session.scalars(stmt))

    async def queued_ids(self, limit: int) -> list[uuid.UUID]:
        stmt = (
            select(Classification.id)
            .where(
                Classification.is_deleted.is_(False),
                Classification.status == ClassificationStatus.QUEUED,
            )
            .order_by(Classification.queued_at)
            .limit(limit)
        )
        return list(await self.session.scalars(stmt))

    async def live_tmp_keys(self) -> set[str]:
        """Temporales que todavía sirven: en cola, procesando o en error (para reintentar)."""
        stmt = select(Classification.tmp_key).where(
            Classification.is_deleted.is_(False),
            Classification.tmp_key.is_not(None),
            Classification.status.in_(
                (
                    ClassificationStatus.QUEUED,
                    ClassificationStatus.PROCESSING,
                    ClassificationStatus.ERROR,
                )
            ),
        )
        return {key for key in await self.session.scalars(stmt) if key}

    async def expire_error_tmp_keys(self, finished_before: datetime) -> list[str]:
        """Errores viejos ya no se reintentan: suelta su temporal (RETRY_FILE_UNAVAILABLE)."""
        result = await self.session.execute(
            update(Classification)
            .where(
                Classification.status.in_(
                    (ClassificationStatus.ERROR, ClassificationStatus.CANCELLED)
                ),
                Classification.tmp_key.is_not(None),
                Classification.updated_at < finished_before,
            )
            .values(tmp_key=None)
            .returning(Classification.id)
        )
        return [str(row[0]) for row in result.all()]

    async def known_evidence_keys(self, keys: list[str]) -> set[str]:
        """Fotogramas con fila (incluidas las borradas lógicamente: esas no se tocan, FL-31)."""
        if not keys:
            return set()
        stmt = select(Classification.evidence_key).where(Classification.evidence_key.in_(keys))
        return {key for key in await self.session.scalars(stmt) if key}
