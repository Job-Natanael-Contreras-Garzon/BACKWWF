"""Panel admin MVP (HU-15a, FL-40..44). Reglas que no se negocian:

- ``AdminScope``: el admin ve lo anónimo y lo público de usuarios; lo privado solo como conteo y
  por id responde 404 (CB-96).
- Toda acción que cambia algo exige ``reason`` y queda en ``admin_audit_log`` (CA-3).
- Restaurar devuelve solo lo que se borró en esa misma operación (mismo ``deleted_at`` y autor).
"""

import asyncio
import secrets
import unicodedata
import uuid
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from math import ceil
from pathlib import Path
from typing import Any

from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.enums import (
    AdminAction,
    AnonSessionStatus,
    EmailType,
    UserRole,
)
from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.core.geo import round_1km
from app.core.logging import log_step, request_id_var
from app.core.responses import Pagination
from app.core.security import hash_token
from app.db.uow import UnitOfWork
from app.integrations.queue import TaskQueue
from app.integrations.storage.base import StorageBackend
from app.models.admin import AdminAuditLog, SystemSetting
from app.models.anon_session import AnonSession
from app.models.camera_station import CameraStation
from app.models.classification import Classification
from app.models.project import Project
from app.models.user import PasswordResetToken, User
from app.reports import excel
from app.repositories.admin import AdminScope, classification_scope, scope_filter
from app.repositories.stats import StatsScope
from app.schemas.admin import (
    AdminAnonSession,
    AdminCamera,
    AdminClassification,
    AdminEntity,
    AdminOwner,
    AdminSettings,
    AdminStats,
    AdminUser,
    AuditEntry,
    CascadeCounts,
    DeleteBatchResult,
    DeleteResult,
    EmailQuota,
    QueueOwner,
    QueueStatus,
    QueueWorkers,
    ResetLink,
    RestoreResult,
    SettingValue,
    Skipped,
    UnlistedSuggestion,
)
from app.schemas.auth import UserRead
from app.schemas.stats import StatsFilters
from app.services import media_validator
from app.services.classification_service import build_filters, to_read
from app.services.stats_service import compute

RETENTION_KEY = "anon_data_retention"
_NOT_FOUND = {
    "classifications": ("CLASSIFICATION_NOT_FOUND", "No encontramos esa clasificación."),
    "camera-stations": ("CAMERA_NOT_FOUND", "No encontramos esa cámara."),
    "projects": ("PROJECT_NOT_FOUND", "No encontramos ese proyecto."),
    "anon-sessions": ("ANON_SESSION_NOT_FOUND", "No encontramos esa sesión anónima."),
}


def anon_label(session_id: uuid.UUID) -> str:
    """Nombre visible de una sesión anónima: nunca el token, solo 4 caracteres del id."""
    return f"Anónimo #{session_id.hex[:4]}"


def _bounds(start: date | None, end: date | None) -> tuple[datetime | None, datetime | None]:
    return (
        datetime.combine(start, time.min, UTC) if start else None,
        datetime.combine(end + timedelta(days=1), time.min, UTC) if end else None,
    )


def _reason(reason: str | None) -> str:
    if not reason or len(reason.strip()) < 3:
        raise BusinessRuleError(
            "DELETE_REASON_REQUIRED",
            "Indica el motivo (mínimo 3 caracteres).",
            details=[{"field": "reason"}],
        )
    return reason.strip()


def _audit(
    uow: UnitOfWork,
    admin: User,
    action: AdminAction,
    entity_type: str,
    entity_id: str | None,
    *,
    old: Any = None,
    new: Any = None,
    reason: str | None = None,
) -> None:
    uow.audit_log.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old,
            new_value=new,
            reason=reason,
            request_id=request_id_var.get(),
        )
    )


def _page(page: int, page_size: int, total: int) -> Pagination:
    size = max(1, min(page_size, 200))
    return Pagination(
        page=page, page_size=size, total=total, total_pages=ceil(total / size) if total else 0
    )


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else 0


# --- estadísticas (#36) -----------------------------------------------------------------------


