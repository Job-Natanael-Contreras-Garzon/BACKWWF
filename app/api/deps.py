import uuid
from typing import Optional
from uuid import UUID
from fastapi import Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.interfaces.auth_service import IAuthService
from app.interfaces.user_service import IUserService
from app.interfaces.project_service import IProjectService
from app.interfaces.station_service import IStationService
from app.interfaces.media_service import IMediaService
from app.models.user import User
from app.services.auth_service import auth_service
from app.services.user_service import user_service
from app.services.project_service import project_service
from app.services.station_service import station_service
from app.services.media_service import media_service


async def get_current_user(
    authorization: Optional[str] = Header(None, description="Token JWT Bearer"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependencia de seguridad que valida el token JWT Bearer en el Header 'Authorization'.
    Retorna la entidad User autenticada o lanza HTTPException 401.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación no proporcionado o formato inválido.",
        )

    token = authorization.split(" ")[1]
    payload = decode_token(token, is_refresh=False)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acceso inválido o expirado.",
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no contiene identificador de usuario válido.",
        )

    try:
        user_uuid = UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identificador de usuario inválido en payload.",
        )

    result = await db.execute(
        select(User).where(User.id == user_uuid, User.is_deleted == False)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado o dado de baja.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta de usuario se encuentra desactivada.",
        )

    return user


async def get_current_user_optional(
    authorization: Optional[str] = Header(None, description="Token JWT Bearer Opcional"),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Dependencia opcional: Si viene un Bearer Token válido retorna el User,
    de lo contrario retorna None sin lanzar excepción 401.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(authorization=authorization, db=db)
    except HTTPException:
        return None


async def get_current_user_id(
    current_user: User = Depends(get_current_user),
) -> UUID:
    """
    Dependencia de compatibilidad: Retorna el UUID del usuario autenticado actual.
    """
    return current_user.id


async def get_anon_session_id(
    response: Response,
    x_anon_session_id: Optional[UUID] = Header(
        None, alias="X-Anon-Session-ID", description="ID de sesión anónima"
    ),
) -> UUID:
    """
    Obtiene el anon_session_id enviado en la cabecera. Si no viene provisto,
    asume una nueva sesión anónima, genera un UUIDv4 y lo inyecta en la cabecera
    de respuesta 'X-Anon-Session-ID'.
    """
    if x_anon_session_id:
        return x_anon_session_id

    new_anon_id = uuid.uuid4()
    response.headers["X-Anon-Session-ID"] = str(new_anon_id)
    return new_anon_id


def get_auth_service() -> IAuthService:
    """Proveedor de inyección de dependencias para el servicio de autenticación."""
    return auth_service


def get_user_service() -> IUserService:
    """Proveedor de inyección de dependencias para el servicio de usuarios."""
    return user_service


def get_project_service() -> IProjectService:
    """Proveedor de inyección de dependencias para el servicio de proyectos."""
    return project_service


def get_station_service() -> IStationService:
    """Proveedor de inyección de dependencias para el servicio de estaciones de cámara."""
    return station_service


def get_media_service() -> IMediaService:
    """Proveedor de inyección de dependencias para el servicio de archivos multimedia e IA."""
    return media_service
