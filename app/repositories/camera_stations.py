import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import (
    and_,
    case,
    delete,
    distinct,
    func,
    insert,
    literal,
    not_,
    or_,
    select,
    update,
)

from app.core.enums import Category, ClassificationStatus, ValidationStatus, Visibility
from app.core.geo import METERS_PER_DEGREE_LAT
from app.models.camera_station import CameraStation
from app.models.classification import Classification
from app.models.project import Project, ProjectCameraStation
from app.models.user import User
from app.repositories.base import Repository
from app.services.policies import Owner, is_mine_sql, owned_by, visible_to

Scope = Literal["mine", "public", "all"]
Sort = Literal["code", "-created_at", "-last_capture_at"]


@dataclass(frozen=True, slots=True)
class CameraAggregates:
    classifications: int = 0
    sightings: int = 0
    species: int = 0
    pending_validation: int = 0
    last_capture_at: datetime | None = None


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def sighting_filter() -> Any:
    """Avistamiento: clasificación terminada de fauna que no se rechazó ni descartó."""
    return and_(
        Classification.is_deleted.is_(False),
        Classification.status == ClassificationStatus.DONE,
        Classification.category == Category.ANIMAL,
        Classification.validation_status.not_in(
            (ValidationStatus.REJECTED, ValidationStatus.DISCARDED_REPEAT)
        ),
    )


