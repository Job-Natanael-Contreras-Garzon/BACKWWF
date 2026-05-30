from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from app import crud
from app.schemas import ReportCreate, ReportRead
from app.db.session import get_db

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.post("/", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(report_in: ReportCreate, db: AsyncSession = Depends(get_db)):
    return await crud.report.create(db=db, obj_in=report_in)

@router.get("/", response_model=List[ReportRead])
async def get_reports(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.report.get_multi(db=db, skip=skip, limit=limit)

@router.get("/{report_id}", response_model=ReportRead)
async def get_report(report_id: UUID, db: AsyncSession = Depends(get_db)):
    rep = await crud.report.get(db=db, id=report_id)
    if not rep: raise HTTPException(status_code=404, detail="Report not found")
    return rep

@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: UUID, db: AsyncSession = Depends(get_db)):
    rep = await crud.report.get(db=db, id=report_id)
    if not rep: raise HTTPException(status_code=404, detail="Report not found")
    await crud.report.remove(db=db, id=report_id)
