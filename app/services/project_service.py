"""Proyectos (HU-07, FL-07): agrupan cámaras propias, con privacidad independiente (CB-20..27)."""

import uuid
from datetime import UTC, datetime
from math import ceil

from sqlalchemy.exc import IntegrityError

from app.core.enums import Visibility
from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.logging import log_step
from app.core.responses import Pagination
from app.db.uow import UnitOfWork
from app.models.project import Project
from app.repositories.projects import ProjectAggregates, ProjectScope, ProjectSort
from app.schemas.project import (
    ProjectCounts,
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    ProjectUpdate,
)
from app.services import camera_station_service
from app.services.policies import Owner

_NOT_FOUND_MSG = "El proyecto no existe o no tienes acceso a él."


def _check_visibility(owner: Owner, visibility: Visibility) -> None:
    if owner.is_anonymous and visibility == Visibility.PUBLIC:
        raise BusinessRuleError("ANON_PUBLIC_NOT_ALLOWED", "Regístrate para publicar proyectos.")


async def _owned_or_error(
    uow: UnitOfWork, owner: Owner, project_id: uuid.UUID, *, for_update: bool = False
) -> Project:
    """Propio → lo devuelve; público ajeno → 403; privado ajeno o inexistente → 404 (S1)."""
    project = await uow.projects.get_owned(project_id, owner, for_update=for_update)
    if project is not None:
        return project
    if await uow.projects.get_visible(project_id, owner) is not None:
        raise ForbiddenError("FORBIDDEN", "Este proyecto no es tuyo.")
    raise NotFoundError("PROJECT_NOT_FOUND", _NOT_FOUND_MSG)


async def _ensure_own_camera(uow: UnitOfWork, owner: Owner, camera_id: uuid.UUID) -> None:
    """CB-23: solo cámaras propias, aunque la ajena sea pública. Privada ajena → 404."""
    if await uow.camera_stations.get_owned(camera_id, owner) is not None:
        return
    if await uow.camera_stations.get_visible(camera_id, owner) is not None:
        raise ForbiddenError(
            "CAMERA_NOT_OWNED", "Solo puedes agregar tus propias cámaras al proyecto."
        )
    raise NotFoundError("CAMERA_NOT_FOUND", "La cámara no existe o no tienes acceso a ella.")


async def _to_reads(
    uow: UnitOfWork, projects: list[Project], viewer: Owner | None
) -> list[ProjectRead]:
    ids = [p.id for p in projects]
    camera_ids = await uow.projects.visible_camera_ids(ids, viewer)
    aggregates = await uow.projects.aggregates(ids, viewer)
    owners = await camera_station_service.owner_views(uow, projects, viewer)
    reads: list[ProjectRead] = []
    for project in projects:
        agg = aggregates.get(project.id, ProjectAggregates())
        reads.append(
            ProjectRead(
                id=project.id,
                name=project.name,
                description=project.description,
                visibility=project.visibility,
                owner=owners[project.id],
                camera_station_ids=camera_ids.get(project.id, []),
                counts=ProjectCounts(
                    camera_stations=agg.camera_stations,
                    classifications=agg.classifications,
                    sightings=agg.sightings,
                    species=agg.species,
                ),
                version=project.version,
                created_at=project.created_at,
                updated_at=project.updated_at,
            )
        )
    return reads


async def _detail(uow: UnitOfWork, project: Project, viewer: Owner | None) -> ProjectDetail:
    read = (await _to_reads(uow, [project], viewer))[0]
    cameras = await uow.camera_stations.list_visible_by_ids(read.camera_station_ids, viewer)
    camera_reads = await camera_station_service.to_reads(uow, cameras, viewer)
    return ProjectDetail(**read.model_dump(), camera_stations=camera_reads)


async def list_projects(
    uow: UnitOfWork,
    viewer: Owner | None,
    *,
    scope: ProjectScope,
    q: str | None,
    page: int,
    page_size: int,
    sort: ProjectSort,
) -> tuple[list[ProjectRead], Pagination]:
    with log_step("project.list"):
        if scope == "mine" and viewer is None:
            raise UnauthorizedError("AUTH_REQUIRED", "Debes iniciar sesión para ver tus proyectos.")
        projects, total = await uow.projects.search(
            viewer, scope=scope, page=page, page_size=page_size, sort=sort, q=q
        )
        size = max(1, min(page_size, 200))
        pagination = Pagination(
            page=page, page_size=size, total=total, total_pages=ceil(total / size) if total else 0
        )
        return await _to_reads(uow, projects, viewer), pagination


