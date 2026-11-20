import uuid

from sqlalchemy import func, select

from app.models.camera_station import CameraStation
from app.repositories.base import Repository
from app.services.policies import Owner, owned_by, visible_to


class CameraStationRepository(Repository[CameraStation]):
    model = CameraStation

    async def get_owned(self, camera_id: uuid.UUID, owner: Owner) -> CameraStation | None:
        stmt = select(CameraStation).where(
            CameraStation.id == camera_id,
            CameraStation.is_deleted.is_(False),
            owned_by(CameraStation, owner),
        )
        return await self._first(stmt)

    async def get_visible(self, camera_id: uuid.UUID, viewer: Owner | None) -> CameraStation | None:
        """None si no existe, está borrada o es privada de otro: el servicio responde 404."""
        stmt = select(CameraStation).where(
            CameraStation.id == camera_id,
            CameraStation.is_deleted.is_(False),
            visible_to(CameraStation, viewer),
        )
        return await self._first(stmt)

    async def list_visible(
        self, viewer: Owner | None, page: int = 1, page_size: int = 50
    ) -> tuple[list[CameraStation], int]:
        stmt = (
            select(CameraStation)
            .where(CameraStation.is_deleted.is_(False), visible_to(CameraStation, viewer))
            .order_by(CameraStation.created_at.desc(), CameraStation.id)
        )
        return await self._page(stmt, page, page_size)

    async def find_active_by_code(self, owner: Owner, code: str) -> CameraStation | None:
        """Mismo criterio que el índice único CB-13 (sin mayúsculas, solo no borradas)."""
        stmt = select(CameraStation).where(
            CameraStation.is_deleted.is_(False),
            owned_by(CameraStation, owner),
            func.lower(CameraStation.code) == code.strip().lower(),
        )
        return await self._first(stmt)
