from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.crud.base import CRUDBase
from app.models.camera_station import CameraStation
from app.models.video import Video
from app.schemas.camera_station import CameraStationCreate, CameraStationUpdate


class CRUDCameraStation(CRUDBase[CameraStation, CameraStationCreate, CameraStationUpdate]):
    def __init__(self, model: type[CameraStation] = CameraStation):
        super().__init__(model)

    async def update_video_stats(
        self, db: AsyncSession, *, station_id: UUID
    ) -> Optional[CameraStation]:
        """
        Actualiza las estadísticas de videos de una estación de cámara:
        - dias_activos: número de días únicos con videos
        - n_clips: número total de videos
        - seg_grabados: suma de duración en segundos de todos los videos
        - horas_grabadas: seg_grabados / 3600
        """
        station = await self.get(db, id=station_id)
        if not station:
            return None
        
        # Contar total de videos (n_clips)
        videos_count_result = await db.execute(
            select(func.count(Video.id)).where(Video.station_id == station_id)
        )
        n_clips = videos_count_result.scalar() or 0
        
        # Sumar duración total en segundos (seg_grabados)
        duration_sum_result = await db.execute(
            select(func.sum(Video.duration_seconds)).where(Video.station_id == station_id)
        )
        seg_grabados = duration_sum_result.scalar() or 0
        
        # Calcular horas grabadas
        horas_grabadas = seg_grabados / 3600 if seg_grabados else 0
        
        # Contar días únicos de capture_date (dias_activos)
        days_count_result = await db.execute(
            select(func.count(func.distinct(func.date(Video.capture_date)))).where(
                Video.station_id == station_id,
                Video.capture_date.isnot(None)
            )
        )
        dias_activos = days_count_result.scalar() or 0
        
        # Actualizar la estación con las nuevas estadísticas
        station.dias_activos = dias_activos
        station.n_clips = n_clips
        station.seg_grabados = seg_grabados
        station.horas_grabadas = horas_grabadas
        
        db.add(station)
        await db.commit()
        await db.refresh(station)
        
        return station


camera_station = CRUDCameraStation()