async def stats(
    uow: UnitOfWork,
    *,
    scope: AdminScope,
    start: date | None,
    end: date | None,
    include_deleted: bool,
) -> AdminStats:
    with log_step("admin.stats"):
        created_from, created_to = _bounds(start, end)
        classifications = await uow.admin.classification_counts()
        evidence_bytes = await asyncio.to_thread(
            _dir_size, Path(settings.STORAGE_LOCAL_PATH) / "evidence"
        )
        content = {
            "camera_stations": await uow.admin.content_counts(CameraStation),
            "projects": await uow.admin.content_counts(Project),
            "classifications": {
                k: classifications[k] for k in ("total", "by_source", "errors_by_code")
            },
            "storage": {
                "evidence_files": classifications["evidence_files"],
                "evidence_gb": round(evidence_bytes / 1024**3, 3),
            },
        }
        retention = {
            "current": await uow.settings.get_value(RETENTION_KEY, True),
            **await uow.admin.retention(),
        }
        cameras = await uow.admin.scoped_cameras(scope, include_deleted=include_deleted)
        filters = StatsFilters(from_=start, to=end)
        fauna = await compute(  # CA-1: nunca entra lo privado; cada archivo cuenta una vez
            uow,
            cameras,
            filters,
            scope="platform",
            scope_id=None,
            scope_name="Plataforma",
            sections=("totals", "richness", "non_animal", "taxa", "by_month", "by_hour"),
            dedup_sha256=True,
        )
        fauna_map = await _fauna_map(uow, cameras, filters)
        return AdminStats(
            users=await uow.admin.user_counts(created_from, created_to),
            anon_sessions=await uow.admin.anon_counts(),
            content=content,
            model_feedback=await uow.admin.model_feedback(scope),
            anon_retention=retention,
            fauna=fauna,
            fauna_map=fauna_map,
        )


async def _fauna_map(
    uow: UnitOfWork, cameras: list[CameraStation], filters: StatsFilters
) -> list[dict[str, Any]]:
    from app.services.stats_service import date_bounds

    start, end = date_bounds(filters)
    rows = await uow.stats.by_camera(
        StatsScope(camera_ids=[c.id for c in cameras], start=start, end=end, dedup_sha256=True)
    )
    per_camera: dict[uuid.UUID, int] = {}
    for camera_id, _label, count in rows:
        per_camera[camera_id] = per_camera.get(camera_id, 0) + int(count)
    points: dict[tuple[float, float, str], int] = {}
    for camera in cameras:
        if not per_camera.get(camera.id):
            continue
        key = (
            round_1km(camera.latitude),
            round_1km(camera.longitude),
            "anonymous" if camera.anon_session_id else "public",
        )
        points[key] = points.get(key, 0) + per_camera[camera.id]
    return [
        {"latitude": lat, "longitude": lng, "sightings": n, "scope": scope}
        for (lat, lng, scope), n in sorted(points.items(), key=lambda kv: -kv[1])
    ]


# --- exploración (#37, #38) -------------------------------------------------------------------


async def list_cameras(
    uow: UnitOfWork,
    *,
    scope: AdminScope,
    q: str | None,
    anon_session_id: uuid.UUID | None,
    include_deleted: bool,
    page: int,
    page_size: int,
) -> tuple[list[AdminCamera], Pagination]:
    cameras, total = await uow.admin.list_cameras(
        scope,
        q=q,
        anon_session_id=anon_session_id,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
    )
    names = await uow.camera_stations.user_profiles(
        {c.owner_user_id for c in cameras if c.owner_user_id}
    )
    items = []
    for c in cameras:
        anonymous = c.anon_session_id is not None
        # §13: lo anónimo va exacto (es de la plataforma); lo público de usuarios, redondeado.
        lat = float(c.latitude) if anonymous else round_1km(c.latitude)
        lng = float(c.longitude) if anonymous else round_1km(c.longitude)
        owner = (
            AdminOwner(type="anonymous", display_name=anon_label(c.anon_session_id))
            if c.anon_session_id
            else AdminOwner(
                type="user",
                display_name=names.get(c.owner_user_id, ("Usuario", None))[0]
                if c.owner_user_id
                else "Usuario",
            )
        )
        items.append(
            AdminCamera(
                id=c.id,
                code=c.code,
                name=c.name,
                latitude=lat,
                longitude=lng,
                location_precision="exact" if anonymous else "approx_1km",
                visibility=c.visibility,
                deployed_at=c.deployed_at,
                retrieved_at=c.retrieved_at,
                still_installed=c.still_installed,
                owner=owner,
                anon_session_id=c.anon_session_id,
                is_deleted=c.is_deleted,
                deleted_at=c.deleted_at,
                deleted_reason=c.deleted_reason,
                created_at=c.created_at,
            )
        )
    return items, _page(page, page_size, total)


