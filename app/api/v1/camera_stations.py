from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_anon_session_id,
    get_current_user,
    get_current_user_optional,
    get_db,
    get_station_service,
)
from app.interfaces.station_service import IStationService
from app.models.user import User
from app.schemas.camera_station import CameraStationCreate, CameraStationUpdate
from app.schemas.response_wrapper import StandardResponse

router = APIRouter(prefix="/camera-stations", tags=["Camera Stations"])


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: POST /api/v1/camera-stations/
# Happy Path: Recibe datos de la estación; si viene autenticado asigna user_id;
# si es anónimo asigna anon_session_id; si incluye project_id asocia en
# project_stations automáticamente; retorna HTTP 201 Created con StandardResponse.
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear estación de cámara trampa",
)
async def create_camera_station(
    station_in: CameraStationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    anon_session_id: UUID = Depends(get_anon_session_id),
    service: IStationService = Depends(get_station_service),
):
    """
    **Physical Path**: `POST /api/v1/camera-stations/`

    **Happy Path**:
    1. Recibe payload de la estación (`station_code`, `location_name`, coordenadas, etc.).
    2. Identifica si la solicitud proviene de un usuario autenticado o anónimo.
    3. Persiste la entidad `CameraStation` y la vincula al proyecto si `project_id` fue enviado.
    4. Retorna HTTP 201 Created con `{status: "success", data: <estacion>, message: "Estación de cámara creada exitosamente"}`.
    """
    station = await service.create_station(
        db=db,
        station_in=station_in,
        current_user=current_user,
        anon_session_id=anon_session_id,
    )
    return StandardResponse(
        status="success",
        data=station,
        message="Estación de cámara creada exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/camera-stations/
# Happy Path: Consulta todas las estaciones activas (is_deleted == False) paginadas.
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar estaciones activas",
)
async def get_stations(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    service: IStationService = Depends(get_station_service),
):
    """
    **Physical Path**: `GET /api/v1/camera-stations/`

    **Happy Path**:
    1. Recibe parámetros `skip` y `limit`.
    2. Consulta estaciones donde `is_deleted == False`.
    3. Retorna HTTP 200 OK con la lista de estaciones activas.
    """
    stations = await service.list_stations(db=db, skip=skip, limit=limit)
    return StandardResponse(
        status="success",
        data=stations,
        message="Estaciones de cámara obtenidas exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/camera-stations/{station_id}
# Happy Path: Obtiene la estación por UUID filtrando is_deleted == False.
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/{station_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener detalle de estación",
)
async def get_station(
    station_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: IStationService = Depends(get_station_service),
):
    """
    **Physical Path**: `GET /api/v1/camera-stations/{station_id}`

    **Happy Path**:
    1. Recibe `station_id` (UUID).
    2. Busca la estación activa (`is_deleted == False`).
    3. Retorna HTTP 200 OK con los datos completos de la estación.
    """
    station = await service.get_station(db=db, station_id=station_id)
    return StandardResponse(
        status="success",
        data=station,
        message="Estación de cámara obtenida exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: PATCH /api/v1/camera-stations/{station_id}
# Happy Path: Valida que el usuario sea el dueño de la estación, actualiza
# campos y retorna la estación modificada.
# ─────────────────────────────────────────────────────────────────────────────
@router.patch(
    "/{station_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Actualizar estación de cámara",
)
async def update_station(
    station_id: UUID,
    station_in: CameraStationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: IStationService = Depends(get_station_service),
):
    """
    **Physical Path**: `PATCH /api/v1/camera-stations/{station_id}`

    **Happy Path**:
    1. Valida token JWT de autenticación.
    2. Verifica que el usuario autenticado sea el dueño.
    3. Aplica los cambios y actualiza `updated_at`.
    4. Retorna HTTP 200 OK con la estación actualizada.
    """
    station = await service.update_station(
        db=db,
        station_id=station_id,
        station_in=station_in,
        current_user=current_user,
    )
    return StandardResponse(
        status="success",
        data=station,
        message="Estación de cámara actualizada exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: DELETE /api/v1/camera-stations/{station_id}
# Happy Path: Valida que la estación tenga dueño registrado y coincida con
# el usuario autenticado; aplica Soft Delete marcando is_deleted=True.
# ─────────────────────────────────────────────────────────────────────────────
@router.delete(
    "/{station_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Eliminar estación (Soft Delete)",
)
async def delete_station(
    station_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: IStationService = Depends(get_station_service),
):
    """
    **Physical Path**: `DELETE /api/v1/camera-stations/{station_id}`

    **Happy Path**:
    1. Valida token JWT obligatorio.
    2. Si la estación es anónima (`user_id is Null`), lanza HTTP 403 Forbidden.
    3. Si el usuario no es el propietario, lanza HTTP 403 Forbidden.
    4. Aplica Soft Delete (`is_deleted = True`, `deleted_at = now()`).
    5. Retorna HTTP 200 OK confirmando la eliminación lógica.
    """
    await service.delete_station(
        db=db, station_id=station_id, current_user=current_user
    )
    return StandardResponse(
        status="success",
        data=None,
        message="Estación eliminada exitosamente (Soft Delete)",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/camera-stations/{station_id}/summary
# Happy Path: Consulta métricas consolidadas de especies detectadas en la estación.
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/{station_id}/summary",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Resumen estadístico de la estación",
)
async def get_station_summary(
    station_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: IStationService = Depends(get_station_service),
):
    """
    **Physical Path**: `GET /api/v1/camera-stations/{station_id}/summary`

    **Happy Path**:
    1. Localiza la estación activa.
    2. Agrega detecciones de fauna asociadas.
    3. Retorna HTTP 200 OK con el resumen taxonómico.
    """
    summary = await service.get_station_summary(db=db, station_id=station_id)
    return StandardResponse(
        status="success",
        data=summary,
        message="Resumen estadístico de la estación obtenido exitosamente",
    )
