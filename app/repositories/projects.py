import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import and_, case, delete, distinct, func, select

from app.core.enums import Visibility
from app.models.camera_station import CameraStation
from app.models.classification import Classification
from app.models.project import Project, ProjectCameraStation
from app.repositories.base import Repository
from app.repositories.camera_stations import escape_like, sighting_filter
from app.services.policies import Owner, is_mine_sql, owned_by, visible_to

ProjectScope = Literal["mine", "public", "all"]
ProjectSort = Literal["name", "-created_at"]


@dataclass(frozen=True, slots=True)
class ProjectAggregates:
    camera_stations: int = 0
    classifications: int = 0
    sightings: int = 0
    species: int = 0


class ProjectRepository(Repository[Project]):
    model = Project

    async def get_owned(
        self,
        project_id: uuid.UUID,
        owner: Owner,
        *,
        for_update: bool = False,
        include_deleted: bool = False,
    ) -> Project | None:
        stmt = select(Project).where(Project.id == project_id, owned_by(Project, owner))
        if not include_deleted:
            stmt = stmt.where(Project.is_deleted.is_(False))
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
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

    async def is_associated(self, project_id: uuid.UUID, camera_station_id: uuid.UUID) -> bool:
        stmt = select(ProjectCameraStation.project_id).where(
            ProjectCameraStation.project_id == project_id,
            ProjectCameraStation.camera_station_id == camera_station_id,
        )
        return (await self.session.scalar(stmt)) is not None

    async def search(
        self,
        viewer: Owner | None,
        *,
        scope: ProjectScope,
        page: int,
        page_size: int,
        sort: ProjectSort = "-created_at",
        q: str | None = None,
    ) -> tuple[list[Project], int]:
        stmt = select(Project).where(Project.is_deleted.is_(False))
        if scope == "mine":
            stmt = stmt.where(is_mine_sql(Project, viewer))
        elif scope == "public":
            stmt = stmt.where(Project.visibility == Visibility.PUBLIC)
        else:
            stmt = stmt.where(visible_to(Project, viewer))
        if q:
            stmt = stmt.where(Project.name.ilike(f"%{escape_like(q.strip())}%", escape="\\"))
        if sort == "name":
            stmt = stmt.order_by(func.lower(Project.name), Project.id)
        else:
            stmt = stmt.order_by(Project.created_at.desc(), Project.id)
        return await self._page(stmt, page, page_size)

    async def visible_camera_ids(
        self, project_ids: list[uuid.UUID], viewer: Owner | None
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        """CB-20: en un proyecto público, las cámaras privadas ajenas no aparecen."""
        if not project_ids:
            return {}
        stmt = (
            select(ProjectCameraStation.project_id, CameraStation.id)
            .join(CameraStation, CameraStation.id == ProjectCameraStation.camera_station_id)
            .where(
                ProjectCameraStation.project_id.in_(project_ids),
                CameraStation.is_deleted.is_(False),
                visible_to(CameraStation, viewer),
            )
            .order_by(ProjectCameraStation.created_at, CameraStation.id)
        )
        result: dict[uuid.UUID, list[uuid.UUID]] = {}
        for pid, cid in (await self.session.execute(stmt)).all():
            result.setdefault(pid, []).append(cid)
        return result

    async def aggregates(
        self, project_ids: list[uuid.UUID], viewer: Owner | None
    ) -> dict[uuid.UUID, ProjectAggregates]:
        """Conteos por proyecto sobre las cámaras que el viewer puede ver (una consulta)."""
        if not project_ids:
            return {}
        active = Classification.is_deleted.is_(False)
        species_name = func.coalesce(
            Classification.corrected_scientific_name, Classification.scientific_name
        )
        rank = func.coalesce(Classification.corrected_rank, Classification.rank)
        stmt = (
            select(
                ProjectCameraStation.project_id,
                func.count(distinct(CameraStation.id)),
                func.count(case((active, Classification.id))),
                func.count(case((sighting_filter(), Classification.id))),
                func.count(
                    distinct(case((and_(sighting_filter(), rank == "species"), species_name)))
                ),
            )
            .join(CameraStation, CameraStation.id == ProjectCameraStation.camera_station_id)
            .outerjoin(Classification, Classification.camera_station_id == CameraStation.id)
            .where(
                ProjectCameraStation.project_id.in_(project_ids),
                CameraStation.is_deleted.is_(False),
                visible_to(CameraStation, viewer),
            )
            .group_by(ProjectCameraStation.project_id)
        )
        result: dict[uuid.UUID, ProjectAggregates] = {}
        for pid, cams, total, sightings, species in await self.session.execute(stmt):
            result[pid] = ProjectAggregates(
                int(cams or 0), int(total or 0), int(sightings or 0), int(species or 0)
            )
        return result
