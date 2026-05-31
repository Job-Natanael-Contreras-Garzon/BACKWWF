from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.crud.base import CRUDBase
from app.models.species import Species
from app.models.camera_station import CameraStation
from app.schemas.species import SpeciesCreate, SpeciesUpdate


class CRUDSpecies(CRUDBase[Species, SpeciesCreate, SpeciesUpdate]):
    def __init__(self, model: type[Species] = Species):
        super().__init__(model)

    async def get_species_with_data(self, db: AsyncSession) -> List[Species]:
        """
        Obtiene todos los species con sus relaciones (station y video) ordenados por fecha.
        """
        result = await db.execute(
            select(Species)
            .order_by(Species.detection_timestamp)
        )
        return list(result.scalars().all())

    async def get_filtered_species_with_data(
        self, 
        db: AsyncSession,
        project_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        station_id: Optional[UUID] = None
    ) -> List[Species]:
        stmt = select(Species).join(CameraStation)
        
        if project_id:
            stmt = stmt.where(CameraStation.project_id == project_id)
        if station_id:
            stmt = stmt.where(Species.station_id == station_id)
        if start_date:
            stmt = stmt.where(Species.detection_timestamp >= start_date)
        if end_date:
            stmt = stmt.where(Species.detection_timestamp <= end_date)
            
        stmt = stmt.order_by(Species.detection_timestamp)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())

species = CRUDSpecies()
