from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from app import crud
from app.schemas import IndividualCreate, IndividualRead, IndividualUpdate
from app.db.session import get_db

router = APIRouter(prefix="/individuals", tags=["Individuals"])

@router.post("/", response_model=IndividualRead, status_code=status.HTTP_201_CREATED)
async def create_individual(ind_in: IndividualCreate, db: AsyncSession = Depends(get_db)):
    if ind_in.species_id:
        sp = await crud.species.get(db=db, id=ind_in.species_id)
        if not sp: raise HTTPException(status_code=404, detail="Species not found")
    return await crud.individual.create(db=db, obj_in=ind_in)

@router.get("/", response_model=List[IndividualRead])
async def get_individuals(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.individual.get_multi(db=db, skip=skip, limit=limit)

@router.get("/{ind_id}", response_model=IndividualRead)
async def get_individual(ind_id: UUID, db: AsyncSession = Depends(get_db)):
    ind = await crud.individual.get(db=db, id=ind_id)
    if not ind: raise HTTPException(status_code=404, detail="Individual not found")
    return ind

@router.post("/{ind_id}/verify", response_model=IndividualRead)
async def verify_individual(ind_id: UUID, verified: bool, db: AsyncSession = Depends(get_db)):
    ind = await crud.individual.get(db=db, id=ind_id)
    if not ind: raise HTTPException(status_code=404, detail="Individual not found")
    return await crud.individual.update(db=db, db_obj=ind, obj_in={"is_verified": verified})

@router.delete("/{ind_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_individual(ind_id: UUID, db: AsyncSession = Depends(get_db)):
    ind = await crud.individual.get(db=db, id=ind_id)
    if not ind: raise HTTPException(status_code=404, detail="Individual not found")
    await crud.individual.remove(db=db, id=ind_id)