async def list_classifications(
    uow: UnitOfWork,
    *,
    scope: AdminScope,
    anon_session_id: uuid.UUID | None,
    camera_station_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    include_deleted: bool,
    filters: dict[str, Any],
    page: int,
    page_size: int,
) -> tuple[list[AdminClassification], Pagination]:
    """§13.3: los mismos filtros de §8.1 (``build_filters``) + ``scope``, sesión anónima y
    borrados. Un proyecto privado responde 404, como cualquier recurso privado (CB-96)."""
    camera_ids: list[uuid.UUID] | None = None
    if camera_station_id is not None:
        camera_ids = [camera_station_id]
    if project_id is not None:
        in_project = await uow.admin.scoped_project_camera_ids(project_id)
        if in_project is None:
            raise NotFoundError(*_NOT_FOUND["projects"])
        camera_ids = [c for c in in_project if camera_ids is None or c in camera_ids]
    query = build_filters(camera_ids=camera_ids, **filters)
    rows, total = await uow.admin.list_classifications(
        scope,
        query,
        anon_session_id=anon_session_id,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
    )
    items = [
        AdminClassification(
            **to_read(r).model_dump(),
            is_deleted=r.is_deleted,
            deleted_at=r.deleted_at,
            deleted_reason=r.deleted_reason,
            owner_type="anonymous" if r.anon_session_id else "user",
        )
        for r in rows
    ]
    return items, _page(page, page_size, total)


async def evidence(uow: UnitOfWork, storage: StorageBackend, classification_id: uuid.UUID) -> bytes:
    """#38: misma matriz que el resto del panel: lo privado → 404 (CB-96)."""
    row = await uow.admin.scoped_classification(classification_id)
    if row is None or row.evidence_key is None:
        raise NotFoundError(*_NOT_FOUND["classifications"])
    try:
        return await storage.get(row.evidence_key)
    except FileNotFoundError as exc:
        raise NotFoundError(*_NOT_FOUND["classifications"]) from exc


async def list_anon_sessions(
    uow: UnitOfWork,
    *,
    status: AnonSessionStatus | None,
    start: date | None,
    end: date | None,
    page: int,
    page_size: int,
) -> tuple[list[AdminAnonSession], Pagination]:
    created_from, created_to = _bounds(start, end)
    sessions, total = await uow.admin.list_anon_sessions(
        status, created_from, created_to, page, page_size
    )
    counts = await uow.admin.anon_session_counts([s.id for s in sessions])
    items = [
        AdminAnonSession(
            id=s.id,
            label=anon_label(s.id),
            status=s.status,
            created_at=s.created_at,
            last_activity_at=s.last_activity_at,
            counts={k: v for k, v in counts[s.id].items() if k != "retained"},
            retained=bool(counts[s.id]["retained"]),
            is_deleted=s.is_deleted,
        )
        for s in sessions
    ]
    return items, _page(page, page_size, total)


# --- borrado y restauración (#39) -------------------------------------------------------------


async def _target(uow: UnitOfWork, entity: AdminEntity, entity_id: uuid.UUID) -> Any:
    model: Any
    if entity == "anon-sessions":
        row: Any = await uow.session.get(AnonSession, entity_id)
    else:
        model, condition = {
            "classifications": (Classification, classification_scope("all")),
            "camera-stations": (CameraStation, scope_filter(CameraStation, "all")),
            "projects": (Project, scope_filter(Project, "all")),
        }[entity]
        row = await uow.session.scalar(
            select(model).where(model.id == entity_id, condition).with_for_update()
        )
    if row is None:  # privado o inexistente: lo mismo para el admin (CB-96)
        raise NotFoundError(*_NOT_FOUND[entity])
    return row


