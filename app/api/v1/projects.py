from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_anon_session_id,
    get_current_user,
    get_current_user_optional,
    get_db,
    get_project_service,
)
from app.interfaces.project_service import IProjectService
from app.models.user import User
from app.schemas.project import (
    ProjectAddCollaborators,
    ProjectCreate,
    ProjectUpdate,
)
from app.schemas.project_station import AssociateStationSchema
from app.schemas.response_wrapper import StandardResponse

router = APIRouter(prefix="/projects", tags=["Projects"])


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: POST /api/v1/projects/
# Happy Path: Recibe payload de creación; si el usuario está autenticado asigna
# user_id; si es anónimo asigna anon_session_id (generado o del header);
# persiste en BD y retorna HTTP 201 Created con StandardResponse.
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear proyecto de investigación",
)
async def create_project(
    project_in: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    anon_session_id: UUID = Depends(get_anon_session_id),
    service: IProjectService = Depends(get_project_service),
):
    """
    **Physical Path**: `POST /api/v1/projects/`

    **Happy Path**:
    1. Recibe payload del proyecto (`title`, `description`, `objectives`, `status`, etc.).
    2. Identifica si la solicitud proviene de un usuario autenticado (asigna `user_id`) o anónimo (asigna `anon_session_id`).
    3. Persiste la entidad `Project` con `is_deleted = False`.
    4. Retorna HTTP 201 Created con `{status: "success", data: <proyecto>, message: "Proyecto creado exitosamente"}`.
    """
    project = await service.create_project(
        db=db,
        project_in=project_in,
        current_user=current_user,
        anon_session_id=anon_session_id,
    )
    return StandardResponse(
        status="success",
        data=project,
        message="Proyecto creado exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/projects/
# Happy Path: Consulta todos los proyectos activos (is_deleted == False) paginados.
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar proyectos activos",
)
async def get_projects(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    service: IProjectService = Depends(get_project_service),
):
    """
    **Physical Path**: `GET /api/v1/projects/`

    **Happy Path**:
    1. Recibe parámetros de paginación opcionales `skip` y `limit`.
    2. Consulta en BD los proyectos donde `is_deleted == False`.
    3. Retorna HTTP 200 OK con la lista estructurada de proyectos.
    """
    projects = await service.list_projects(db=db, skip=skip, limit=limit)
    return StandardResponse(
        status="success",
        data=projects,
        message="Proyectos obtenidos exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/projects/{project_id}
# Happy Path: Consulta el proyecto por UUID filtrando is_deleted == False,
# incluyendo el listado de estaciones de cámara activas asociadas (N:M).
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/{project_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener detalle de proyecto",
)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: IProjectService = Depends(get_project_service),
):
    """
    **Physical Path**: `GET /api/v1/projects/{project_id}`

    **Happy Path**:
    1. Recibe el `project_id` (UUID).
    2. Busca el proyecto activo (`is_deleted == False`) y sus estaciones asociadas activas.
    3. Retorna HTTP 200 OK con el detalle completo del proyecto.
    """
    project = await service.get_project(db=db, project_id=project_id)
    return StandardResponse(
        status="success",
        data=project,
        message="Proyecto obtenido exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: PATCH /api/v1/projects/{project_id}
# Happy Path: Valida que el usuario autenticado sea el dueño (user_id == current_user.id),
# actualiza los campos enviados y retorna el proyecto actualizado.
# ─────────────────────────────────────────────────────────────────────────────
@router.patch(
    "/{project_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Actualizar proyecto",
)
async def update_project(
    project_id: UUID,
    project_in: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: IProjectService = Depends(get_project_service),
):
    """
    **Physical Path**: `PATCH /api/v1/projects/{project_id}`

    **Happy Path**:
    1. Valida el token de autenticación.
    2. Verifica que el usuario sea el dueño del proyecto.
    3. Actualiza parcialmente los campos y actualiza `updated_at`.
    4. Retorna HTTP 200 OK con el proyecto modificado.
    """
    project = await service.update_project(
        db=db,
        project_id=project_id,
        project_in=project_in,
        current_user=current_user,
    )
    return StandardResponse(
        status="success",
        data=project,
        message="Proyecto actualizado exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: DELETE /api/v1/projects/{project_id}
# Happy Path: Valida que el proyecto tenga dueño y el usuario sea el propietario;
# aplica Soft Delete marcando is_deleted=True y deleted_at=now(); no borra
# registros físicos ni estaciones asociadas.
# ─────────────────────────────────────────────────────────────────────────────
@router.delete(
    "/{project_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Eliminar proyecto (Soft Delete)",
)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: IProjectService = Depends(get_project_service),
):
    """
    **Physical Path**: `DELETE /api/v1/projects/{project_id}`

    **Happy Path**:
    1. Valida token JWT obligatorio.
    2. Si el proyecto es anónimo (`user_id is Null`), lanza HTTP 403 Forbidden.
    3. Si el usuario no es el propietario, lanza HTTP 403 Forbidden.
    4. Ejecuta Soft Delete (`is_deleted = True`, `deleted_at = now()`).
    5. Retorna HTTP 200 OK confirmando la eliminación lógica.
    """
    await service.delete_project(
        db=db, project_id=project_id, current_user=current_user
    )
    return StandardResponse(
        status="success",
        data=None,
        message="Proyecto eliminado exitosamente (Soft Delete)",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: POST /api/v1/projects/{project_id}/stations
# Happy Path: Asocia una estación existente al proyecto a través de la tabla
# intermedia project_stations (N:M de forma idempotente).
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/{project_id}/stations",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Asociar estación a proyecto (N:M)",
)
async def associate_station(
    project_id: UUID,
    data: AssociateStationSchema,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    service: IProjectService = Depends(get_project_service),
):
    """
    **Physical Path**: `POST /api/v1/projects/{project_id}/stations`

    **Happy Path**:
    1. Valida existencia de proyecto activo y estación activa.
    2. Crea o reactiva el vínculo en la tabla `project_stations`.
    3. Retorna HTTP 200 OK con los identificadores asociados.
    """
    res = await service.associate_station(
        db=db,
        project_id=project_id,
        station_id=data.station_id,
        current_user=current_user,
    )
    return StandardResponse(
        status="success",
        data=res,
        message="Estación asociada al proyecto exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: DELETE /api/v1/projects/{project_id}/stations/{station_id}
# Happy Path: Desasocia la estación del proyecto aplicando Soft Delete a la
# relación en project_stations (la estación sigue existiendo).
# ─────────────────────────────────────────────────────────────────────────────
@router.delete(
    "/{project_id}/stations/{station_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Desasociar estación de proyecto (N:M)",
)
async def disassociate_station(
    project_id: UUID,
    station_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    service: IProjectService = Depends(get_project_service),
):
    """
    **Physical Path**: `DELETE /api/v1/projects/{project_id}/stations/{station_id}`

    **Happy Path**:
    1. Localiza el vínculo activo en `project_stations`.
    2. Aplica Soft Delete a la relación (`is_deleted = True`).
    3. Retorna HTTP 200 OK confirmando la desasociación.
    """
    await service.disassociate_station(
        db=db,
        project_id=project_id,
        station_id=station_id,
        current_user=current_user,
    )
    return StandardResponse(
        status="success",
        data=None,
        message="Estación desasociada del proyecto exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/projects/{project_id}/summary
# Happy Path: Agrega las detecciones taxonómicas de todas las estaciones
# vinculadas activas y retorna el desglose estadístico.
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/{project_id}/summary",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Resumen estadístico agregado del proyecto",
)
async def get_project_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: IProjectService = Depends(get_project_service),
):
    """
    **Physical Path**: `GET /api/v1/projects/{project_id}/summary`

    **Happy Path**:
    1. Obtiene todas las estaciones asociadas activas del proyecto.
    2. Agrega las detecciones de especies, conteo total y distribución taxonómica.
    3. Retorna HTTP 200 OK con el resumen consolidado.
    """
    summary = await service.get_project_summary(db=db, project_id=project_id)
    return StandardResponse(
        status="success",
        data=summary,
        message="Resumen del proyecto obtenido exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: POST /api/v1/projects/{project_id}/collaborators
# Happy Path: El propietario añade una lista de colaboradores al proyecto.
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/{project_id}/collaborators",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Añadir colaboradores a un proyecto",
)
async def add_collaborators(
    project_id: UUID,
    collaborators_in: ProjectAddCollaborators,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: IProjectService = Depends(get_project_service),
):
    """
    **Physical Path**: `POST /api/v1/projects/{project_id}/collaborators`

    **Happy Path**:
    1. Valida permisos del propietario.
    2. Fusiona colaboradores sin duplicados.
    3. Retorna HTTP 200 OK con el proyecto actualizado.
    """
    updated_project = await service.add_collaborators(
        db=db,
        project_id=project_id,
        collaborators=collaborators_in.colaborators,
        current_user=current_user,
    )
    return StandardResponse(
        status="success",
        data=updated_project,
        message="Colaboradores añadidos exitosamente",
    )
