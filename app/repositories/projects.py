import uuid

from sqlalchemy import delete, select

from app.models.project import Project, ProjectCameraStation
from app.repositories.base import Repository
from app.services.policies import Owner, owned_by, visible_to


class ProjectRepository(Repository[Project]):
    model = Project

    async def get_owned(self, project_id: uuid.UUID, owner: Owner) -> Project | None:
        stmt = select(Project).where(
            Project.id == project_id, Project.is_deleted.is_(False), owned_by(Project, owner)
        )
        return await self._first(stmt)

    async def get_visible(self, project_id: uuid.UUID, viewer: Owner | None) -> Project | None:
        stmt = select(Project).where(
            Project.id == project_id, Project.is_deleted.is_(False), visible_to(Project, viewer)
        )
        return await self._first(stmt)

    async def list_visible(
        self, viewer: Owner | None, page: int = 1, page_size: int = 50
    ) -> tuple[list[Project], int]:
        stmt = (
            select(Project)
            .where(Project.is_deleted.is_(False), visible_to(Project, viewer))
            .order_by(Project.created_at.desc(), Project.id)
        )
        return await self._page(stmt, page, page_size)

    async def camera_ids(self, project_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(ProjectCameraStation.camera_station_id).where(
            ProjectCameraStation.project_id == project_id
        )
        return list(await self.session.scalars(stmt))

    def add_camera(self, project_id: uuid.UUID, camera_station_id: uuid.UUID) -> None:
        """Asociar: el servicio valida antes que cámara y proyecto son del mismo dueño (CB-23)."""
        self.session.add(
            ProjectCameraStation(project_id=project_id, camera_station_id=camera_station_id)
        )

    async def remove_camera(self, project_id: uuid.UUID, camera_station_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(ProjectCameraStation).where(
                ProjectCameraStation.project_id == project_id,
                ProjectCameraStation.camera_station_id == camera_station_id,
            )
        )
        return bool(getattr(result, "rowcount", 0))
