"""Consultas del panel admin (HU-15a). El ``AdminScope`` vive acá: el admin ve lo anónimo y lo
público de usuarios, **nunca** lo privado (CB-96); de lo privado solo hay conteos.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import ColumnElement, and_, case, func, or_, select, update

from app.core.enums import (
    AnonSessionStatus,
    ClassificationStatus,
    UserRole,
    ValidationStatus,
    Visibility,
)
from app.models.admin import AdminAuditLog, AnonPurgeRun
from app.models.anon_session import AnonSession
from app.models.camera_station import CameraStation
from app.models.classification import Classification
from app.models.project import Project, ProjectCameraStation
from app.models.user import User
from app.repositories.base import Repository
from app.repositories.camera_stations import escape_like
from app.repositories.classifications import ClassificationQuery, apply_filters

AdminScope = Literal["anonymous", "public", "all"]


def scope_filter(model: Any, scope: AdminScope) -> ColumnElement[bool]:
    """Cámaras y proyectos: anónimo = de una sesión; público = de un usuario y público."""
    anonymous = model.anon_session_id.is_not(None)
    public = and_(model.owner_user_id.is_not(None), model.visibility == Visibility.PUBLIC)
    options: dict[str, ColumnElement[bool]] = {
        "anonymous": anonymous,
        "public": public,
        "all": or_(anonymous, public),
    }
    return options[scope]


def classification_scope(scope: AdminScope) -> ColumnElement[bool]:
    """Una clasificación entra si es anónima o si su cámara es pública de un usuario."""
    anonymous = Classification.anon_session_id.is_not(None)
    public = Classification.camera_station_id.in_(
        select(CameraStation.id).where(scope_filter(CameraStation, "public"))
    )
    options: dict[str, ColumnElement[bool]] = {
        "anonymous": anonymous,
        "public": public,
        "all": or_(anonymous, public),
    }
    return options[scope]


def _count(condition: ColumnElement[bool]) -> Any:
    return func.count(case((condition, 1)))


class AdminRepository(Repository[User]):
    model = User

    # --- conteos de plataforma (incluyen lo privado, solo como número) ----------------------

    async def user_counts(self, start: datetime | None, end: datetime | None) -> dict[str, Any]:
        stmt = select(
            func.count(),
            _count(User.is_active.is_(True)),
            _count(User.is_active.is_(False)),
        ).where(User.role == UserRole.USER)
        total, active, disabled = (await self.session.execute(stmt)).one()
        with_cls = await self.session.scalar(
            select(func.count(func.distinct(Classification.owner_user_id))).where(
                Classification.owner_user_id.is_not(None)
            )
        )
        month = func.to_char(User.created_at, "YYYY-MM")
        by_month = select(month, func.count()).where(User.role == UserRole.USER)
        if start is not None:
            by_month = by_month.where(User.created_at >= start)
        if end is not None:
            by_month = by_month.where(User.created_at < end)
        months = (await self.session.execute(by_month.group_by(month).order_by(month))).all()
        return {
            "total": int(total),
            "active": int(active),
            "disabled": int(disabled),
            "with_classifications": int(with_cls or 0),
            "new_by_month": [{"month": m, "count": int(n)} for m, n in months],
        }

    async def anon_counts(self) -> dict[str, Any]:
        stmt = select(
            func.count(),
            _count(AnonSession.status == AnonSessionStatus.ACTIVE),
            _count(AnonSession.status == AnonSessionStatus.CLAIMED),
            _count(AnonSession.status == AnonSessionStatus.EXPIRED),
        )
        total, active, claimed, expired = (await self.session.execute(stmt)).one()
        anon_cls = await self.session.scalar(
            select(func.count()).where(Classification.anon_session_id.is_not(None))
        )
        return {
            "total": int(total),
            "active": int(active),
            "claimed": int(claimed),
            "expired": int(expired),
            "conversion_rate": round(claimed / total * 100, 1) if total else 0.0,
            "avg_classifications_per_session": round((anon_cls or 0) / total, 1) if total else 0.0,
        }

    async def content_counts(self, model: Any) -> dict[str, int]:
        stmt = select(
            _count(and_(model.is_deleted.is_(False), scope_filter(model, "public"))),
            _count(
                and_(
                    model.is_deleted.is_(False),
                    model.owner_user_id.is_not(None),
                    model.visibility == Visibility.PRIVATE,
                )
            ),
            _count(and_(model.is_deleted.is_(False), model.anon_session_id.is_not(None))),
            _count(model.is_deleted.is_(True)),
        )
        public, private, anonymous, deleted = (await self.session.execute(stmt)).one()
        return {
            "public": int(public),
            "private": int(private),
            "anonymous": int(anonymous),
            "deleted": int(deleted),
        }

    async def classification_counts(self) -> dict[str, Any]:
        live = Classification.is_deleted.is_(False)
        total = await self.session.scalar(select(func.count()).where(live))
        by_source = (
            await self.session.execute(
                select(Classification.source, func.count())
                .where(live)
                .group_by(Classification.source)
            )
        ).all()
        errors = (
            await self.session.execute(
                select(Classification.error_code, func.count())
                .where(live, Classification.status == ClassificationStatus.ERROR)
                .group_by(Classification.error_code)
            )
        ).all()
        evidence = await self.session.scalar(
            select(func.count()).where(live, Classification.evidence_key.is_not(None))
        )
        return {
            "total": int(total or 0),
            "by_source": {str(s): int(n) for s, n in by_source},
            "errors_by_code": {str(c or "UNKNOWN"): int(n) for c, n in errors},
            "evidence_files": int(evidence or 0),
        }

    async def model_feedback(self, scope: AdminScope) -> dict[str, Any]:
        """Acierto real de la IA según las validaciones, sin lo privado ni las repeticiones."""
        base = and_(
            Classification.is_deleted.is_(False),
            classification_scope(scope),
            Classification.validation_status.in_(
                (
                    ValidationStatus.CONFIRMED,
                    ValidationStatus.CORRECTED,
                    ValidationStatus.CORRECTED_UNLISTED,
                    ValidationStatus.REJECTED,
                )
            ),
        )
        vs, cs = Classification.validation_status, Classification.correction_source
        stmt = select(
            func.count(),
            _count(vs == ValidationStatus.CONFIRMED),
            _count(and_(vs == ValidationStatus.CORRECTED, cs == "alternative")),
            _count(and_(vs == ValidationStatus.CORRECTED, cs == "catalog")),
            _count(vs == ValidationStatus.CORRECTED_UNLISTED),
            _count(vs == ValidationStatus.REJECTED),
        ).where(base)
        total, confirmed, alt, catalog, unlisted, rejected = (
            await self.session.execute(stmt)
        ).one()

        def pct(n: int) -> float:
            return round(n / total * 100, 1) if total else 0.0

        confusions = (
            await self.session.execute(
                select(
                    Classification.scientific_name,
                    Classification.corrected_scientific_name,
                    func.count().label("n"),
                )
                .where(base, vs == ValidationStatus.CORRECTED)
                .group_by(Classification.scientific_name, Classification.corrected_scientific_name)
                .order_by(func.count().desc())
                .limit(10)
            )
        ).all()
        return {
            "validated": int(total),
            "confirmed_pct": pct(confirmed),
            "corrected_with_alternative_pct": pct(alt),
            "corrected_from_catalog_pct": pct(catalog),
            "corrected_unlisted_pct": pct(unlisted),
            "rejected_pct": pct(rejected),
            "top_confusions": [
                {"predicted": p, "corrected_to": c, "count": int(n)} for p, c, n in confusions
            ],
        }

    async def retention(self) -> dict[str, Any]:
        retained = await self.session.scalar(
            select(func.count()).where(
                Classification.anon_session_id.is_not(None), Classification.anon_retain.is_(True)
            )
        )
        purged = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(AnonPurgeRun.classifications), 0),
                    func.coalesce(func.sum(AnonPurgeRun.camera_stations), 0),
                    func.coalesce(func.sum(AnonPurgeRun.projects), 0),
                    func.coalesce(func.sum(AnonPurgeRun.frames), 0),
                )
            )
        ).one()
        keys = ("classifications", "camera_stations", "projects", "frames")
        return {
            "retained_classifications": int(retained or 0),
            "purged": {k: int(v) for k, v in zip(keys, purged, strict=True)},
        }

    # --- exploración (solo AdminScope) -------------------------------------------------------

    async def scoped_cameras(
        self, scope: AdminScope, *, include_deleted: bool
    ) -> list[CameraStation]:
        stmt = select(CameraStation).where(scope_filter(CameraStation, scope))
        if not include_deleted:
            stmt = stmt.where(CameraStation.is_deleted.is_(False))
        return list(await self.session.scalars(stmt))

    async def list_cameras(
        self,
        scope: AdminScope,
        *,
        q: str | None,
        anon_session_id: uuid.UUID | None,
        include_deleted: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[CameraStation], int]:
        stmt = select(CameraStation).where(scope_filter(CameraStation, scope))
        if not include_deleted:
            stmt = stmt.where(CameraStation.is_deleted.is_(False))
        if anon_session_id is not None:
            stmt = stmt.where(CameraStation.anon_session_id == anon_session_id)
        if q:
            like = f"%{escape_like(q.strip())}%"
            stmt = stmt.where(
                or_(
                    CameraStation.code.ilike(like, escape="\\"),
                    CameraStation.name.ilike(like, escape="\\"),
                )
            )
        stmt = stmt.order_by(CameraStation.created_at.desc(), CameraStation.id)
        return await self._page(stmt, page, page_size)  # type: ignore[return-value]

    async def list_classifications(
        self,
        scope: AdminScope,
        query: ClassificationQuery,
        *,
        anon_session_id: uuid.UUID | None,
        include_deleted: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[Classification], int]:
        """§13.3: los filtros de §8.1 (``apply_filters``) dentro del ``AdminScope``."""
        stmt = select(Classification).where(classification_scope(scope))
        if not include_deleted:
            stmt = stmt.where(Classification.is_deleted.is_(False))
        if anon_session_id is not None:
            stmt = stmt.where(Classification.anon_session_id == anon_session_id)
        if query.camera_ids is not None:
            stmt = stmt.where(Classification.camera_station_id.in_(query.camera_ids))
        return await self._page(apply_filters(stmt, query), page, page_size)  # type: ignore[return-value]

    async def scoped_project_camera_ids(self, project_id: uuid.UUID) -> list[uuid.UUID] | None:
        """Cámaras del proyecto que el admin puede ver; ``None`` si el proyecto es privado."""
        project = await self.session.scalar(
            select(Project.id).where(
                Project.id == project_id,
                Project.is_deleted.is_(False),
                scope_filter(Project, "all"),
            )
        )
        if project is None:
            return None
        stmt = (
            select(CameraStation.id)
            .join(ProjectCameraStation, ProjectCameraStation.camera_station_id == CameraStation.id)
            .where(
                ProjectCameraStation.project_id == project_id, scope_filter(CameraStation, "all")
            )
        )
        return list(await self.session.scalars(stmt))

    async def scoped_classification(self, classification_id: uuid.UUID) -> Classification | None:
        stmt = select(Classification).where(
            Classification.id == classification_id, classification_scope("all")
        )
        row: Classification | None = await self.session.scalar(stmt)
        return row

    async def list_anon_sessions(
        self,
        status: AnonSessionStatus | None,
        start: datetime | None,
        end: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AnonSession], int]:
        stmt = select(AnonSession)
        if status is not None:
            stmt = stmt.where(AnonSession.status == status)
        if start is not None:
            stmt = stmt.where(AnonSession.created_at >= start)
        if end is not None:
            stmt = stmt.where(AnonSession.created_at < end)
        stmt = stmt.order_by(AnonSession.created_at.desc(), AnonSession.id)
        return await self._page(stmt, page, page_size)  # type: ignore[return-value]

    async def anon_session_counts(
        self, session_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, Any]]:
        if not session_ids:
            return {}
        result: dict[uuid.UUID, dict[str, Any]] = {
            sid: {"classifications": 0, "camera_stations": 0, "projects": 0, "retained": False}
            for sid in session_ids
        }
        for model, key in (
            (Classification, "classifications"),
            (CameraStation, "camera_stations"),
            (Project, "projects"),
        ):
            rows = await self.session.execute(
                select(
                    model.anon_session_id,
                    _count(model.is_deleted.is_(False)),
                    func.bool_or(model.anon_retain),
                )
                .where(model.anon_session_id.in_(session_ids))
                .group_by(model.anon_session_id)
            )
            for sid, n, retained in rows.all():
                result[sid][key] = int(n)
                result[sid]["retained"] = result[sid]["retained"] or bool(retained)
        return result

    # --- usuarios -----------------------------------------------------------------------------

    async def list_users(
        self, q: str | None, active: bool | None, page: int, page_size: int
    ) -> tuple[list[User], int]:
        stmt = select(User)
        if q:
            like = f"%{escape_like(q.strip())}%"
            stmt = stmt.where(
                or_(User.email.ilike(like, escape="\\"), User.full_name.ilike(like, escape="\\"))
            )
        if active is not None:
            stmt = stmt.where(User.is_active.is_(active))
        return await self._page(stmt.order_by(User.created_at.desc(), User.id), page, page_size)

    async def user_content_counts(
        self, user_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, int]]:
        result = {
            uid: {
                "camera_stations_public": 0,
                "camera_stations_private": 0,
                "projects_public": 0,
                "projects_private": 0,
                "classifications": 0,
            }
            for uid in user_ids
        }
        if not user_ids:
            return result
        for model, prefix in ((CameraStation, "camera_stations"), (Project, "projects")):
            rows = await self.session.execute(
                select(
                    model.owner_user_id,
                    _count(model.visibility == Visibility.PUBLIC),
                    _count(model.visibility == Visibility.PRIVATE),
                )
                .where(model.owner_user_id.in_(user_ids), model.is_deleted.is_(False))
                .group_by(model.owner_user_id)
            )
            for uid, pub, pri in rows.all():
                result[uid][f"{prefix}_public"] = int(pub)
                result[uid][f"{prefix}_private"] = int(pri)
        rows = await self.session.execute(
            select(Classification.owner_user_id, func.count())
            .where(Classification.owner_user_id.in_(user_ids), Classification.is_deleted.is_(False))
            .group_by(Classification.owner_user_id)
        )
        for uid, n in rows.all():
            result[uid]["classifications"] = int(n)
        return result

    async def cancel_queued(self, condition: ColumnElement[bool], error_code: str) -> list[str]:
        """CB-97/CB-98: cancela lo que estaba en cola y devuelve los temporales a borrar."""
        pending = and_(condition, Classification.status == ClassificationStatus.QUEUED)
        keys = list(await self.session.scalars(select(Classification.tmp_key).where(pending)))
        await self.session.execute(
            update(Classification)
            .where(pending)
            .values(status=ClassificationStatus.CANCELLED, error_code=error_code, tmp_key=None)
            .execution_options(synchronize_session=False)
        )
        return [k for k in keys if k]

    # --- auditoría ----------------------------------------------------------------------------

    async def list_audit(
        self,
        action: str | None,
        entity_type: str | None,
        start: datetime | None,
        end: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminAuditLog], int]:
        stmt = select(AdminAuditLog)
        if action:
            stmt = stmt.where(AdminAuditLog.action == action)
        if entity_type:
            stmt = stmt.where(AdminAuditLog.entity_type == entity_type)
        if start is not None:
            stmt = stmt.where(AdminAuditLog.created_at >= start)
        if end is not None:
            stmt = stmt.where(AdminAuditLog.created_at < end)
        stmt = stmt.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id)
        return await self._page(stmt, page, page_size)  # type: ignore[return-value]

    # --- HU-15b ---------------------------------------------------------------------------

    async def queue_snapshot(self, now: datetime, hour_ago: datetime) -> dict[str, Any]:
        """#43: estado de la cola. Cuenta todo (también lo privado): son números, no contenido."""
        c = Classification
        queued_ = c.status == ClassificationStatus.QUEUED
        processing_ = c.status == ClassificationStatus.PROCESSING
        recent = c.finished_at >= hour_ago
        done_ = and_(c.status == ClassificationStatus.DONE, recent)
        error_ = and_(c.status == ClassificationStatus.ERROR, recent)
        alive = and_(processing_, c.heartbeat_at >= now - timedelta(minutes=2))
        counts = await self.session.execute(
            select(
                func.count(case((queued_, 1))),
                func.count(case((processing_, 1))),
                func.min(case((queued_, c.created_at))),
                func.avg(case((done_, func.extract("epoch", c.finished_at - c.started_at)))),
                func.count(case((done_, 1))),
                func.count(case((error_, 1))),
                func.count(case((alive, 1))),
            ).where(c.is_deleted.is_(False))
        )
        queued, processing, oldest, avg, done, error, busy = counts.one()
        owners = await self.session.execute(
            select(c.owner_user_id, c.anon_session_id, User.full_name, func.count())
            .outerjoin(User, User.id == c.owner_user_id)
            .where(c.status == ClassificationStatus.QUEUED, c.is_deleted.is_(False))
            .group_by(c.owner_user_id, c.anon_session_id, User.full_name)
            .order_by(func.count().desc())
            .limit(20)
        )
        return {
            "queued": int(queued),
            "processing": int(processing),
            "busy": int(busy),
            "oldest_queued_at": oldest,
            "avg_processing_seconds": round(float(avg), 1) if avg is not None else None,
            "last_hour": {"done": int(done), "error": int(error)},
            "by_owner": [(user_id, anon_id, name, int(n)) for user_id, anon_id, name, n in owners],
        }

    async def unlisted_suggestions(self, scope: AdminScope) -> list[Classification]:
        """#44 (CB-65): validaciones ``correct_unlisted`` de lo anónimo y público."""
        stmt = (
            select(Classification)
            .where(
                classification_scope(scope),
                Classification.is_deleted.is_(False),
                Classification.validation_status == ValidationStatus.CORRECTED_UNLISTED,
                Classification.suggested_name.is_not(None),
            )
            .order_by(Classification.validated_at, Classification.id)
        )
        return list(await self.session.scalars(stmt))

    async def export_classifications(
        self,
        scope: AdminScope,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[tuple[Classification, CameraStation, str | None]]:
        """#42: filas de la hoja *Clasificaciones* (sin privados), con su cámara y su dueño."""
        stmt = (
            select(Classification, CameraStation, User.full_name)
            .join(CameraStation, CameraStation.id == Classification.camera_station_id)
            .outerjoin(User, User.id == Classification.owner_user_id)
            .where(
                classification_scope(scope),
                Classification.is_deleted.is_(False),
                Classification.status.in_((ClassificationStatus.DONE, ClassificationStatus.ERROR)),
            )
            .order_by(Classification.captured_at, Classification.id)
            .limit(limit)
        )
        if start is not None:
            stmt = stmt.where(Classification.captured_at >= start.replace(tzinfo=None))
        if end is not None:
            stmt = stmt.where(Classification.captured_at < end.replace(tzinfo=None))
        rows = await self.session.execute(stmt)
        return [(row, camera, name) for row, camera, name in rows]
