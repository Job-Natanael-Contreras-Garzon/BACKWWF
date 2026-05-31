from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
import uuid
import os
import shutil
import asyncio
import logging
import json
from datetime import timedelta, datetime
from dotenv import load_dotenv

from app import crud
from app.schemas import VideoCreate, VideoRead, SpeciesCreate
from app.db.session import get_db
from app.services.video_service import extract_video_metadata
from app.services.ai_service import analyze_video_with_external_ai

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["Videos"])

@router.post("/", response_model=VideoRead, status_code=status.HTTP_201_CREATED)
async def upload_video(
    station_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Sube un archivo de video real. Lo guarda localmente, extrae metadatos con FFmpeg
    y lo asocia a una cámara trampa.
    """
    logger.info(f"[Video Router] Petición recibida para subir video a la estación {station_id}")
    
    station = await crud.camera_station.get(db=db, id=station_id)
    if not station: 
        logger.error(f"[Video Router] La estación {station_id} no existe.")
        raise HTTPException(status_code=404, detail="Camera Station not found")

    # Usar ruta absoluta desde el inicio para evitar problemas con el working directory
    upload_dir = os.path.abspath("uploads/videos")
    os.makedirs(upload_dir, exist_ok=True)
    logger.info(f"[Video Router] Directorio de subida: {upload_dir}")
    
    safe_filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = os.path.join(upload_dir, safe_filename)
    
    # Escribir el archivo
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Verificar que el archivo se guardó
    if os.path.exists(file_path):
        file_size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
        logger.info(f"[Video Router] Archivo guardado correctamente en: {file_path} ({file_size_mb} MB)")
    else:
        logger.error("[Video Router] Error crítico: El archivo no se guardó en el disco.")
        raise HTTPException(status_code=500, detail="Error guardando el archivo.")

    # 3. Extraer metadatos usando tu función (en un hilo separado)
    logger.info("[Video Router] Iniciando hilo para extraer metadatos...")
    metadata = await asyncio.to_thread(extract_video_metadata, file_path)
    
    # Manejar los datos por defecto si hubo error
    duration = None
    capture_date = None
    metadata_extra = metadata
    
    if "error" not in metadata:
        duration = metadata.get("duration_seconds")
        capture_date = metadata.get("capture_date")
    else:
        logger.warning(f"[Video Router] La extracción devolvió un error: {metadata['error']}")

    # 4. Crear el registro en la base de datos
    logger.info("[Video Router] Guardando registro en la Base de Datos...")
    video_in = VideoCreate(
        station_id=station_id,
        file_url=file_path,
        original_filename=file.filename,
        duration_seconds=int(duration) if duration else None, 
        file_size_mb=file_size_mb,
        capture_date=capture_date,
        metadata_extra=metadata_extra
    )
    
    video = await crud.video.create(db=db, obj_in=video_in)
    
    # 5. Llamar a la API de IA para analizar el video
    try:
        logger.info("[Video Router] Enviando video a la API de IA para análisis...")
        ai_response = await analyze_video_with_external_ai(file_path)
        logger.info(f"[Video Router] Response de la API de IA:\n{json.dumps(ai_response, indent=2)}")
        
        # 6. Procesar el response y crear registros en la tabla species
        if "results" in ai_response and ai_response["results"]:
            logger.info(f"[Video Router] Procesando {len(ai_response['results'])} resultados...")
            
            # Concatenar AI_SERVICE_URL con crop_url
            ai_service_url = os.getenv("AI_SERVICE_URL", "http://localhost:8080")
            
            # Procesar todas las detecciones de todos los resultados
            total_detections = 0
            for result in ai_response["results"]:
                timestamp_seconds = result.get("timestamp_seconds", 0)
                
                for detection in result["detections"]:
                    # Parsear el campo species (formato: "genus;species;common_name")
                    species_parts = detection["species"].split(";")
                    common_name = species_parts[-1] if len(species_parts) > 2 else species_parts[0]
                    scientific_name = f"{species_parts[0]} {species_parts[1]}" if len(species_parts) > 1 else None
                    
                    # Calcular detection_timestamp como capture_date + timestamp_seconds
                    detection_timestamp = None
                    if capture_date:
                        # Convertir capture_date a datetime si es string
                        if isinstance(capture_date, str):
                            capture_date_dt = datetime.fromisoformat(capture_date.replace('Z', '+00:00'))
                        else:
                            capture_date_dt = capture_date
                        detection_timestamp = capture_date_dt + timedelta(seconds=timestamp_seconds)
                    
                    # Concatenar AI_SERVICE_URL con crop_url
                    url_img = None
                    if detection.get("crop_url"):
                        crop_url = detection["crop_url"]
                        if isinstance(crop_url, str):
                            url_img = f"{ai_service_url}{crop_url}"
                        else:
                            url_img = f"{ai_service_url}{str(crop_url)}"
                    
                    species_in = SpeciesCreate(
                        station_id=station_id,
                        video_id=video.id,
                        common_name=common_name,
                        scientific_name=scientific_name,
                        confidence_score=detection["confidence"],
                        detection_timestamp=detection_timestamp,
                        url_img=url_img
                    )
                    
                    await crud.species.create(db=db, obj_in=species_in)
                    total_detections += 1
            
            logger.info(f"[Video Router] Se crearon {total_detections} registros en species")
        else:
            logger.warning("[Video Router] No se encontraron detecciones en el response de la IA")
            
    except Exception as e:
        logger.error(f"[Video Router] Error al procesar detecciones de IA: {e}")
        import traceback
        logger.error(f"[Video Router] Traceback: {traceback.format_exc()}")
        # No fallamos el endpoint si la IA falla, solo logueamos el error
    
    return video

@router.get("/", response_model=List[VideoRead])
async def get_videos(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.video.get_multi(db=db, skip=skip, limit=limit)

@router.get("/{video_id}", response_model=VideoRead)
async def get_video(video_id: UUID, db: AsyncSession = Depends(get_db)):
    video = await crud.video.get(db=db, id=video_id)
    if not video: raise HTTPException(status_code=404, detail="Video not found")
    return video

@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(video_id: UUID, db: AsyncSession = Depends(get_db)):
    video = await crud.video.get(db=db, id=video_id)
    if not video: raise HTTPException(status_code=404, detail="Video not found")
    
    await crud.video.remove(db=db, id=video_id)
    
    if os.path.exists(video.file_url):
        os.remove(video.file_url)