class CameraStationRepository(Repository[CameraStation]):
    model = CameraStation

    async def get_owned(
        self,
        camera_id: uuid.UUID,
        owner: Owner,
        *,
        for_update: bool = False,
        include_deleted: bool = False,
    ) -> CameraStation | None:
        stmt = select(CameraStation).where(
            CameraStation.id == camera_id, owned_by(CameraStation, owner)
        )
        if not include_deleted:
            stmt = stmt.where(CameraStation.is_deleted.is_(False))
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self._first(stmt)

    async def get_visible(self, camera_id: uuid.UUID, viewer: Owner | None) -> CameraStation | None:
        """None si no existe, está borrada o es privada de otro: el servicio responde 404."""
        stmt = select(CameraStation).where(
            CameraStation.id == camera_id,
            CameraStation.is_deleted.is_(False),
            visible_to(CameraStation, viewer),
        )
        return await self._first(stmt)

    async def list_visible_by_ids(
        self, camera_ids: list[uuid.UUID], viewer: Owner | None
    ) -> list[CameraStation]:
        if not camera_ids:
            return []
        stmt = select(CameraStation).where(
            CameraStation.id.in_(camera_ids),
            CameraStation.is_deleted.is_(False),
            visible_to(CameraStation, viewer),
        )
        by_id = {c.id: c for c in await self.session.scalars(stmt)}
        return [by_id[cid] for cid in camera_ids if cid in by_id]

    async def codes_by_ids(self, camera_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Solo para cámaras del propio dueño (lotes): sin filtro de visibilidad."""
        if not camera_ids:
            return {}
        stmt = select(CameraStation.id, CameraStation.code).where(CameraStation.id.in_(camera_ids))
        return {cid: code for cid, code in (await self.session.execute(stmt)).all()}

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

    async def list_active_codes_for_user(self, user_id: uuid.UUID) -> list[str]:
        stmt = select(CameraStation.code).where(
            CameraStation.owner_user_id == user_id,
            CameraStation.is_deleted.is_(False),
        )
        return list(await self.session.scalars(stmt))

    async def list_active_for_anon(self, anon_session_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
        stmt = (
            select(CameraStation.id, CameraStation.code)
            .where(
                CameraStation.anon_session_id == anon_session_id,
                CameraStation.is_deleted.is_(False),
            )
            .order_by(CameraStation.created_at, CameraStation.id)
        )
        return [(row[0], row[1]) for row in (await self.session.execute(stmt)).all()]

    async def count_active_for_owner(self, owner: Owner) -> int:
        stmt = select(func.count()).where(
            CameraStation.is_deleted.is_(False), owned_by(CameraStation, owner)
        )
        return int(await self.session.scalar(stmt) or 0)

    async def search(
        self,
        viewer: Owner | None,
        *,
        scope: Scope,
        page: int,
        page_size: int,
        max_page_size: int,
        sort: Sort = "-created_at",
        project_id: uuid.UUID | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        q: str | None = None,
        still_installed: bool | None = None,
    ) -> tuple[list[CameraStation], int]:
        stmt = select(CameraStation).where(CameraStation.is_deleted.is_(False))
        if scope == "mine":
            stmt = stmt.where(is_mine_sql(CameraStation, viewer))
        elif scope == "public":
            stmt = stmt.where(CameraStation.visibility == Visibility.PUBLIC)
        else:
            stmt = stmt.where(visible_to(CameraStation, viewer))
        if bbox is not None:
            min_lng, min_lat, max_lng, max_lat = bbox
            mine = is_mine_sql(CameraStation, viewer)
            # DD-17 / CB-05b: lo ajeno se filtra por la coordenada redondeada que se muestra,
            # para que un bbox diminuto no revele la ubicación exacta.
            lat_r, lng_r = (
                func.round(CameraStation.latitude, 2),
                func.round(CameraStation.longitude, 2),
            )
            stmt = stmt.where(
                or_(
                    and_(
                        mine,
                        CameraStation.latitude.between(min_lat, max_lat),
                        CameraStation.longitude.between(min_lng, max_lng),
                    ),
                    and_(
                        not_(mine),
                        lat_r.between(min_lat, max_lat),
                        lng_r.between(min_lng, max_lng),
                    ),
                )
            )
        if project_id is not None:
            stmt = stmt.where(
                CameraStation.id.in_(
                    select(ProjectCameraStation.camera_station_id).where(
                        ProjectCameraStation.project_id == project_id
                    )
                )
            )
        if q:
            pattern = f"%{escape_like(q.strip())}%"
            stmt = stmt.where(
                or_(
                    CameraStation.code.ilike(pattern, escape="\\"),
                    CameraStation.name.ilike(pattern, escape="\\"),
                )
            )
        if still_installed is not None:
            stmt = stmt.where(CameraStation.still_installed.is_(still_installed))

        if sort == "code":
            stmt = stmt.order_by(func.lower(CameraStation.code), CameraStation.id)
        elif sort == "-last_capture_at":
            last = (
                select(
                    Classification.camera_station_id.label("cid"),
                    func.max(Classification.captured_at).label("last_capture_at"),
                )
                .where(Classification.is_deleted.is_(False))
                .group_by(Classification.camera_station_id)
                .subquery()
            )
            stmt = stmt.outerjoin(last, last.c.cid == CameraStation.id).order_by(
                last.c.last_capture_at.desc().nulls_last(), CameraStation.id
            )
        else:
            stmt = stmt.order_by(CameraStation.created_at.desc(), CameraStation.id)
        return await self._page(stmt, page, page_size, max_page_size)

    async def aggregates(self, camera_ids: list[uuid.UUID]) -> dict[uuid.UUID, CameraAggregates]:
        """Conteos de todas las cámaras pedidas en una sola consulta (sin N+1)."""
        if not camera_ids:
            return {}
        active = Classification.is_deleted.is_(False)
        species_name = func.coalesce(
            Classification.corrected_scientific_name, Classification.scientific_name
        )
        rank = func.coalesce(Classification.corrected_rank, Classification.rank)
        stmt = (
            select(
                Classification.camera_station_id,
                func.count(case((active, 1))),
                func.count(case((sighting_filter(), 1))),
                func.count(
                    distinct(case((and_(sighting_filter(), rank == "species"), species_name)))
                ),
                func.count(
                    case(
                        (
                            and_(
                                active,
                                Classification.status == ClassificationStatus.DONE,
                                Classification.validation_status == ValidationStatus.UNVALIDATED,
                            ),
                            1,
                        )
                    )
                ),
                func.max(case((active, Classification.captured_at))),
            )
            .where(Classification.camera_station_id.in_(camera_ids))
            .group_by(Classification.camera_station_id)
        )
        result: dict[uuid.UUID, CameraAggregates] = {}
        for cid, total, sightings, species, pending, last in await self.session.execute(stmt):
            result[cid] = CameraAggregates(
                int(total or 0), int(sightings or 0), int(species or 0), int(pending or 0), last
            )
        return result

    async def visible_project_ids(
        self, camera_ids: list[uuid.UUID], viewer: Owner | None
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        if not camera_ids:
            return {}
        stmt = (
            select(ProjectCameraStation.camera_station_id, ProjectCameraStation.project_id)
            .join(Project, Project.id == ProjectCameraStation.project_id)
            .where(
                ProjectCameraStation.camera_station_id.in_(camera_ids),
                Project.is_deleted.is_(False),
                visible_to(Project, viewer),
            )
            .order_by(ProjectCameraStation.created_at)
        )
        result: dict[uuid.UUID, list[uuid.UUID]] = {}
        for cid, pid in (await self.session.execute(stmt)).all():
            result.setdefault(cid, []).append(pid)
        return result

    async def user_profiles(
        self, user_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[str, str | None]]:
        if not user_ids:
            return {}
        stmt = select(User.id, User.full_name, User.institution).where(User.id.in_(user_ids))
        return {uid: (name, inst) for uid, name, inst in (await self.session.execute(stmt)).all()}

    async def near_candidates(
        self,
        lat: float,
        lng: float,
        radius_m: float,
        viewer: Owner,
        exclude_id: uuid.UUID | None,
    ) -> list[CameraStation]:
        """Prefiltro por caja (índice-friendly); la distancia exacta se calcula en el servicio."""
        d_lat = radius_m / METERS_PER_DEGREE_LAT
        d_lng = radius_m / (METERS_PER_DEGREE_LAT * max(math.cos(math.radians(lat)), 0.01))
        stmt = select(CameraStation).where(
            CameraStation.is_deleted.is_(False),
            or_(is_mine_sql(CameraStation, viewer), CameraStation.visibility == Visibility.PUBLIC),
            CameraStation.latitude.between(lat - d_lat, lat + d_lat),
            CameraStation.longitude.between(lng - d_lng, lng + d_lng),
        )
        if exclude_id is not None:
            stmt = stmt.where(CameraStation.id != exclude_id)
        return list(await self.session.scalars(stmt))

    async def copy_projects(self, from_camera_id: uuid.UUID, to_camera_id: uuid.UUID) -> None:
        source = select(
            ProjectCameraStation.project_id, literal(to_camera_id, CameraStation.id.type)
        ).where(ProjectCameraStation.camera_station_id == from_camera_id)
        await self.session.execute(
            insert(ProjectCameraStation).from_select(["project_id", "camera_station_id"], source)
        )

    async def cascade_soft_delete(
        self, camera_id: uuid.UUID, now: datetime, deleted_by: uuid.UUID | None
    ) -> None:
        """CB-21: cancela lo que está en cola, borra lógicamente las clasificaciones y quita la
        cámara de los proyectos. La cámara la marca el servicio."""
        await self.session.execute(
            update(Classification)
            .where(
                Classification.camera_station_id == camera_id,
                Classification.is_deleted.is_(False),
                Classification.status == ClassificationStatus.QUEUED,
            )
            .values(status=ClassificationStatus.CANCELLED, error_code="CAMERA_DELETED")
        )
        await self.session.execute(
            update(Classification)
            .where(
                Classification.camera_station_id == camera_id, Classification.is_deleted.is_(False)
            )
            .values(is_deleted=True, deleted_at=now, deleted_by=deleted_by)
        )
        await self.session.execute(
            delete(ProjectCameraStation).where(ProjectCameraStation.camera_station_id == camera_id)
        )
