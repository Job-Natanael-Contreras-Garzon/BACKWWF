from abc import ABC, abstractmethod
from typing import Any, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User


class IUserService(ABC):
    """
    Interfaz abstracta para el servicio de usuarios, historial y gestión de sesiones anónimas.
    """

    @abstractmethod
    async def claim_anonymous_session(
        self, db: AsyncSession, current_user: User, anon_session_id: UUID
    ) -> Dict[str, Any]:
        """
        Reasigna proyectos y estaciones anónimas hacia el usuario autenticado
        y registra la sesión anónima como reclamada.
        """
        pass

    @abstractmethod
    async def get_user_history(self, db: AsyncSession, current_user: User) -> Dict[str, Any]:
        """
        Consulta los proyectos y estaciones activas asociadas al usuario autenticado.
        """
        pass