async def _mark(uow: UnitOfWork, model: Any, condition: Any, values: dict[str, Any]) -> int:
    result = await uow.session.execute(
        update(model).where(condition).values(**values).execution_options(synchronize_session=False)
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def _delete_one(
    uow: UnitOfWork,
    admin: User,
    entity: AdminEntity,
    entity_id: uuid.UUID,
    reason: str,
    now: datetime,
    tmp_keys: list[str],
) -> CascadeCounts:
    row = await _target(uow, entity, entity_id)
    if row.is_deleted:
        raise ConflictError("ENTITY_ALREADY_DELETED", "Ya estaba eliminado.")
    mark = {"is_deleted": True, "deleted_at": now, "deleted_by": admin.id, "deleted_reason": reason}
    live = Classification.is_deleted.is_(False)
    counts = CascadeCounts()
    if entity == "classifications":
        tmp_keys += await uow.admin.cancel_queued(Classification.id == row.id, "CANCELLED_BY_USER")
        counts.classifications = await _mark(uow, Classification, Classification.id == row.id, mark)
    elif entity == "camera-stations":
        of_camera = and_(Classification.camera_station_id == row.id, live)
        tmp_keys += await uow.admin.cancel_queued(of_camera, "CAMERA_DELETED")
        counts.classifications = await _mark(uow, Classification, of_camera, mark)
        counts.camera_stations = await _mark(uow, CameraStation, CameraStation.id == row.id, mark)
    elif entity == "projects":
        counts.projects = await _mark(uow, Project, Project.id == row.id, mark)
    else:  # anon-sessions: todo lo suyo (CB-98)
        mine = and_(Classification.anon_session_id == row.id, live)
        tmp_keys += await uow.admin.cancel_queued(mine, "ANON_SESSION_EXPIRED")
        counts.classifications = await _mark(uow, Classification, mine, mark)
        counts.camera_stations = await _mark(
            uow,
            CameraStation,
            and_(CameraStation.anon_session_id == row.id, CameraStation.is_deleted.is_(False)),
            mark,
        )
        counts.projects = await _mark(
            uow,
            Project,
            and_(Project.anon_session_id == row.id, Project.is_deleted.is_(False)),
            mark,
        )
        row.is_deleted, row.deleted_at, row.deleted_by, row.deleted_reason = (
            True,
            now,
            admin.id,
            reason,
        )
        row.status = AnonSessionStatus.EXPIRED  # su token deja de servir
    _audit(
        uow,
        admin,
        AdminAction.SOFT_DELETE,
        entity,
        str(row.id),
        new=counts.model_dump(),
        reason=reason,
    )
    return counts


async def _discard(tmp_keys: list[str]) -> None:
    for key in tmp_keys:
        await media_validator.discard(Path(settings.TMP_UPLOAD_PATH) / key)


async def delete(
    uow: UnitOfWork, admin: User, entity: AdminEntity, entity_id: uuid.UUID, reason: str | None
) -> DeleteResult:
    with log_step("admin.delete", entity=entity):
        why = _reason(reason)
        tmp_keys: list[str] = []
        counts = await _delete_one(uow, admin, entity, entity_id, why, datetime.now(UTC), tmp_keys)
        await uow.commit()
        await _discard(tmp_keys)
        return DeleteResult(deleted=counts)


async def delete_batch(
    uow: UnitOfWork,
    admin: User,
    entity: AdminEntity,
    ids: list[uuid.UUID],
    reason: str | None,
) -> DeleteBatchResult:
    with log_step("admin.delete_batch", entity=entity, count=len(ids)):
        why = _reason(reason)
        now = datetime.now(UTC)
        total = CascadeCounts()
        skipped: list[Skipped] = []
        tmp_keys: list[str] = []
        for entity_id in dict.fromkeys(ids):
            try:
                counts = await _delete_one(uow, admin, entity, entity_id, why, now, tmp_keys)
            except (NotFoundError, ConflictError) as exc:
                skipped.append(Skipped(id=entity_id, code=exc.code))
                continue
            total.classifications += counts.classifications
            total.camera_stations += counts.camera_stations
            total.projects += counts.projects
        await uow.commit()
        await _discard(tmp_keys)
        return DeleteBatchResult(deleted=total, skipped=skipped)


async def restore(
    uow: UnitOfWork, admin: User, entity: AdminEntity, entity_id: uuid.UUID, reason: str | None
) -> RestoreResult:
    """Solo vuelve lo que cayó en la misma operación (mismo ``deleted_at`` y autor)."""
    with log_step("admin.restore", entity=entity):
        row = await _target(uow, entity, entity_id)
        if not row.is_deleted:
            raise ConflictError("ENTITY_NOT_DELETED", "No está eliminado.")
        same_op = {"deleted_at": row.deleted_at, "deleted_by": row.deleted_by}
        clear = {
            "is_deleted": False,
            "deleted_at": None,
            "deleted_by": None,
            "deleted_reason": None,
        }

        def batch(model: Any, owner_condition: Any) -> Any:
            return and_(
                owner_condition,
                model.is_deleted.is_(True),
                model.deleted_at == same_op["deleted_at"],
                model.deleted_by == same_op["deleted_by"],
            )

        counts = CascadeCounts()
        try:
            if entity == "classifications":
                counts.classifications = await _mark(
                    uow, Classification, Classification.id == row.id, clear
                )
            elif entity == "camera-stations":
                counts.classifications = await _mark(
                    uow,
                    Classification,
                    batch(Classification, Classification.camera_station_id == row.id),
                    clear,
                )
                counts.camera_stations = await _mark(
                    uow, CameraStation, CameraStation.id == row.id, clear
                )
            elif entity == "projects":
                counts.projects = await _mark(uow, Project, Project.id == row.id, clear)
            else:
                counts.classifications = await _mark(
                    uow,
                    Classification,
                    batch(Classification, Classification.anon_session_id == row.id),
                    clear,
                )
                counts.camera_stations = await _mark(
                    uow,
                    CameraStation,
                    batch(CameraStation, CameraStation.anon_session_id == row.id),
                    clear,
                )
                counts.projects = await _mark(
                    uow, Project, batch(Project, Project.anon_session_id == row.id), clear
                )
                row.is_deleted, row.deleted_at, row.deleted_by, row.deleted_reason = (
                    False,
                    None,
                    None,
                    None,
                )
            _audit(
                uow,
                admin,
                AdminAction.RESTORE,
                entity,
                str(row.id),
                new=counts.model_dump(),
                reason=reason,
            )
            await uow.commit()
        except IntegrityError as exc:  # el mismo archivo ya volvió a subirse en esa cámara
            raise ConflictError(
                "DUPLICATE_FILE", "No se puede restaurar: el archivo ya existe en esa cámara."
            ) from exc
        return RestoreResult(restored=counts)


# --- usuarios (#40) ---------------------------------------------------------------------------


async def list_users(
    uow: UnitOfWork, *, q: str | None, status: str | None, page: int, page_size: int
) -> tuple[list[AdminUser], Pagination]:
    active = {"active": True, "disabled": False}.get(status or "")
    users, total = await uow.admin.list_users(q, active, page, page_size)
    counts = await uow.admin.user_content_counts([u.id for u in users])
    items = [
        AdminUser(**UserRead.model_validate(u).model_dump(), counts=counts[u.id]) for u in users
    ]
    return items, _page(page, page_size, total)


async def _user(uow: UnitOfWork, user_id: uuid.UUID) -> User:
    user = await uow.users.get(user_id)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", "No encontramos ese usuario.")
    return user


async def deactivate(
    uow: UnitOfWork, admin: User, user_id: uuid.UUID, reason: str | None
) -> UserRead:
    """CB-97/CB-99: no puede desactivarse a sí mismo; se cortan sus sesiones y su cola."""
    with log_step("admin.user.deactivate"):
        if user_id == admin.id:
            raise ConflictError("CANNOT_DEACTIVATE_SELF", "No puedes desactivar tu propia cuenta.")
        why = _reason(reason)
        user = await _user(uow, user_id)
        was = user.is_active
        user.is_active = False
        await uow.refresh_tokens.revoke_all_for_user(user.id, datetime.now(UTC))
        tmp_keys = await uow.admin.cancel_queued(
            Classification.owner_user_id == user.id, "ACCOUNT_DISABLED"
        )
        _audit(
            uow,
            admin,
            AdminAction.DEACTIVATE_USER,
            "users",
            str(user.id),
            old={"is_active": was},
            new={"is_active": False},
            reason=why,
        )
        await uow.commit()
        await _discard(tmp_keys)
        await uow.users.refresh(user)
        return UserRead.model_validate(user)


async def reactivate(
    uow: UnitOfWork, admin: User, user_id: uuid.UUID, reason: str | None
) -> UserRead:
    with log_step("admin.user.reactivate"):
        user = await _user(uow, user_id)
        was = user.is_active
        user.is_active = True
        _audit(
            uow,
            admin,
            AdminAction.REACTIVATE_USER,
            "users",
            str(user.id),
            old={"is_active": was},
            new={"is_active": True},
            reason=reason,
        )
        await uow.commit()
        await uow.users.refresh(user)
        return UserRead.model_validate(user)


async def password_reset_link(
    uow: UnitOfWork, admin: User, user_id: uuid.UUID, reason: str | None
) -> ResetLink:
    """CB-76: respaldo cuando no hay correo. El admin no ve ni fija la contraseña; el enlace no
    se guarda en la auditoría ni en los logs (solo su vencimiento)."""
    with log_step("admin.user.reset_link"):
        why = _reason(reason)
        user = await _user(uow, user_id)
        if user.role == UserRole.ADMIN:
            raise ForbiddenError("FORBIDDEN", "La cuenta admin se recupera con la CLI.")
        now = datetime.now(UTC)
        await uow.password_reset_tokens.invalidate_pending_for_user(user.id, now)
        token = secrets.token_urlsafe(32)
        expires = now + timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES)
        uow.password_reset_tokens.add(
            PasswordResetToken(user_id=user.id, token_hash=hash_token(token), expires_at=expires)
        )
        _audit(
            uow,
            admin,
            AdminAction.PASSWORD_RESET_LINK,
            "users",
            str(user.id),
            new={"expires_at": expires.isoformat()},
            reason=why,
        )
        await uow.commit()
        url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/restablecer?token={token}"
        return ResetLink(reset_url=url, expires_at=expires)


