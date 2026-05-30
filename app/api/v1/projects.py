from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from app import crud
from app.schemas import ProjectCreate, ProjectRead, ProjectUpdate
from app.db.session import get_db
from app.api.deps import get_current_user_id

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.post("/", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_in: ProjectCreate, 
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    # Forzamos que el creador sea el dueño, ignorando lo que venga en el schema
    project_in.user_id = current_user_id
    return await crud.project.create(db=db, obj_in=project_in)

@router.get("/", response_model=List[ProjectRead])
async def get_projects(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.project.get_multi(db=db, skip=skip, limit=limit)

@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await crud.project.get(db=db, id=project_id)
    if not project: raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID, 
    project_in: ProjectUpdate, 
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    project = await crud.project.get(db=db, id=project_id)
    if not project: raise HTTPException(status_code=404, detail="Project not found")
    
    # AUTORIZACIÓN: Solo el dueño puede editar
    if project.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Not enough permissions. You are not the owner.")
        
    return await crud.project.update(db=db, db_obj=project, obj_in=project_in)

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID, 
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    project = await crud.project.get(db=db, id=project_id)
    if not project: raise HTTPException(status_code=404, detail="Project not found")
    
    # AUTORIZACIÓN: Solo el dueño puede eliminar
    if project.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Not enough permissions. You are not the owner.")
        
    await crud.project.remove(db=db, id=project_id)
