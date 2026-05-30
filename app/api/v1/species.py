from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from app import crud
from app.schemas import SpeciesRead, SpeciesUpdate
from app.db.session import get_db

router = APIRouter(prefix="/species", tags=["Species & AI"])

@router.get("/", response_model=List[SpeciesRead])
async def get_all_species(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.species.get_multi(db=db, skip=skip, limit=limit)

@router.get("/{species_id}", response_model=SpeciesRead)
async def get_species(species_id: UUID, db: AsyncSession = Depends(get_db)):
    sp = await crud.species.get(db=db, id=species_id)
    if not sp: raise HTTPException(status_code=404, detail="Species not found")
    return sp

@router.post("/{species_id}/verify", response_model=SpeciesRead)
async def verify_species(species_id: UUID, verified: bool, db: AsyncSession = Depends(get_db)):
    """
    Un experto humano verifica si la detección de IA es correcta o incorrecta.
    verified = True (Correcto), verified = False (Falso Positivo)
    """
    sp = await crud.species.get(db=db, id=species_id)
    if not sp: raise HTTPException(status_code=404, detail="Species not found")
    
    return await crud.species.update(db=db, db_obj=sp, obj_in={"is_verified": verified})

@router.delete("/{species_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_species(species_id: UUID, db: AsyncSession = Depends(get_db)):
    sp = await crud.species.get(db=db, id=species_id)
    if not sp: raise HTTPException(status_code=404, detail="Species not found")
    await crud.species.remove(db=db, id=species_id)