# --- configuración (#41) ----------------------------------------------------------------------


async def get_settings(uow: UnitOfWork) -> AdminSettings:
    row = await uow.session.get(SystemSetting, RETENTION_KEY)
    updated_by = None
    if row is not None and row.updated_by is not None:
        who = await uow.users.get(row.updated_by)
        updated_by = who.email if who else None
    return AdminSettings(
        anon_data_retention=SettingValue(
            value=row.value if row is not None else True,
            updated_by=updated_by,
            updated_at=row.updated_at if row is not None else None,
        )
    )


async def update_settings(
    uow: UnitOfWork, admin: User, value: Any, reason: str | None
) -> AdminSettings:
    """CB-43: el cambio solo afecta lo que se cree después (cada fila guardó su anon_retain)."""
    with log_step("admin.settings.update"):
        if not isinstance(value, bool):
            raise BusinessRuleError(
                "SETTING_INVALID",
                "anon_data_retention debe ser true o false.",
                details=[{"field": RETENTION_KEY}],
            )
        why = _reason(reason)
        row = await uow.session.get(SystemSetting, RETENTION_KEY, with_for_update=True)
        old = row.value if row is not None else None
        if row is None:
            row = SystemSetting(key=RETENTION_KEY, value=value, updated_by=admin.id)
            uow.session.add(row)
        else:
            row.value, row.updated_by = value, admin.id
        _audit(
            uow,
            admin,
            AdminAction.UPDATE_SETTING,
            "system_settings",
            RETENTION_KEY,
            old=old,
            new=value,
            reason=why,
        )
        await uow.commit()
        await uow.session.refresh(row)  # updated_at lo pone la BD
        return await get_settings(uow)


