from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User


class IMediaService(ABC):
    """
    Interfaz abstracta para los casos de uso relacionados con Archivos Multimedia (Videos/Imágenes)
    y procesamiento de inferencia de IA.
    """

    @abstractmethod
    async def process_media_upload(
        self,
        db: AsyncSession,
        station_id: UUID,
        file: UploadFile,
        current_user: Optional[User],
        anon_session_id: UUID,
    ) -> Dict[str, Any]:
        """
        Procesa la subida de un archivo multimedia (imagen o video), lo almacena localmente,
        registra la entidad MediaFile, consulta el servicio de IA y persiste las detecciones taxonómicas.
        """
        ...

    @abstractmethod
    async def get_media_file(
        self, db: AsyncSession, media_file_id: UUID
    ) -> Dict[str, Any]:
        """Obtiene un archivo multimedia activo por su identificador UUID."""
        ...

    @abstractmethod
    async def list_media_by_station(
        self, db: AsyncSession, station_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Lista archivos multimedia activos pertenecientes a una estación de cámara."""
        ...
