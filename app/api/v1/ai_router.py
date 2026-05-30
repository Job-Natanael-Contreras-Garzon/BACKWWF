from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime

from app import crud
from app.schemas import SpeciesRead, SpeciesCreate
from app.services.ai_service import analyze_video_with_external_ai
from app.db.session import get_db

router = APIRouter(prefix="/ai", tags=["AI Processing"])

@router.post("/process-video/{video_id}", response_model=list[SpeciesRead])
async def process_video_ai(video_id: UUID, db: AsyncSession = Depends(get_db)):
    # 1. Usar CRUD genérico para buscar el video
    video = await crud.video.get(db=db, id=video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found in database.")

    ai_response = await analyze_video_with_external_ai(video.file_url)
    new_species_records = []
    
    for detection in ai_response.get("detections", []):
        # Usamos los schemas Create con el CRUD genérico
        species_in = SpeciesCreate(
            station_id=video.station_id,
            video_id=video.id,
            common_name=detection["common_name"],
            scientific_name=detection.get("scientific_name"),
            confidence_score=detection.get("confidence_score"),
            detection_timestamp=datetime.fromisoformat(detection["detection_timestamp"].replace("Z", "+00:00")),
            ai_raw_response=ai_response
        )
        # ⚠️ Nota: Para transacciones atómicas masivas, es mejor un create_multi, 
        # pero para simplificar usamos create individual por ahora.
        new_species = await crud.species.create(db=db, obj_in=species_in)
        new_species_records.append(new_species)
        
    return new_species_records
