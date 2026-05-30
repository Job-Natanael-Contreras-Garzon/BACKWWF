from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from app import crud
from app.schemas import CameraStationCreate, CameraStationRead, CameraStationUpdate
from app.db.session import get_db
from app.api.deps import get_current_user_id

router = APIRouter(prefix="/camera-stations", tags=["Camera Stations"])

@router.post("/", response_model=CameraStationRead, status_code=status.HTTP_201_CREATED)
async def create_camera_station(
    station_in: CameraStationCreate, 
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    project = await crud.project.get(db=db, id=station_in.project_id)
    if not project: raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Only project owners can add camera stations.")
        
    return await crud.camera_station.create(db=db, obj_in=station_in)

@router.get("/", response_model=List[CameraStationRead])
async def get_stations(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.camera_station.get_multi(db=db, skip=skip, limit=limit)

@router.get("/{station_id}", response_model=CameraStationRead)
async def get_station(station_id: UUID, db: AsyncSession = Depends(get_db)):
    station = await crud.camera_station.get(db=db, id=station_id)
    if not station: raise HTTPException(status_code=404, detail="Station not found")
    return station

@router.patch("/{station_id}", response_model=CameraStationRead)
async def update_station(
    station_id: UUID, 
    station_in: CameraStationUpdate, 
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    station = await crud.camera_station.get(db=db, id=station_id)
    if not station: raise HTTPException(status_code=404, detail="Station not found")
    
    project = await crud.project.get(db=db, id=station.project_id)
    if project.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Only project owners can edit camera stations.")
        
    return await crud.camera_station.update(db=db, db_obj=station, obj_in=station_in)

@router.delete("/{station_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_station(
    station_id: UUID, 
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    station = await crud.camera_station.get(db=db, id=station_id)
    if not station: raise HTTPException(status_code=404, detail="Station not found")
    
    project = await crud.project.get(db=db, id=station.project_id)
    if project.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Only project owners can delete camera stations.")
        
    await crud.camera_station.remove(db=db, id=station_id)