# --- auditoría (#42) --------------------------------------------------------------------------


async def audit_log(
    uow: UnitOfWork,
    *,
    action: str | None,
    entity_type: str | None,
    start: date | None,
    end: date | None,
    page: int,
    page_size: int,
) -> tuple[list[AuditEntry], Pagination]:
    created_from, created_to = _bounds(start, end)
    rows, total = await uow.admin.list_audit(
        action, entity_type, created_from, created_to, page, page_size
    )
    items = [
        AuditEntry(
            id=r.id,
            action=str(r.action),
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            old_value=r.old_value,
            new_value=r.new_value,
            reason=r.reason,
            created_at=r.created_at,
            request_id=r.request_id,
        )
        for r in rows
    ]
    return items, _page(page, page_size, total)


# --- HU-15b: cola (#43), sugerencias no catalogadas (#44) y Excel global (#42) ---------------


async def queue_status(uow: UnitOfWork, queue: TaskQueue) -> QueueStatus:
    with log_step("admin.queue"):
        now = datetime.now(UTC)
        snap = await uow.admin.queue_snapshot(now, now - timedelta(hours=1))
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        oldest = snap["oldest_queued_at"]
        return QueueStatus(
            workers=QueueWorkers(
                alive=await queue.workers_alive(),
                concurrency=settings.WORKER_CONCURRENCY,
                busy=snap["busy"],
            ),
            queued=snap["queued"],
            processing=snap["processing"],
            avg_processing_seconds=snap["avg_processing_seconds"],
            oldest_queued_age_seconds=int((now - oldest).total_seconds()) if oldest else None,
            by_owner=[
                QueueOwner(label=anon_label(anon) if anon else (name or "Usuario"), queued=n)
                for _user, anon, name, n in snap["by_owner"]
            ],
            last_hour=snap["last_hour"],
            email=EmailQuota(
                sent_today=await uow.email_log.count_since(EmailType.PASSWORD_RESET, day),
                daily_cap=settings.EMAIL_DAILY_CAP,
                sent_month=await uow.email_log.count_since(
                    EmailType.PASSWORD_RESET, day.replace(day=1)
                ),
                monthly_cap=settings.EMAIL_MONTHLY_CAP,
            ),
        )


