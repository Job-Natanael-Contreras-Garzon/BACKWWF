from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.station_service import IStationService
from app.models.anon_session import AnonSession
from app.models.camera_station import CameraStation
from app.models.project import Project
from app.models.project_station import ProjectStation
from app.models.species import Species
from app.models.user import User
from app.schemas.camera_station import CameraStationCreate, CameraStationUpdate


class StationService(IStationService):
    """
    Implementación de la lógica de negocio y casos de uso para Estaciones de Cámara Trampa.
    Cumple con el contrato IStationService.
    """

    def _format_station(self, station: CameraStation) -> Dict[str, Any]:
        return {
            "id": str(station.id),
            "project_id": str(station.project_id) if station.project_id else None,
            "user_id": str(station.user_id) if station.user_id else None,
            "anon_session_id": str(station.anon_session_id) if station.anon_session_id else None,
            "station_code": station.station_code,
            "location_name": station.location_name,
            "latitude": float(station.latitude) if station.latitude is not None else None,
            "longitude": float(station.longitude) if station.longitude is not None else None,
            "altitude_meters": float(station.altitude_meters) if station.altitude_meters is not None else None,
            "camera_brand": station.camera_brand,
            "camera_model": station.camera_model,
            "serial_number": station.serial_number,
            "trigger_speed_ms": station.trigger_speed_ms,
            "ir_range_meters": station.ir_range_meters,
            "deployment_date": station.deployment_date,
            "retrieval_date": station.retrieval_date,
            "status": station.status,
            "meta_data": station.meta_data,
            "created_at": station.created_at,
            "updated_at": station.updated_at,
            "is_deleted": station.is_deleted,
            "deleted_at": station.deleted_at,
            "dias_activos": station.dias_activos,
            "n_clips": station.n_clips,
            "seg_grabados": station.seg_grabados,
            "horas_grabadas": float(station.horas_grabadas) if station.horas_grabadas is not None else None,
        }

    async def create_station(
        self,
        db: AsyncSession,
        station_in: CameraStationCreate,
        current_user: Optional[User],
        anon_session_id: UUID,
    ) -> Dict[str, Any]:
        user_id = current_user.id if current_user else None
        anon_id = None if current_user else anon_session_id

        if anon_id:
            # Garantizar que exista el registro en anon_sessions antes de referenciarlo
            anon_check = await db.execute(select(AnonSession).where(AnonSession.id == anon_id))
            if not anon_check.scalar_one_or_none():
                db.add(AnonSession(id=anon_id, is_claimed=False))
                await db.flush()

        # Si viene project_id, validar que el proyecto exista y no esté eliminado
        if station_in.project_id:
            p_res = await db.execute(
                select(Project).where(
                    Project.id == station_in.project_id, Project.is_deleted == False
                )
            )
            project = p_res.scalar_one_or_none()
            if not project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="El proyecto especificado no existe o ha sido eliminado.",
                )

        new_station = CameraStation(
            project_id=station_in.project_id,
            user_id=user_id,
            anon_session_id=anon_id,
            station_code=station_in.station_code,
            location_name=station_in.location_name,
            latitude=station_in.latitude,
            longitude=station_in.longitude,
            altitude_meters=station_in.altitude_meters,
            camera_brand=station_in.camera_brand,
            camera_model=station_in.camera_model,
            serial_number=station_in.serial_number,
            trigger_speed_ms=station_in.trigger_speed_ms,
            ir_range_meters=station_in.ir_range_meters,
            deployment_date=station_in.deployment_date,
            retrieval_date=station_in.retrieval_date,
            status=station_in.status or "active",
            meta_data=station_in.meta_data,
            is_deleted=False,
        )
        db.add(new_station)
        await db.commit()
        await db.refresh(new_station)

        # Si tiene project_id, registrar automáticamente en project_stations (N:M)
        if station_in.project_id:
            new_ps = ProjectStation(
                project_id=station_in.project_id,
                station_id=new_station.id,
                is_deleted=False,
            )
            db.add(new_ps)
            await db.commit()

        return self._format_station(new_station)

    async def get_station(self, db: AsyncSession, station_id: UUID) -> Dict[str, Any]:
        result = await db.execute(
            select(CameraStation).where(
                CameraStation.id == station_id, CameraStation.is_deleted == False
            )
        )
        station = result.scalar_one_or_none()
        if not station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estación de cámara no encontrada.",
            )
        return self._format_station(station)

    async def list_stations(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(CameraStation)
            .where(CameraStation.is_deleted == False)
            .offset(skip)
            .limit(limit)
        )
        stations = result.scalars().all()
        return [self._format_station(s) for s in stations]

    async def update_station(
        self,
        db: AsyncSession,
        station_id: UUID,
        station_in: CameraStationUpdate,
        current_user: User,
    ) -> Dict[str, Any]:
        result = await db.execute(
            select(CameraStation).where(
                CameraStation.id == station_id, CameraStation.is_deleted == False
            )
        )
        station = result.scalar_one_or_none()
        if not station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estación de cámara no encontrada.",
            )

        # Validación de autorización: Solo el dueño puede editar
        if station.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para modificar esta estación de cámara.",
            )

        update_data = station_in.model_dump(exclude_unset=True)
        for field, val in update_data.items():
            setattr(station, field, val)

        station.updated_at = datetime.now(timezone.utc)
        db.add(station)
        await db.commit()
        await db.refresh(station)
        return self._format_station(station)

    async def delete_station(
        self, db: AsyncSession, station_id: UUID, current_user: User
    ) -> None:
        result = await db.execute(
            select(CameraStation).where(
                CameraStation.id == station_id, CameraStation.is_deleted == False
            )
        )
        station = result.scalar_one_or_none()
        if not station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estación de cámara no encontrada.",
            )

        # Regla 1 Soft Delete: Si es anónima, bloquear con 403
        if station.user_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No se pueden eliminar elementos anónimos. Inicie sesión y reclame el recurso primero.",
            )

        # Regla 2 Soft Delete: Verificar propiedad
        if station.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para eliminar esta estación de cámara. Solo el propietario puede realizar esta acción.",
            )

        # Ejecutar Soft Delete
        station.is_deleted = True
        station.deleted_at = datetime.now(timezone.utc)
        db.add(station)
        await db.commit()

    async def get_station_summary(
        self, db: AsyncSession, station_id: UUID
    ) -> Dict[str, Any]:
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

        # Total detecciones activas
        det_res = await db.execute(
            select(func.count(Species.id)).where(
                Species.station_id == station_id, Species.is_deleted == False
            )
        )
        total_detections = det_res.scalar() or 0

        # Conteo de especies distintas activas
        spec_count_res = await db.execute(
            select(func.count(func.distinct(Species.common_name))).where(
                Species.station_id == station_id, Species.is_deleted == False
            )
        )
        distinct_species = spec_count_res.scalar() or 0

        # Frecuencia por especie (Nombre Común)
        spec_freq_res = await db.execute(
            select(Species.common_name, func.count(Species.id))
            .where(Species.station_id == station_id, Species.is_deleted == False)
            .group_by(Species.common_name)
            .order_by(func.count(Species.id).desc())
        )
        freq_by_species = [
            {"species": row[0], "count": row[1]} for row in spec_freq_res.fetchall()
        ]

        # Frecuencia por Familia
        fam_freq_res = await db.execute(
            select(Species.family, func.count(Species.id))
            .where(
                Species.station_id == station_id,
                Species.family.isnot(None),
                Species.is_deleted == False,
            )
            .group_by(Species.family)
            .order_by(func.count(Species.id).desc())
        )
        freq_by_family = [
            {"family": row[0], "count": row[1]} for row in fam_freq_res.fetchall()
        ]

        # Frecuencia por Género
        gen_freq_res = await db.execute(
            select(Species.genus, func.count(Species.id))
            .where(
                Species.station_id == station_id,
                Species.genus.isnot(None),
                Species.is_deleted == False,
            )
            .group_by(Species.genus)
            .order_by(func.count(Species.id).desc())
        )
        freq_by_genus = [
            {"genus": row[0], "count": row[1]} for row in gen_freq_res.fetchall()
        ]

        return {
            "station_id": str(station_id),
            "distinct_species_count": distinct_species,
            "total_detections_count": total_detections,
            "frequency_by_species": freq_by_species,
            "frequency_by_family": freq_by_family,
            "frequency_by_genus": freq_by_genus,
        }


station_service = StationService()
