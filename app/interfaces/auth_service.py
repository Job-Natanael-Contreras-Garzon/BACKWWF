from abc import ABC, abstractmethod
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.auth import RegisterSchema, LoginSchema, RefreshSchema, AuthTokens, AuthDataResponse, UserReadBasic


class IAuthService(ABC):
    """
    Interfaz abstracta para el servicio de autenticación y gestión de tokens.
    Define los contratos que deben implementar las clases de servicio de casos de uso de Auth.
    """

    @abstractmethod
    async def register_user(self, db: AsyncSession, user_in: RegisterSchema) -> Dict[str, Any]:
        """
        Registra un nuevo usuario en la base de datos, valida unicidad de correo,
        genera hash de contraseña y emite tokens JWT.
        """
        pass

    @abstractmethod
    async def authenticate_user(self, db: AsyncSession, credentials: LoginSchema) -> Dict[str, Any]:
        """
        Valida las credenciales de un usuario existente y genera tokens JWT de acceso y refresco.
        """
        pass

    @abstractmethod
    async def refresh_tokens(self, db: AsyncSession, data: RefreshSchema) -> Dict[str, Any]:
        """
        Valida un token de refresco vigente y emite un nuevo par de tokens JWT.
        """
        pass

    @abstractmethod
    async def get_user_profile(self, current_user: User) -> Dict[str, Any]:
        """
        Formatea y devuelve la información del perfil del usuario autenticado.
        """
        pass
