from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.interfaces.project_service import IProjectService
from app.models.anon_session import AnonSession
from app.models.camera_station import CameraStation
from app.models.project import Project
from app.models.project_station import ProjectStation
from app.models.species import Species
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService(IProjectService):
    """
    Implementación de la lógica de negocio y casos de uso para Proyectos.
    Cumple con el contrato IProjectService.
    """

    def _format_project(self, project: Project, stations: Optional[List[CameraStation]] = None) -> Dict[str, Any]:
        stations_list = []
        if stations is not None:
            stations_list = [
                {
                    "id": str(s.id),
                    "station_code": s.station_code,
                    "location_name": s.location_name,
                    "status": s.status,
                    "created_at": s.created_at,
                }
                for s in stations
                if not s.is_deleted
            ]
        elif hasattr(project, "camera_stations") and project.camera_stations:
            stations_list = [
                {
                    "id": str(s.id),
                    "station_code": s.station_code,
                    "location_name": s.location_name,
                    "status": s.status,
                    "created_at": s.created_at,
                }
                for s in project.camera_stations
                if not s.is_deleted
            ]

        return {
            "id": str(project.id),
            "user_id": str(project.user_id) if project.user_id else None,
            "anon_session_id": str(project.anon_session_id) if project.anon_session_id else None,
            "title": project.title,
            "description": project.description,
            "objectives": project.objectives,
            "expected_results": project.expected_results,
            "status": project.status,
            "colaborators": [str(c) for c in (project.colaborators or [])],
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "is_deleted": project.is_deleted,
            "deleted_at": project.deleted_at,
            "camera_stations": stations_list,
        }

    async def create_project(
        self,
        db: AsyncSession,
        project_in: ProjectCreate,
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

        new_project = Project(
            user_id=user_id,
            anon_session_id=anon_id,
            title=project_in.title,
            description=project_in.description,
            objectives=project_in.objectives,
            expected_results=project_in.expected_results,
            status=project_in.status or "public",
            colaborators=project_in.colaborators or [],
            is_deleted=False,
        )
        db.add(new_project)
        await db.commit()
        await db.refresh(new_project)
        return self._format_project(new_project, stations=[])

    async def get_project(self, db: AsyncSession, project_id: UUID) -> Dict[str, Any]:
        result = await db.execute(
            select(Project)
            .where(Project.id == project_id, Project.is_deleted == False)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proyecto no encontrado.",
            )

        # Consultar estaciones asociadas activas
        stations_query = (
            select(CameraStation)
            .join(ProjectStation, ProjectStation.station_id == CameraStation.id)
            .where(
                ProjectStation.project_id == project_id,
                ProjectStation.is_deleted == False,
                CameraStation.is_deleted == False,
            )
        )
        stations_res = await db.execute(stations_query)
        stations = stations_res.scalars().all()

        return self._format_project(project, stations=list(stations))

    async def list_projects(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(Project)
            .where(Project.is_deleted == False)
            .offset(skip)
            .limit(limit)
        )
        projects = result.scalars().all()
        return [self._format_project(p) for p in projects]

    async def update_project(
        self,
        db: AsyncSession,
        project_id: UUID,
        project_in: ProjectUpdate,
        current_user: User,
    ) -> Dict[str, Any]:
        result = await db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proyecto no encontrado.",
            )

        # Validación de autorización: Solo el dueño puede editar
        if project.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para modificar este proyecto. Solo el propietario puede editarlo.",
            )

        update_data = project_in.model_dump(exclude_unset=True)
        for field, val in update_data.items():
            setattr(project, field, val)

        project.updated_at = datetime.now(timezone.utc)
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return self._format_project(project)

    async def delete_project(
        self, db: AsyncSession, project_id: UUID, current_user: User
    ) -> None:
        result = await db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proyecto no encontrado.",
            )

        # Regla 1 Soft Delete: Si es anónimo, bloquear con 403
        if project.user_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No se pueden eliminar proyectos anónimos. Inicie sesión y reclame el recurso primero.",
            )

        # Regla 2 Soft Delete: Verificar propiedad
        if project.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para eliminar este proyecto. Solo el propietario puede realizar esta acción.",
            )

        # Ejecutar Soft Delete
        project.is_deleted = True
        project.deleted_at = datetime.now(timezone.utc)
        db.add(project)
        await db.commit()

    async def associate_station(
        self,
        db: AsyncSession,
        project_id: UUID,
        station_id: UUID,
        current_user: Optional[User],
    ) -> Dict[str, Any]:
        # 1. Validar que el proyecto exista y no esté eliminado
        p_res = await db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )
        project = p_res.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proyecto no encontrado.",
            )

        # 2. Validar que la estación exista y no esté eliminada
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

        # 3. Verificar si ya existe relación en project_stations
        ps_res = await db.execute(
            select(ProjectStation).where(
                ProjectStation.project_id == project_id,
                ProjectStation.station_id == station_id,
            )
        )
        existing = ps_res.scalar_one_or_none()

        if existing:
            if existing.is_deleted:
                existing.is_deleted = False
                existing.deleted_at = None
                existing.updated_at = datetime.now(timezone.utc)
                db.add(existing)
                await db.commit()
            return {"project_id": str(project_id), "station_id": str(station_id)}

        # 4. Crear nueva asociación N:M
        new_ps = ProjectStation(
            project_id=project_id,
            station_id=station_id,
            is_deleted=False,
        )
        db.add(new_ps)
        await db.commit()

        return {"project_id": str(project_id), "station_id": str(station_id)}

    async def disassociate_station(
        self,
        db: AsyncSession,
        project_id: UUID,
        station_id: UUID,
        current_user: Optional[User],
    ) -> None:
        ps_res = await db.execute(
            select(ProjectStation).where(
                ProjectStation.project_id == project_id,
                ProjectStation.station_id == station_id,
                ProjectStation.is_deleted == False,
            )
        )
        ps = ps_res.scalar_one_or_none()
        if not ps:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="La relación entre el proyecto y la estación no existe.",
            )

        ps.is_deleted = True
        ps.deleted_at = datetime.now(timezone.utc)
        db.add(ps)
        await db.commit()

    async def get_project_summary(
        self, db: AsyncSession, project_id: UUID
    ) -> Dict[str, Any]:
        p_res = await db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )
        project = p_res.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proyecto no encontrado.",
            )

        ps_res = await db.execute(
            select(ProjectStation.station_id).where(
                ProjectStation.project_id == project_id,
                ProjectStation.is_deleted == False,
            )
        )
        station_ids = [row[0] for row in ps_res.fetchall()]

        if not station_ids:
            return {
                "project_id": str(project_id),
                "total_associated_stations": 0,
                "distinct_species_count": 0,
                "total_detections_count": 0,
                "frequency_by_species": [],
                "frequency_by_family": [],
                "frequency_by_genus": [],
            }

        # Conteo de detecciones activas
        det_count_res = await db.execute(
            select(func.count(Species.id)).where(
                Species.station_id.in_(station_ids),
                Species.is_deleted == False,
            )
        )
        total_detections = det_count_res.scalar() or 0

        # Conteo de especies distintas activas
        spec_count_res = await db.execute(
            select(func.count(func.distinct(Species.common_name))).where(
                Species.station_id.in_(station_ids),
                Species.is_deleted == False,
            )
        )
        distinct_species = spec_count_res.scalar() or 0

        # Frecuencia por especie
        spec_freq_res = await db.execute(
            select(Species.common_name, func.count(Species.id))
            .where(
                Species.station_id.in_(station_ids),
                Species.is_deleted == False,
            )
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
                Species.station_id.in_(station_ids),
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
                Species.station_id.in_(station_ids),
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
            "project_id": str(project_id),
            "total_associated_stations": len(station_ids),
            "distinct_species_count": distinct_species,
            "total_detections_count": total_detections,
            "frequency_by_species": freq_by_species,
            "frequency_by_family": freq_by_family,
            "frequency_by_genus": freq_by_genus,
        }

    async def add_collaborators(
        self,
        db: AsyncSession,
        project_id: UUID,
        collaborators: List[UUID],
        current_user: User,
    ) -> Dict[str, Any]:
        result = await db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado.")

        if project.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para modificar colaboradores de este proyecto.",
            )

        existing = project.colaborators or []
        merged = list(set(existing + collaborators))
        project.colaborators = merged
        project.updated_at = datetime.now(timezone.utc)
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return self._format_project(project)


project_service = ProjectService()