def normalize_name(name: str) -> str:
    """CB-65: "Leopardus  Colocolo" y "leopardus colócolo" son la misma sugerencia."""
    plain = "".join(
        ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch)
    )
    return " ".join(plain.lower().split())


async def unlisted_suggestions(uow: UnitOfWork, scope: AdminScope) -> list[UnlistedSuggestion]:
    with log_step("admin.unlisted_suggestions"):
        groups: dict[str, list[Classification]] = {}
        for row in await uow.admin.unlisted_suggestions(scope):
            groups.setdefault(normalize_name(row.suggested_name or ""), []).append(row)
        result = []
        for name, rows in groups.items():
            parents = Counter(
                r.corrected_scientific_name for r in rows if r.corrected_scientific_name
            )
            dates = [r.validated_at for r in rows if r.validated_at]
            result.append(
                UnlistedSuggestion(
                    suggested_name=name,
                    count=len(rows),
                    parent_taxon=parents.most_common(1)[0][0] if parents else None,
                    first_at=min(dates) if dates else None,
                    last_at=max(dates) if dates else None,
                    classification_ids=[r.id for r in rows],
                )
            )
        return sorted(result, key=lambda s: (-s.count, s.suggested_name))


EXPORT_MAX_ROWS = 200_000  # muy por debajo del límite de Excel (1 048 576 filas)


