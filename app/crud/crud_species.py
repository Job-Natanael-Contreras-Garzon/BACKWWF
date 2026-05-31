from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.crud.base import CRUDBase
from app.models.species import Species
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


species = CRUDSpecies()
