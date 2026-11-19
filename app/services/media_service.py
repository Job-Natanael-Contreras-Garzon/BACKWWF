import os
import shutil
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MediaType
from app.interfaces.media_service import IMediaService
from app.models.camera_station import CameraStation
from app.models.media_file import MediaFile
from app.models.species import Species
from app.models.user import User
from app.services.ai_service import analyze_media_with_ai, parse_taxonomy


ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}
ALLOWED_EXTENSIONS = ALLOWED_VIDEO_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS

ALLOWED_MIME_TYPES = {
    "video/mp4", "video/x-msvideo", "video/quicktime", "video/x-matroska",
    "video/x-ms-wmv", "video/x-flv", "video/webm",
    "image/jpeg", "image/png", "image/bmp", "image/webp", "image/tiff",
    "application/octet-stream",  # Fallback for binary uploads from mobile/hardware
}


class MediaService(IMediaService):
    """
    Implementación de la lógica de negocio para Archivos Multimedia y procesamiento de IA.
    Cumple con el contrato IMediaService.
    """

    def _format_media_file(self, media: MediaFile) -> Dict[str, Any]:
        return {
            "id": str(media.id),
            "station_id": str(media.station_id),
            "file_type": media.file_type,
            "file_url": media.file_url,
            "original_filename": media.original_filename,
            "duration_seconds": media.duration_seconds,
            "file_size_mb": float(media.file_size_mb) if media.file_size_mb is not None else None,
            "capture_date": media.capture_date,
            "metadata_extra": media.metadata_extra,
            "created_at": media.created_at,
            "updated_at": media.updated_at,
            "is_deleted": media.is_deleted,
            "deleted_at": media.deleted_at,
        }

    async def process_media_upload(
        self,
        db: AsyncSession,
        station_id: UUID,
        file: UploadFile,
        current_user: Optional[User],
        anon_session_id: UUID,
    ) -> Dict[str, Any]:
        # 1. Validar existencia y estado de la estación
        s_res = await db.execute(
            select(CameraStation).where(
                CameraStation.id == station_id, CameraStation.is_deleted == False
            )
        )
        station = s_res.scalar_one_or_none()
        if not station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estación de cámara no encontrada.",
            )

        # 2. Validar extensión de archivo y Content-Type (Seguridad y MIME Validation)
        filename = file.filename or "unknown_file"
        ext = os.path.splitext(filename)[1].lower()
        content_type = (file.content_type or "").lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Extensión '{ext}' no permitida. Formatos válidos: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        if content_type and content_type not in ALLOWED_MIME_TYPES and not any(v in content_type for v in ["video/", "image/"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipo MIME '{content_type}' no permitido para archivos multimedia.",
            )

        # Determinar tipo de archivo
        if ext in ALLOWED_VIDEO_EXTENSIONS or "video" in content_type:
            file_type = MediaType.VIDEO
            upload_subfolder = "videos"
        else:
            file_type = MediaType.IMAGE
            upload_subfolder = "images"

        # 3. Guardar archivo localmente
        base_upload_dir = os.path.abspath(os.path.join("uploads", upload_subfolder))
        os.makedirs(base_upload_dir, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex[:12]}_{filename}"
        file_path = os.path.join(base_upload_dir, unique_name)

        import asyncio

        max_file_bytes = 300 * 1024 * 1024  # 300 MB
        chunk_size = 1024 * 1024  # 1 MB
        file_size_bytes = 0

        try:
            def _write_chunk(path: str, data: bytes, mode: str) -> None:
                with open(path, mode) as buffer:
                    buffer.write(data)

            mode = "wb"
            while chunk := await file.read(chunk_size):
                file_size_bytes += len(chunk)
                if file_size_bytes > max_file_bytes:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="El archivo excede el límite máximo de 300 MB.",
                    )
                await asyncio.to_thread(_write_chunk, file_path, chunk, mode)
                mode = "ab"
        except HTTPException:
            raise
        except Exception:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno al guardar el archivo (INTERNAL_ERROR).",
            )
        file_size_mb = Decimal(str(round(file_size_bytes / (1024 * 1024), 2)))

        # 4. Crear registro en BD para MediaFile
        media_entity = MediaFile(
            station_id=station_id,
            file_type=file_type,
            file_url=file_path.replace("\\", "/"),
            original_filename=filename,
            file_size_mb=file_size_mb,
            capture_date=datetime.now(timezone.utc),
            metadata_extra={"content_type": content_type, "size_bytes": file_size_bytes},
            is_deleted=False,
        )
        db.add(media_entity)
        await db.commit()
        await db.refresh(media_entity)

        # 5. Inferencia de IA externa y persistencia taxonómica por lotes (Batch Insert)
        ai_response = await analyze_media_with_ai(file_path, file_type=file_type)
        species_records_to_insert: List[Species] = []

        for group in ai_response.get("results", []):
            for det in group.get("detections", []):
                raw_species = det.get("species", "")
                tax = parse_taxonomy(raw_species)
                conf = det.get("confidence")
                conf_dec = Decimal(str(round(conf, 4))) if conf is not None else None

                species_record = Species(
                    station_id=station_id,
                    media_file_id=media_entity.id,
                    common_name=tax["common_name"] or "Especie Desconocida",
                    scientific_name=tax["scientific_name"],
                    family=tax["family"],
                    genus=tax["genus"],
                    confidence_score=conf_dec,
                    url_img=det.get("crop_url"),
                    detection_timestamp=datetime.now(timezone.utc),
                    is_deleted=False,
                )
                species_records_to_insert.append(species_record)

        # Inserción masiva en un único round-trip (elimina problema N+1)
        if species_records_to_insert:
            db.add_all(species_records_to_insert)
            await db.flush()

        saved_detections = [
            {
                "id": sp.id,
                "common_name": sp.common_name,
                "scientific_name": sp.scientific_name,
                "family": sp.family,
                "genus": sp.genus,
                "confidence_score": float(sp.confidence_score) if sp.confidence_score is not None else None,
                "url_img": sp.url_img,
            }
            for sp in species_records_to_insert
        ]

        # 6. Actualizar métricas de la estación si es video
        if file_type == MediaType.VIDEO:
            station.n_clips = (station.n_clips or 0) + 1
            db.add(station)

        await db.commit()

        return {
            "media_file_id": str(media_entity.id),
            "station_id": str(station_id),
            "file_type": file_type,
            "file_url": media_entity.file_url,
            "file_size_mb": float(file_size_mb),
            "detections_count": len(saved_detections),
            "detections": saved_detections,
        }

    async def get_media_file(
        self, db: AsyncSession, media_file_id: UUID
    ) -> Dict[str, Any]:
        result = await db.execute(
            select(MediaFile).where(
                MediaFile.id == media_file_id, MediaFile.is_deleted == False
            )
        )
        media = result.scalar_one_or_none()
        if not media:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Archivo multimedia no encontrado.",
            )
        return self._format_media_file(media)

    async def list_media_by_station(
        self, db: AsyncSession, station_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(MediaFile)
            .where(MediaFile.station_id == station_id, MediaFile.is_deleted == False)
            .offset(skip)
            .limit(limit)
        )
        files = result.scalars().all()
        return [self._format_media_file(f) for f in files]


media_service = MediaService()