async def excel_report(
    uow: UnitOfWork,
    admin: User,
    *,
    scope: AdminScope,
    start: date | None,
    end: date | None,
) -> tuple[bytes, str]:
    """#42: hojas Plataforma, Fauna por especie/género/familia, Clasificaciones y Sugerencias.

    Nunca entra lo privado; lo anónimo sale como "Anónimo #xxxx" y lo público de usuarios con la
    ubicación redondeada (como en el resto del panel). Queda en la auditoría (``export``).
    """
    with log_step("admin.report.excel"):
        data = await stats(uow, scope=scope, start=start, end=end, include_deleted=False)
        fauna = data.fauna
        captured_from, captured_to = _bounds(start, end)
        rows = await uow.admin.export_classifications(
            scope, captured_from, captured_to, EXPORT_MAX_ROWS
        )
        suggestions = await unlisted_suggestions(uow, scope)
        _audit(
            uow,
            admin,
            AdminAction.EXPORT,
            "reports",
            "admin_excel",
            new={
                "scope": scope,
                "from": str(start) if start else None,
                "to": str(end) if end else None,
                "rows": len(rows),
            },
        )
        await uow.commit()
        content = await asyncio.to_thread(
            excel.build,
            [
                ("Plataforma", ["Indicador", "Valor"], _platform_rows(data)),
                (
                    "Fauna por especie",
                    [
                        "Nombre científico",
                        "Nombre común",
                        "Género",
                        "Familia",
                        "Avistamientos",
                        "%",
                        "Validados",
                        "Confianza media",
                        "Primera fecha",
                        "Última fecha",
                        "N.º de cámaras",
                    ],
                    [
                        [
                            s.scientific_name,
                            s.common_name,
                            s.genus,
                            s.family,
                            s.count,
                            s.pct,
                            s.validated,
                            s.mean_confidence,
                            s.first_seen,
                            s.last_seen,
                            s.camera_stations,
                        ]
                        for s in fauna.by_species or []
                    ],
                ),
                (
                    "Por género",
                    ["Género", "Familia", "Avistamientos", "%"],
                    [[g.name, g.family, g.count, g.pct] for g in fauna.by_genus or []],
                ),
                (
                    "Por familia",
                    ["Familia", "Avistamientos", "%"],
                    [[f.name, f.count, f.pct] for f in fauna.by_family or []],
                ),
                (
                    "Clasificaciones",
                    [
                        "Dueño",
                        "Archivo",
                        "Código de cámara",
                        "Latitud",
                        "Longitud",
                        "Precisión",
                        "Fecha de captura",
                        "Categoría",
                        "Especie (IA)",
                        "Género (IA)",
                        "Familia (IA)",
                        "Confianza",
                        "Estado de validación",
                        "Especie validada",
                        "Origen",
                        "Error",
                    ],
                    [_export_row(row, camera, name) for row, camera, name in rows],
                ),
                (
                    "Sugerencias",
                    ["Nombre sugerido", "Veces", "Taxón superior", "Primera vez", "Última vez"],
                    [
                        [s.suggested_name, s.count, s.parent_taxon, s.first_at, s.last_at]
                        for s in suggestions
                    ],
                ),
            ],
        )
        name = f"WWM_admin_{scope}_{datetime.now(UTC):%Y%m%d}.xlsx"
        return content, name


def _platform_rows(data: AdminStats) -> list[list[Any]]:
    rows: list[list[Any]] = []

    def flat(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, inner in value.items():
                flat(f"{prefix}.{key}" if prefix else str(key), inner)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and "month" in item:
                    rows.append([f"{prefix}.{item['month']}", item.get("count")])
        else:
            rows.append([prefix, value])

    for section in ("users", "anon_sessions", "content", "anon_retention", "model_feedback"):
        flat(section, getattr(data, section))
    return rows


def _export_row(row: Classification, camera: CameraStation, owner_name: str | None) -> list[Any]:
    anonymous = row.anon_session_id is not None
    corrected = row.corrected_scientific_name or row.suggested_name
    return [
        anon_label(row.anon_session_id) if row.anon_session_id else (owner_name or "Usuario"),
        row.file_name,
        camera.code,
        float(camera.latitude) if anonymous else round_1km(camera.latitude),
        float(camera.longitude) if anonymous else round_1km(camera.longitude),
        "exacta" if anonymous else "~1 km",
        row.captured_at,
        row.category.value if row.category else row.status.value,
        row.scientific_name if row.species else None,
        row.genus,
        row.family,
        float(row.confidence) if row.confidence is not None else None,
        row.validation_status.value,
        corrected,
        row.source.value,
        row.error_code,
    ]
