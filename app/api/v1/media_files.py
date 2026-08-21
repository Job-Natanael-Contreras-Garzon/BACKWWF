from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_anon_session_id,
    get_current_user_optional,
    get_db,
    get_media_service,
)
from app.interfaces.media_service import IMediaService
from app.models.user import User
from app.schemas.response_wrapper import StandardResponse

router = APIRouter(prefix="/camera-stations", tags=["Media Files"])


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: POST /api/v1/camera-stations/{station_id}/files
# Happy Path: Recibe archivo multimedia (.mp4, .jpg, .png, etc.), valida que la
# estación exista y esté activa, almacena en uploads/{type}s, registra MediaFile,
# procesa inferencia de IA, parsea taxonomía a Species y retorna HTTP 201 Created.
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/{station_id}/files",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir archivo multimedia (Video o Imagen) y procesar con IA",
)
async def upload_station_media_file(
    station_id: UUID,
    file: UploadFile = File(..., description="Archivo multimedia de imagen o video"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    anon_session_id: UUID = Depends(get_anon_session_id),
    service: IMediaService = Depends(get_media_service),
):
    """
    **Physical Path**: `POST /api/v1/camera-stations/{station_id}/files`

    **Happy Path**:
    1. Recibe un archivo `multipart/form-data` correspondiente a una imagen (`.jpg`, `.png`) o video (`.mp4`, etc.).
    2. Valida la estación activa (`is_deleted == False`).
    3. Almacena el binario en la carpeta correspondiente (`uploads/videos` o `uploads/images`).
    4. Registra la entidad `MediaFile`.
    5. Envía a inferencia de IA externa y parsea automáticamente la taxonomía (`family`, `genus`, `scientific_name`, `common_name`).
    6. Persiste los registros de `Species` asociados y actualiza telemetría si es video.
    7. Retorna HTTP 201 Created con el resumen del archivo y detecciones identificadas.
    """
    result = await service.process_media_upload(
        db=db,
        station_id=station_id,
        file=file,
        current_user=current_user,
        anon_session_id=anon_session_id,
    )
    file_type = result.get("file_type", "archivo")
    return StandardResponse(
        status="success",
        data=result,
        message=f"Archivo {file_type} subido y procesado exitosamente por la IA",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/camera-stations/{station_id}/files
# Happy Path: Lista todos los archivos multimedia activos asociados a una estación.
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/{station_id}/files",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar archivos multimedia de una estación",
)
async def list_station_media_files(
    station_id: UUID,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    service: IMediaService = Depends(get_media_service),
):
    """
    **Physical Path**: `GET /api/v1/camera-stations/{station_id}/files`

    **Happy Path**:
    1. Consulta los archivos multimedia activos (`is_deleted == False`) vinculados a la estación `station_id`.
    2. Retorna HTTP 200 OK con la lista paginada de archivos.
    """
    files = await service.list_media_by_station(
        db=db, station_id=station_id, skip=skip, limit=limit
    )
    return StandardResponse(
        status="success",
        data=files,
        message="Archivos multimedia de la estación obtenidos exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/camera-stations/files/{media_file_id}
# Happy Path: Obtiene el detalle de un archivo multimedia por su UUID.
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/files/{media_file_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener detalle de archivo multimedia",
)
async def get_media_file_detail(
    media_file_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: IMediaService = Depends(get_media_service),
):
    """
    **Physical Path**: `GET /api/v1/camera-stations/files/{media_file_id}`

    **Happy Path**:
    1. Busca el archivo multimedia activo por su `media_file_id`.
    2. Retorna HTTP 200 OK con los metadatos completos del archivo.
    """
    media_file = await service.get_media_file(db=db, media_file_id=media_file_id)
    return StandardResponse(
        status="success",
        data=media_file,
        message="Archivo multimedia obtenido exitosamente",
    )
