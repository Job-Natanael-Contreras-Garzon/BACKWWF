from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.user_service import IUserService
from app.models.anon_session import AnonSession
from app.models.camera_station import CameraStation
from app.models.project import Project
from app.models.user import User


class UserService(IUserService):
    """
    Implementación del caso de uso de gestión de usuarios, historial y reclamo de sesiones anónimas.
    Cumple con la interfaz IUserService.
    """

    async def claim_anonymous_session(
        self, db: AsyncSession, current_user: User, anon_session_id: UUID
    ) -> Dict[str, Any]:
        # 1. Reasignar proyectos anónimos hacia el usuario
        proj_stmt = (
            update(Project)
            .where(Project.anon_session_id == anon_session_id, Project.is_deleted == False)
            .values(user_id=current_user.id)
        )
        proj_res = await db.execute(proj_stmt)

        # 2. Reasignar estaciones anónimas hacia el usuario
        stat_stmt = (
            update(CameraStation)
            .where(CameraStation.anon_session_id == anon_session_id, CameraStation.is_deleted == False)
            .values(user_id=current_user.id)
        )
        stat_res = await db.execute(stat_stmt)

        # 3. Registrar o actualizar sesión anónima como reclamada
        session_res = await db.execute(
            select(AnonSession).where(AnonSession.id == anon_session_id)
        )
        anon_session = session_res.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if not anon_session:
            anon_session = AnonSession(
                id=anon_session_id,
                is_claimed=True,
                claimed_by_user_id=current_user.id,
                claimed_at=now,
            )
            db.add(anon_session)
        else:
            anon_session.is_claimed = True
            anon_session.claimed_by_user_id = current_user.id
            anon_session.claimed_at = now

        await db.commit()

        return {
            "claimed_projects_count": proj_res.rowcount if proj_res.rowcount is not None else 0,
            "claimed_stations_count": stat_res.rowcount if stat_res.rowcount is not None else 0,
            "anon_session_id": str(anon_session_id),
            "claimed_by_user_id": str(current_user.id),
        }

    async def get_user_history(self, db: AsyncSession, current_user: User) -> Dict[str, Any]:
        proj_res = await db.execute(
            select(Project).where(Project.user_id == current_user.id, Project.is_deleted == False)
        )
        projects = proj_res.scalars().all()

        stat_res = await db.execute(
            select(CameraStation).where(
                CameraStation.user_id == current_user.id, CameraStation.is_deleted == False
            )
        )
        stations = stat_res.scalars().all()

        return {
            "projects": [
                {
                    "id": str(p.id),
                    "title": p.title,
                    "status": p.status,
                    "created_at": p.created_at,
                }
                for p in projects
            ],
            "camera_stations": [
                {
                    "id": str(s.id),
                    "station_code": s.station_code,
                    "location_name": s.location_name,
                    "status": s.status,
                    "created_at": s.created_at,
                }
                for s in stations
            ],
        }


user_service = UserService()
