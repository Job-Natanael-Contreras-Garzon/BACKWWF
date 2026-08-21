from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate


class IProjectService(ABC):
    """
    Interfaz abstracta para los casos de uso relacionados con Proyectos de Investigación.
    """

    @abstractmethod
    async def create_project(
        self,
        db: AsyncSession,
        project_in: ProjectCreate,
        current_user: Optional[User],
        anon_session_id: UUID,
    ) -> Dict[str, Any]:
        """Crea un proyecto en modo autenticado o anónimo."""
        ...

    @abstractmethod
    async def get_project(self, db: AsyncSession, project_id: UUID) -> Dict[str, Any]:
        """Obtiene el detalle de un proyecto activo junto con sus estaciones activas asociadas."""
        ...

    @abstractmethod
    async def list_projects(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Lista proyectos activos paginados."""
        ...

    @abstractmethod
    async def update_project(
        self,
        db: AsyncSession,
        project_id: UUID,
        project_in: ProjectUpdate,
        current_user: User,
    ) -> Dict[str, Any]:
        """Actualiza un proyecto previa validación de propiedad."""
        ...

    @abstractmethod
    async def delete_project(
        self, db: AsyncSession, project_id: UUID, current_user: User
    ) -> None:
        """Aplica Soft Delete a un proyecto (403 si es anónimo o no es propietario)."""
        ...

    @abstractmethod
    async def associate_station(
        self,
        db: AsyncSession,
        project_id: UUID,
        station_id: UUID,
        current_user: Optional[User],
    ) -> Dict[str, Any]:
        """Asocia una estación existente al proyecto (relación N:M idempotente)."""
        ...

    @abstractmethod
    async def disassociate_station(
        self,
        db: AsyncSession,
        project_id: UUID,
        station_id: UUID,
        current_user: Optional[User],
    ) -> None:
        """Desasocia una estación de un proyecto (Soft Delete de la relación intermedia)."""
        ...

    @abstractmethod
    async def get_project_summary(
        self, db: AsyncSession, project_id: UUID
    ) -> Dict[str, Any]:
        """Genera el resumen estadístico agregado de detecciones taxonómicas de todas las estaciones vinculadas."""
        ...

    @abstractmethod
    async def add_collaborators(
        self,
        db: AsyncSession,
        project_id: UUID,
        collaborators: List[UUID],
        current_user: User,
    ) -> Dict[str, Any]:
        """Añade colaboradores al proyecto validando propiedad."""
        ...