async def create_project(uow: UnitOfWork, owner: Owner, data: ProjectCreate) -> ProjectDetail:
    with log_step("project.create"):
        _check_visibility(owner, data.visibility)
        camera_ids = list(dict.fromkeys(data.camera_station_ids))  # sin duplicados, en orden
        for camera_id in camera_ids:
            await _ensure_own_camera(uow, owner, camera_id)
        anon_retain = (
            bool(await uow.settings.get_value("anon_data_retention", True))
            if owner.is_anonymous
            else False
        )
        project = Project(
            name=data.name,
            description=data.description,
            visibility=data.visibility,
            version=1,
        )
        owner.assign_to(project, anon_retain=anon_retain)
        uow.projects.add(project)
        await uow.projects.flush()
        for camera_id in camera_ids:
            uow.projects.add_camera(project.id, camera_id)
        await uow.commit()
        await uow.projects.refresh(project)
        return await _detail(uow, project, owner)


async def get_project(
    uow: UnitOfWork, viewer: Owner | None, project_id: uuid.UUID
) -> ProjectDetail:
    with log_step("project.get"):
        project = await uow.projects.get_visible(project_id, viewer)
        if project is None:
            raise NotFoundError("PROJECT_NOT_FOUND", _NOT_FOUND_MSG)
        return await _detail(uow, project, viewer)


async def update_project(
    uow: UnitOfWork, owner: Owner, project_id: uuid.UUID, if_match: int, data: ProjectUpdate
) -> ProjectDetail:
    with log_step("project.update"):
        project = await _owned_or_error(uow, owner, project_id, for_update=True)
        if project.version != if_match:  # CB-15
            raise ConflictError(
                "CONFLICT_STALE",
                "El proyecto se modificó en otra ventana. Recarga para ver los cambios.",
                context={"expected": if_match, "current": project.version},
            )
        changes = data.model_dump(exclude_unset=True)
        if "name" in changes and changes["name"] is None:
            raise BusinessRuleError("VALIDATION_ERROR", "El nombre del proyecto es obligatorio.")
        if changes.get("visibility") is not None:
            _check_visibility(owner, changes["visibility"])
            project.visibility = changes["visibility"]
        if "name" in changes:
            project.name = changes["name"]
        if "description" in changes:
            project.description = changes["description"]
        project.version += 1
        await uow.commit()
        await uow.projects.refresh(project)
        return await _detail(uow, project, owner)


async def delete_project(uow: UnitOfWork, owner: Owner, project_id: uuid.UUID) -> None:
    """CB-27: borrado lógico del proyecto; cámaras y clasificaciones no se tocan."""
    with log_step("project.delete"):
        existing = await uow.projects.get_owned(project_id, owner, include_deleted=True)
        if existing is not None and existing.is_deleted:
            raise ConflictError("ENTITY_ALREADY_DELETED", "El proyecto ya estaba eliminado.")
        project = await _owned_or_error(uow, owner, project_id, for_update=True)
        project.is_deleted = True
        project.deleted_at = datetime.now(UTC)
        project.deleted_by = owner.user_id or owner.anon_session_id
        await uow.commit()


async def add_camera(
    uow: UnitOfWork, owner: Owner, project_id: uuid.UUID, camera_id: uuid.UUID
) -> ProjectDetail:
    with log_step("project.camera.add"):
        project = await _owned_or_error(uow, owner, project_id)
        await _ensure_own_camera(uow, owner, camera_id)
        conflict = ConflictError("ALREADY_ASSOCIATED", "La cámara ya está en este proyecto.")
        if await uow.projects.is_associated(project_id, camera_id):  # CB-24
            raise conflict
        uow.projects.add_camera(project_id, camera_id)
        try:
            await uow.projects.flush()
        except IntegrityError as exc:  # dos pestañas a la vez: decide la PK
            raise conflict from exc
        await uow.commit()
        return await _detail(uow, project, owner)


async def remove_camera(
    uow: UnitOfWork, owner: Owner, project_id: uuid.UUID, camera_id: uuid.UUID
) -> None:
    """Desasocia sin borrar la cámara."""
    with log_step("project.camera.remove"):
        await _owned_or_error(uow, owner, project_id)
        if not await uow.projects.remove_camera(project_id, camera_id):
            raise NotFoundError("CAMERA_NOT_FOUND", "La cámara no está en este proyecto.")
        await uow.commit()
