from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from pydantic import BaseModel
from decimal import Decimal
from app import crud
from app.schemas import SpeciesRead, SpeciesUpdate, SpeciesDataResponse
from app.db.session import get_db
from app.services.species_data_service import (
    calcular_periodo_dia,
    obtener_temperatura_media,
    calcular_distancia_haversine,
    calcular_velocidad,
    obtener_moonphase
)

router = APIRouter(prefix="/species", tags=["Species & AI"])

class VerifyRequest(BaseModel):
    verified: bool

@router.get("/", response_model=List[SpeciesRead])
async def get_all_species(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.species.get_multi(db=db, skip=skip, limit=limit)

@router.get("/data", response_model=List[SpeciesDataResponse])
async def get_species_data(db: AsyncSession = Depends(get_db)):
    """
    Endpoint que devuelve datos enriquecidos de species con cálculos adicionales.
    """
    species_list = await crud.species.get_species_with_data(db=db)
    
    results = []
    prev_row = None
    
    for sp in species_list:
        # Obtener datos básicos
        id_deteccion = sp.id
        id_camara = str(sp.station_id)
        url_img = sp.url_img
        fecha_hora = sp.detection_timestamp
        especie = sp.common_name
        
        # Obtener latitud y longitud de la cámara
        latitud = float(sp.station.latitude) if sp.station.latitude else None
        longitud = float(sp.station.longitude) if sp.station.longitude else None
        
        # Obtener duración del clip del video
        duracion_clip_seg = sp.video.duration_seconds if sp.video else None
        
        # Calcular fecha, hora y periodo_dia
        fecha = fecha_hora.strftime("%Y-%m-%d") if fecha_hora else None
        hora = fecha_hora.strftime("%H:%M:%S") if fecha_hora else None
        hora_int = fecha_hora.hour if fecha_hora else None
        periodo_dia = calcular_periodo_dia(hora_int) if hora_int else None
        
        # Obtener temperatura media desde API externa
        temp_media = None
        if latitud and longitud and fecha_hora:
            temp_media = await obtener_temperatura_media(latitud, longitud, fecha_hora)
        
        # Calcular minutos desde anterior y distancia anterior
        min_desde_anterior = None
        dist_anterior_km = None
        
        if prev_row and fecha_hora and prev_row['fecha_hora']:
            # Calcular diferencia en minutos
            diff = fecha_hora - prev_row['fecha_hora']
            min_desde_anterior = diff.total_seconds() / 60  # Convertir a minutos
            
            # Calcular distancia si hay coordenadas
            if latitud and longitud and prev_row['latitud'] and prev_row['longitud']:
                dist_anterior_km = calcular_distancia_haversine(
                    latitud, longitud,
                    prev_row['latitud'], prev_row['longitud']
                )
        
        # Crear row actual para calcular velocidad
        row = {
            'especie': especie,
            'min_desde_anterior': min_desde_anterior,
            'dist_anterior_km': dist_anterior_km
        }
        
        # Calcular velocidad
        velocidad_kmh = None
        if prev_row:
            velocidad_kmh = calcular_velocidad(row, prev_row)
        
        # Obtener moonphase desde API externa
        periodo_weckel = None
        if latitud and longitud and fecha_hora:
            periodo_weckel = await obtener_moonphase(latitud, longitud, fecha_hora)
        
        # Crear respuesta
        result = SpeciesDataResponse(
            id_deteccion=id_deteccion,
            id_camara=id_camara,
            url_img=url_img,
            fecha_hora=fecha_hora,
            fecha=fecha,
            hora=hora,
            periodo_dia=periodo_dia,
            especie=especie,
            duracion_clip_seg=duracion_clip_seg,
            latitud=latitud,
            longitud=longitud,
            temp_media=temp_media,
            min_desde_anterior=min_desde_anterior,
            dist_anterior_km=dist_anterior_km,
            velocidad_kmh=velocidad_kmh,
            periodo_weckel=periodo_weckel
        )
        
        results.append(result)
        
        # Guardar row actual como prev_row para la siguiente iteración
        prev_row = {
            'especie': especie,
            'fecha_hora': fecha_hora,
            'latitud': latitud,
            'longitud': longitud,
            'min_desde_anterior': min_desde_anterior,
            'dist_anterior_km': dist_anterior_km
        }
    
    return results

@router.get("/{species_id}", response_model=SpeciesRead)
async def get_species(species_id: int, db: AsyncSession = Depends(get_db)):
    sp = await crud.species.get(db=db, id=species_id)
    if not sp: raise HTTPException(status_code=404, detail="Species not found")
    return sp

@router.post("/{species_id}/verify", response_model=SpeciesRead)
async def verify_species(species_id: int, verify_data: VerifyRequest, db: AsyncSession = Depends(get_db)):
    """
    Un experto humano verifica si la detección de IA es correcta o incorrecta.
    verified = True (Correcto), verified = False (Falso Positivo)
    """
    sp = await crud.species.get(db=db, id=species_id)
    if not sp: raise HTTPException(status_code=404, detail="Species not found")
    
    return await crud.species.update(db=db, db_obj=sp, obj_in={"is_verified": verify_data.verified})

@router.delete("/{species_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_species(species_id: int, db: AsyncSession = Depends(get_db)):
    sp = await crud.species.get(db=db, id=species_id)
    if not sp: raise HTTPException(status_code=404, detail="Species not found")
    await crud.species.remove(db=db, id=species_id)
