import uuid

from sqlalchemy import select

from app.core.enums import BatchStatus, ClassificationStatus
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

    async def get_owned(self, batch_id: uuid.UUID, owner: Owner) -> ClassificationBatch | None:
        stmt = select(ClassificationBatch).where(
            ClassificationBatch.id == batch_id,
            ClassificationBatch.is_deleted.is_(False),
            owned_by(ClassificationBatch, owner),
        )
        return await self._first(stmt)

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
