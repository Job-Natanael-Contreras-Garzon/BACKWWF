from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from app import crud
from app.schemas import UserCreate, UserRead, UserUpdate
from app.db.session import get_db

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    return await crud.user.create(db=db, obj_in=user_in)

@router.get("/", response_model=List[UserRead])
async def get_users(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.user.get_multi(db=db, skip=skip, limit=limit)

@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: UUID, db: AsyncSession = Depends(get_db)):
    user = await crud.user.get(db=db, id=user_id)
    if not user: raise HTTPException(status_code=404, detail="User not found")
    return user

@router.patch("/{user_id}", response_model=UserRead)
async def update_user(user_id: UUID, user_in: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = await crud.user.get(db=db, id=user_id)
    if not user: raise HTTPException(status_code=404, detail="User not found")
    return await crud.user.update(db=db, db_obj=user, obj_in=user_in)

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: UUID, db: AsyncSession = Depends(get_db)):
    user = await crud.user.get(db=db, id=user_id)
    if not user: raise HTTPException(status_code=404, detail="User not found")
    await crud.user.remove(db=db, id=user_id)
