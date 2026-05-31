from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app import crud
from app.schemas import ReportCreate, ReportRead
from app.db.session import get_db
from app.services.species_data_service import enrich_species_data
from app.services.indicators_service import IndicatorsService

router = APIRouter(prefix="/reports", tags=["Reports"])

indicators_router = APIRouter(prefix="/indicators", tags=["Reports Indicators"])

async def get_filtered_data(
    db: AsyncSession,
    project_id: Optional[UUID] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    station_ids: Optional[List[UUID]] = None
):
    raw_species = await crud.species.get_filtered_species_with_data(
        db, project_id=project_id, start_date=start_date, end_date=end_date, station_ids=station_ids
    )
    return await enrich_species_data(raw_species)

@indicators_router.get("/frequency")
async def get_indicator_frequency(
    project_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    station_ids: Optional[List[UUID]] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    data = await get_filtered_data(db, project_id, start_date, end_date, station_ids)
    return IndicatorsService.calculate_frequency(data)

@indicators_router.get("/diversity")
async def get_indicator_diversity(
    project_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    station_ids: Optional[List[UUID]] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    data = await get_filtered_data(db, project_id, start_date, end_date, station_ids)
    return IndicatorsService.calculate_diversity(data)

@indicators_router.get("/rai")
async def get_indicator_rai(
    project_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    station_ids: Optional[List[UUID]] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    data = await get_filtered_data(db, project_id, start_date, end_date, station_ids)
    return IndicatorsService.calculate_rai(data)

@indicators_router.get("/rai-monthly")
async def get_indicator_rai_monthly(
    project_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    station_ids: Optional[List[UUID]] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    data = await get_filtered_data(db, project_id, start_date, end_date, station_ids)
    return IndicatorsService.calculate_rai_mensual(data)

@indicators_router.get("/activity-weckel")
async def get_indicator_activity(
    project_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    station_ids: Optional[List[UUID]] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    data = await get_filtered_data(db, project_id, start_date, end_date, station_ids)
    return IndicatorsService.calculate_actividad(data)

@indicators_router.get("/ocupacion")
async def get_indicator_ocupacion(
    project_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    station_ids: Optional[List[UUID]] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    data = await get_filtered_data(db, project_id, start_date, end_date, station_ids)
    return IndicatorsService.calculate_ocupacion(data)

@indicators_router.get("/temperatura")
async def get_indicator_temperatura(
    project_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    station_ids: Optional[List[UUID]] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    data = await get_filtered_data(db, project_id, start_date, end_date, station_ids)
    return IndicatorsService.calculate_temperatura(data)

@indicators_router.get("/eventos-independientes")
async def get_indicator_eventos_independientes(
    project_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    station_ids: Optional[List[UUID]] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    data = await get_filtered_data(db, project_id, start_date, end_date, station_ids)
    return IndicatorsService.calculate_eventos_independientes(data)

@indicators_router.get("/mapa-calor")
async def get_indicator_mapa_calor(
    project_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    station_ids: Optional[List[UUID]] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    data = await get_filtered_data(db, project_id, start_date, end_date, station_ids)
    return IndicatorsService.calculate_mapa_calor(data)

@indicators_router.get("/gremios")
async def get_indicator_gremios(
    project_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    station_ids: Optional[List[UUID]] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    data = await get_filtered_data(db, project_id, start_date, end_date, station_ids)
    return IndicatorsService.calculate_gremios(data)

# Include indicators before dynamic paths like /{report_id}
router.include_router(indicators_router)

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
