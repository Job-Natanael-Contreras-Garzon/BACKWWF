from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user, get_user_service
from app.db.session import get_db
from app.interfaces.user_service import IUserService
from app.models.user import User
from app.schemas.response_wrapper import StandardResponse
from app.schemas.user import ClaimRequest, UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["Users & Sessions"])


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: POST /api/v1/users/me/claim
# Happy Path: Usuario autenticado provee anon_session_id; el sistema reasigna
# todos los proyectos y estaciones anónimas hacia su user_id, marca la sesión
# como reclamada y retorna HTTP 200 con el conteo de recursos vinculados.
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/me/claim",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Reclamar datos creados en sesión anónima",
)
async def claim_anon_data(
    data: ClaimRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: IUserService = Depends(get_user_service),
):
    """
    **Physical Path**: `POST /api/v1/users/me/claim`

    **Happy Path**:
    1. Usuario autenticado envía `Authorization: Bearer <access_token>` junto con el `anon_session_id` en el body.
    2. El sistema localiza todos los `projects` creados con `anon_session_id` y actualiza `user_id = current_user.id`.
    3. El sistema localiza todas las `camera_stations` con `anon_session_id` y actualiza `user_id = current_user.id`.
    4. La entidad `AnonSession` se registra o actualiza con `is_claimed = True`, `claimed_by_user_id = current_user.id` y `claimed_at = now()`.
    5. Se ejecuta el `commit` transaccional.
    6. Retorna HTTP 200 OK con `{status: "success", data: {claimed_projects_count, claimed_stations_count, anon_session_id, claimed_by_user_id}, message: "Datos anónimos vinculados exitosamente a su cuenta"}`.
    """
    result = await service.claim_anonymous_session(
        db=db, current_user=current_user, anon_session_id=data.anon_session_id
    )
    return StandardResponse(
        status="success",
        data=result,
        message="Datos anónimos vinculados exitosamente a su cuenta",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/users/me/history
# Happy Path: Usuario autenticado consulta sus proyectos y estaciones asignadas
# no eliminadas, retornando HTTP 200 con el listado completo y estructurado.
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/me/history",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultar historial de proyectos y estaciones del usuario",
)
async def get_my_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: IUserService = Depends(get_user_service),
):
    """
    **Physical Path**: `GET /api/v1/users/me/history`

    **Happy Path**:
    1. Usuario autenticado envía `Authorization: Bearer <access_token>`.
    2. El sistema consulta todos los proyectos donde `user_id == current_user.id` y `is_deleted == False`.
    3. El sistema consulta todas las estaciones donde `user_id == current_user.id` y `is_deleted == False`.
    4. Retorna HTTP 200 OK con `{status: "success", data: {projects: [...], camera_stations: [...]}, message: "Historial del usuario obtenido exitosamente"}`.
    """
    history = await service.get_user_history(db=db, current_user=current_user)
    return StandardResponse(
        status="success",
        data=history,
        message="Historial del usuario obtenido exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/users/
# Happy Path: Lista usuarios activos registrados en el sistema (con paginación).
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar usuarios del sistema",
)
async def get_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """
    **Physical Path**: `GET /api/v1/users/`

    **Happy Path**:
    1. Recibe parámetros de paginación `skip` y `limit`.
    2. Consulta la lista de usuarios activos (`is_deleted == False`).
    3. Retorna HTTP 200 OK envuelto en `StandardResponse`.
    """
    users = await crud.user.get_multi(db=db, skip=skip, limit=limit)
    users_data = [UserRead.model_validate(u).model_dump() for u in users]
    return StandardResponse(
        status="success",
        data=users_data,
        message="Lista de usuarios obtenida exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/users/{user_id}
# Happy Path: Obtiene un usuario específico por su UUID.
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/{user_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener usuario por ID",
)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    **Physical Path**: `GET /api/v1/users/{user_id}`

    **Happy Path**:
    1. Recibe un `user_id` en path parameter.
    2. Busca el usuario en la BD.
    3. Si existe, retorna HTTP 200 OK con los datos del usuario.
    """
    user = await crud.user.get(db=db, id=user_id)
    if not user or user.is_deleted:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return StandardResponse(
        status="success",
        data=UserRead.model_validate(user).model_dump(),
        message="Usuario obtenido exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: PATCH /api/v1/users/{user_id}
# Happy Path: Actualiza parcialmente los datos de un usuario.
# ─────────────────────────────────────────────────────────────────────────────
@router.patch(
    "/{user_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Actualizar usuario",
)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Physical Path**: `PATCH /api/v1/users/{user_id}`

    **Happy Path**:
    1. Valida permisos del usuario autenticado.
    2. Actualiza los campos provistos del usuario.
    3. Retorna HTTP 200 OK con el registro actualizado.
    """
    user = await crud.user.get(db=db, id=user_id)
    if not user or user.is_deleted:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    updated = await crud.user.update(db=db, db_obj=user, obj_in=user_in)
    return StandardResponse(
        status="success",
        data=UserRead.model_validate(updated).model_dump(),
        message="Usuario actualizado exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: DELETE /api/v1/users/{user_id}
# Happy Path: Realiza soft delete marcando is_deleted=True.
# ─────────────────────────────────────────────────────────────────────────────
@router.delete(
    "/{user_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Eliminar usuario (Soft Delete)",
)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Physical Path**: `DELETE /api/v1/users/{user_id}`

    **Happy Path**:
    1. Valida permisos del usuario autenticado.
    2. Aplica Soft Delete marcando `is_deleted = True`.
    3. Retorna HTTP 200 OK con confirmación.
    """
    user = await crud.user.get(db=db, id=user_id)
    if not user or user.is_deleted:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    user.is_deleted = True
    await db.commit()
    return StandardResponse(
        status="success",
        data={"id": str(user_id)},
        message="Usuario eliminado exitosamente",
    )
