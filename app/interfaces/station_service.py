from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.camera_station import CameraStationCreate, CameraStationUpdate


class IStationService(ABC):
    """
    Interfaz abstracta para los casos de uso relacionados con Estaciones de Cámara Trampa.
    """

    @abstractmethod
    async def create_station(
        self,
        db: AsyncSession,
        station_in: CameraStationCreate,
        current_user: Optional[User],
        anon_session_id: UUID,
    ) -> Dict[str, Any]:
        """Crea una estación de cámara en modo autenticado o anónimo."""
        ...

    @abstractmethod
    async def get_station(self, db: AsyncSession, station_id: UUID) -> Dict[str, Any]:
        """Obtiene una estación de cámara activa por su identificador UUID."""
        ...

    @abstractmethod
    async def list_stations(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Lista estaciones de cámara activas paginadas."""
        ...

    @abstractmethod
    async def update_station(
        self,
        db: AsyncSession,
        station_id: UUID,
        station_in: CameraStationUpdate,
        current_user: User,
    ) -> Dict[str, Any]:
        """Actualiza una estación de cámara previa validación de propiedad."""
        ...

    @abstractmethod
    async def delete_station(
        self, db: AsyncSession, station_id: UUID, current_user: User
    ) -> None:
        """Aplica Soft Delete a una estación (403 si es anónima o no es propietario)."""
        ...

    @abstractmethod
    async def get_station_summary(
        self, db: AsyncSession, station_id: UUID
    ) -> Dict[str, Any]:
        """Genera el resumen estadístico de especies detectadas en la estación."""
        ...
