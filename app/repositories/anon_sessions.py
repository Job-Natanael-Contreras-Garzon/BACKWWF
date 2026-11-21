import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import case, delete, exists, func, or_, select, update

from app.core.enums import AnonSessionStatus, ClassificationStatus
from app.models.anon_session import AnonSession
from app.models.camera_station import CameraStation
from app.models.classification import Classification, ClassificationBatch
from app.models.project import Project
from app.repositories.base import Repository


def _purgeable_ids() -> Any:
    """Sesiones vencidas sin archivos en proceso (D13): esas se purgan en la próxima corrida,
    cuando el worker haya terminado, para no dejar un fotograma sin fila."""
    return select(AnonSession.id).where(
        AnonSession.status == AnonSessionStatus.EXPIRED,
        ~exists(
            select(1).where(
                Classification.anon_session_id == AnonSession.id,
                Classification.status == ClassificationStatus.PROCESSING,
            )
        ),
    )


class AnonSessionRepository(Repository[AnonSession]):
    model = AnonSession

    async def get_by_token_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> AnonSession | None:
        stmt = select(AnonSession).where(AnonSession.token_hash == token_hash)
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self._first(stmt)

    async def list_expirable(self, now: datetime, limit: int = 500) -> list[AnonSession]:
        """Sesiones activas vencidas, para el cron FL-30."""
        stmt = (
            select(AnonSession)
            .where(AnonSession.status == AnonSessionStatus.ACTIVE, AnonSession.expires_at < now)
            .order_by(AnonSession.expires_at)
            .limit(limit)
        )
        return list(await self.session.scalars(stmt))

    async def count_active_resources(self, anon_session_id: uuid.UUID) -> tuple[int, int, int]:
        stmt = select(
            select(func.count())
            .select_from(Classification)
            .where(
                Classification.anon_session_id == anon_session_id,
                Classification.is_deleted.is_(False),
            )
            .scalar_subquery(),
            select(func.count())
            .select_from(CameraStation)
            .where(
                CameraStation.anon_session_id == anon_session_id,
                CameraStation.is_deleted.is_(False),
            )
            .scalar_subquery(),
            select(func.count())
            .select_from(Project)
            .where(
                Project.anon_session_id == anon_session_id,
                Project.is_deleted.is_(False),
            )
            .scalar_subquery(),
        )
        cls_count, cam_count, proj_count = (await self.session.execute(stmt)).one()
        return int(cls_count or 0), int(cam_count or 0), int(proj_count or 0)

    async def summarize_retention(self, anon_session_id: uuid.UUID) -> tuple[bool, bool]:
        """Devuelve (tiene_filas_activas, tiene_alguna_con_anon_retain_false) en las 4 tablas."""
        owned_models = (Classification, ClassificationBatch, Project, CameraStation)
        has_any_expr = or_(
            *(
                exists(
                    select(1).where(
                        model.anon_session_id == anon_session_id,
                        model.is_deleted.is_(False),
                    )
                )
                for model in owned_models
            )
        )
        has_non_retained_expr = or_(
            *(
                exists(
                    select(1).where(
                        model.anon_session_id == anon_session_id,
                        model.is_deleted.is_(False),
                        model.anon_retain.is_(False),
                    )
                )
                for model in owned_models
            )
        )
        has_any, has_non_retained = (
            await self.session.execute(select(has_any_expr, has_non_retained_expr))
        ).one()
        return bool(has_any), bool(has_non_retained)

    async def transfer_to_user(
        self,
        anon_session_id: uuid.UUID,
        user_id: uuid.UUID,
        camera_renames: dict[uuid.UUID, str],
    ) -> None:
        """Traspaso masivo en 4 UPDATE (incluye is_deleted para no dejar huérfanos).

        CB-41: los ítems en cola siguen al dueño del lote; al mover lotes y clasificaciones
        al usuario, todo trabajo en curso aterriza directamente en su cuenta.
        """
        cam_values: dict[str, Any] = {
            "owner_user_id": user_id,
            "anon_session_id": None,
            "anon_retain": None,
        }
        if camera_renames:
            cam_values["code"] = case(
                camera_renames, value=CameraStation.id, else_=CameraStation.code
            )
        await self.session.execute(
            update(CameraStation)
            .where(CameraStation.anon_session_id == anon_session_id)
            .values(**cam_values)
        )
        for model in (Project, ClassificationBatch, Classification):
            await self.session.execute(
                update(model)
                .where(model.anon_session_id == anon_session_id)
                .values(owner_user_id=user_id, anon_session_id=None, anon_retain=None)
            )

    async def mark_expired(self, session_ids: list[uuid.UUID]) -> int:
        if not session_ids:
            return 0
        result = await self.session.execute(
            update(AnonSession)
            .where(
                AnonSession.id.in_(session_ids),
                AnonSession.status == AnonSessionStatus.ACTIVE,
            )
            .values(status=AnonSessionStatus.EXPIRED)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def cancel_queued_in_expired(self) -> tuple[int, list[str]]:
        """D13 / CB-42: antes de purgar, los archivos en cola se cancelan. Devuelve sus temporales
        para borrarlos después del commit."""
        pending = (
            Classification.anon_session_id.in_(_purgeable_ids()),
            Classification.anon_retain.is_(False),
            Classification.status == ClassificationStatus.QUEUED,
        )
        keys = list(await self.session.scalars(select(Classification.tmp_key).where(*pending)))
        await self.session.execute(
            update(Classification)
            .where(*pending)
            .values(
                status=ClassificationStatus.CANCELLED,
                error_code="ANON_SESSION_EXPIRED",
                tmp_key=None,
            )
        )
        return len(keys), [k for k in keys if k]

    async def list_expired_evidence_keys_to_purge(self) -> list[str]:
        stmt = select(Classification.evidence_key).where(
            Classification.anon_session_id.in_(_purgeable_ids()),
            Classification.anon_retain.is_(False),
            Classification.evidence_key.is_not(None),
            Classification.evidence_key != "",
        )
        return [key for key in await self.session.scalars(stmt) if key]

    async def count_retained_in_expired(self) -> int:
        expired_ids = select(AnonSession.id).where(AnonSession.status == AnonSessionStatus.EXPIRED)
        owned_models = (Classification, ClassificationBatch, Project, CameraStation)
        stmt = select(
            *(
                select(func.count())
                .select_from(model)
                .where(model.anon_session_id.in_(expired_ids), model.anon_retain.is_(True))
                .scalar_subquery()
                for model in owned_models
            )
        )
        counts = (await self.session.execute(stmt)).one()
        return sum(int(c or 0) for c in counts)

    async def purge_non_retained_in_expired(self) -> tuple[int, int, int, int, int]:
        """Borrado físico en orden FK (única excepción a 'no borrar nunca', FLUJOS §3)."""
        expired_ids = _purgeable_ids()

        cls_sessions = list(
            await self.session.scalars(
                delete(Classification)
                .where(
                    Classification.anon_session_id.in_(expired_ids),
                    Classification.anon_retain.is_(False),
                )
                .returning(Classification.anon_session_id)
            )
        )
        # CB-43: si el ajuste cambió mid-session, un lote anon_retain=false puede tener hijos true.
        batch_sessions = list(
            await self.session.scalars(
                delete(ClassificationBatch)
                .where(
                    ClassificationBatch.anon_session_id.in_(expired_ids),
                    ClassificationBatch.anon_retain.is_(False),
                    ~exists(select(1).where(Classification.batch_id == ClassificationBatch.id)),
                )
                .returning(ClassificationBatch.anon_session_id)
            )
        )
        proj_sessions = list(
            await self.session.scalars(
                delete(Project)
                .where(
                    Project.anon_session_id.in_(expired_ids),
                    Project.anon_retain.is_(False),
                )
                .returning(Project.anon_session_id)
            )
        )
        cam_sessions = list(
            await self.session.scalars(
                delete(CameraStation)
                .where(
                    CameraStation.anon_session_id.in_(expired_ids),
                    CameraStation.anon_retain.is_(False),
                    ~exists(select(1).where(Classification.camera_station_id == CameraStation.id)),
                    ~exists(
                        select(1).where(ClassificationBatch.camera_station_id == CameraStation.id)
                    ),
                )
                .returning(CameraStation.anon_session_id)
            )
        )
        affected_sessions = {
            sid
            for sid in (*cls_sessions, *batch_sessions, *proj_sessions, *cam_sessions)
            if sid is not None
        }
        return (
            len(affected_sessions),
            len(cls_sessions),
            len(batch_sessions),
            len(proj_sessions),
            len(cam_sessions),
        )
