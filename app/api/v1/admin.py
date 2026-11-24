"""Panel admin MVP (HU-15a). Solo HTTP: la matriz ``AdminScope`` vive en el servicio/repo."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import AdminDep, StorageDep, UoWDep
from app.core.enums import AnonSessionStatus, ClassificationSource
from app.core.logging import flow
from app.core.responses import ApiResponse, ok
from app.integrations.queue import TaskQueue, get_task_queue
from app.repositories.admin import AdminScope
from app.schemas.admin import (
    AdminAnonSession,
    AdminCamera,
    AdminClassification,
    AdminEntity,
    AdminSettings,
    AdminStats,
    AdminUser,
    AuditEntry,
    DeleteBatchBody,
    DeleteBatchResult,
    DeleteResult,
    QueueStatus,
    ReasonBody,
    ResetLink,
    RestoreResult,
    SettingsUpdate,
    UnlistedSuggestion,
)
from app.schemas.auth import UserRead
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["Admin"])

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]
From = Annotated[date | None, Query(alias="from")]
To = Annotated[date | None, Query()]
Confidence = Annotated[float | None, Query(ge=0, le=1)]


@router.get("/stats", response_model=ApiResponse[AdminStats], dependencies=[Depends(flow("FL-40"))])
async def stats(
    uow: UoWDep,
    _admin: AdminDep,
    scope: AdminScope = "all",
    from_: From = None,
    to: To = None,
    include_deleted: bool = False,
) -> ApiResponse[AdminStats]:
    data = await admin_service.stats(
        uow, scope=scope, start=from_, end=to, include_deleted=include_deleted
    )
    return ok(data)


@router.get(
    "/camera-stations",
    response_model=ApiResponse[list[AdminCamera]],
    dependencies=[Depends(flow("FL-41"))],
)
async def list_cameras(
    uow: UoWDep,
    _admin: AdminDep,
    scope: AdminScope = "all",
    q: Annotated[str | None, Query(max_length=100)] = None,
    anon_session_id: uuid.UUID | None = None,
    include_deleted: bool = False,
    page: Page = 1,
    page_size: PageSize = 50,
) -> ApiResponse[list[AdminCamera]]:
    items, pagination = await admin_service.list_cameras(
        uow,
        scope=scope,
        q=q,
        anon_session_id=anon_session_id,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
    )
    return ok(items, pagination=pagination)


@router.get(
    "/classifications",
    response_model=ApiResponse[list[AdminClassification]],
    dependencies=[Depends(flow("FL-41"))],
)
async def list_classifications(
    uow: UoWDep,
    _admin: AdminDep,
    scope: AdminScope = "all",
    anon_session_id: uuid.UUID | None = None,
    camera_station_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    status: Literal["done", "error", "all"] = "done",
    category: str | None = None,
    validation_status: str | None = None,
    taxon: Annotated[str | None, Query(max_length=64)] = None,
    min_confidence: Confidence = None,
    max_confidence: Confidence = None,
    from_: From = None,
    to: To = None,
    source: ClassificationSource | None = None,
    # Por defecto lo más reciente subido (lo que el admin modera); §8.1 ordena por captura.
    sort: Literal["-captured_at", "confidence", "-created_at", "file_name"] = "-created_at",
    include_deleted: bool = False,
    page: Page = 1,
    page_size: PageSize = 50,
) -> ApiResponse[list[AdminClassification]]:
    """§13.3: los filtros de §8.1 + ``scope``, ``anon_session_id`` e ``include_deleted``.
    ``category`` y ``validation_status`` aceptan varios valores separados por coma."""
    items, pagination = await admin_service.list_classifications(
        uow,
        scope=scope,
        anon_session_id=anon_session_id,
        camera_station_id=camera_station_id,
        project_id=project_id,
        include_deleted=include_deleted,
        filters={
            "batch_id": batch_id,
            "status": status,
            "category": category,
            "validation_status": validation_status,
            "taxon": taxon,
            "min_confidence": min_confidence,
            "max_confidence": max_confidence,
            "from_": from_,
            "to": to,
            "source": source,
            "sort": sort,
        },
        page=page,
        page_size=page_size,
    )
    return ok(items, pagination=pagination)


@router.get(
    "/classifications/{classification_id}/evidence",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
    dependencies=[Depends(flow("FL-41"))],
)
async def evidence(
    classification_id: uuid.UUID, uow: UoWDep, storage: StorageDep, _admin: AdminDep
) -> Response:
    data = await admin_service.evidence(uow, storage, classification_id)
    return Response(
        content=data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"}
    )


@router.get(
    "/anon-sessions",
    response_model=ApiResponse[list[AdminAnonSession]],
    dependencies=[Depends(flow("FL-41"))],
)
async def list_anon_sessions(
    uow: UoWDep,
    _admin: AdminDep,
    status: AnonSessionStatus | None = None,
    from_: From = None,
    to: To = None,
    page: Page = 1,
    page_size: PageSize = 50,
) -> ApiResponse[list[AdminAnonSession]]:
    items, pagination = await admin_service.list_anon_sessions(
        uow, status=status, start=from_, end=to, page=page, page_size=page_size
    )
    return ok(items, pagination=pagination)


@router.post(
    "/delete-batch",
    response_model=ApiResponse[DeleteBatchResult],
    dependencies=[Depends(flow("FL-42"))],
)
async def delete_batch(
    body: DeleteBatchBody, uow: UoWDep, admin: AdminDep
) -> ApiResponse[DeleteBatchResult]:
    data = await admin_service.delete_batch(uow, admin, body.entity, body.ids, body.reason)
    return ok(data, message="Eliminación aplicada.")


@router.post(
    "/{entity}/{entity_id}/restore",
    response_model=ApiResponse[RestoreResult],
    dependencies=[Depends(flow("FL-42"))],
)
async def restore(
    entity: AdminEntity,
    entity_id: uuid.UUID,
    uow: UoWDep,
    admin: AdminDep,
    body: ReasonBody | None = None,
) -> ApiResponse[RestoreResult]:
    reason = body.reason if body else None
    data = await admin_service.restore(uow, admin, entity, entity_id, reason)
    return ok(data, message="Restaurado.")


@router.get(
    "/users", response_model=ApiResponse[list[AdminUser]], dependencies=[Depends(flow("FL-43"))]
)
async def list_users(
    uow: UoWDep,
    _admin: AdminDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: Literal["active", "disabled"] | None = None,
    page: Page = 1,
    page_size: PageSize = 50,
) -> ApiResponse[list[AdminUser]]:
    items, pagination = await admin_service.list_users(
        uow, q=q, status=status, page=page, page_size=page_size
    )
    return ok(items, pagination=pagination)


@router.post(
    "/users/{user_id}/deactivate",
    response_model=ApiResponse[UserRead],
    dependencies=[Depends(flow("FL-43"))],
)
async def deactivate(
    user_id: uuid.UUID, body: ReasonBody, uow: UoWDep, admin: AdminDep
) -> ApiResponse[UserRead]:
    data = await admin_service.deactivate(uow, admin, user_id, body.reason)
    return ok(data, message="Cuenta desactivada.")


@router.post(
    "/users/{user_id}/reactivate",
    response_model=ApiResponse[UserRead],
    dependencies=[Depends(flow("FL-43"))],
)
async def reactivate(
    user_id: uuid.UUID, uow: UoWDep, admin: AdminDep, body: ReasonBody | None = None
) -> ApiResponse[UserRead]:
    data = await admin_service.reactivate(uow, admin, user_id, body.reason if body else None)
    return ok(data, message="Cuenta reactivada.")


@router.post(
    "/users/{user_id}/password-reset-link",
    response_model=ApiResponse[ResetLink],
    dependencies=[Depends(flow("FL-43"))],
)
async def password_reset_link(
    user_id: uuid.UUID, body: ReasonBody, uow: UoWDep, admin: AdminDep
) -> ApiResponse[ResetLink]:
    data = await admin_service.password_reset_link(uow, admin, user_id, body.reason)
    return ok(data, message="Enlace generado. Entrégalo al usuario por un canal seguro.")


@router.get(
    "/settings", response_model=ApiResponse[AdminSettings], dependencies=[Depends(flow("FL-44"))]
)
async def get_settings(uow: UoWDep, _admin: AdminDep) -> ApiResponse[AdminSettings]:
    return ok(await admin_service.get_settings(uow))


@router.put(
    "/settings", response_model=ApiResponse[AdminSettings], dependencies=[Depends(flow("FL-44"))]
)
async def update_settings(
    body: SettingsUpdate, uow: UoWDep, admin: AdminDep
) -> ApiResponse[AdminSettings]:
    data = await admin_service.update_settings(uow, admin, body.anon_data_retention, body.reason)
    return ok(data, message="Configuración guardada. Aplica a lo que se cree desde ahora.")


@router.get(
    "/audit-log",
    response_model=ApiResponse[list[AuditEntry]],
    dependencies=[Depends(flow("FL-40"))],
)
async def audit_log(
    uow: UoWDep,
    _admin: AdminDep,
    action: str | None = None,
    entity_type: str | None = None,
    from_: From = None,
    to: To = None,
    page: Page = 1,
    page_size: PageSize = 50,
) -> ApiResponse[list[AuditEntry]]:
    items, pagination = await admin_service.audit_log(
        uow,
        action=action,
        entity_type=entity_type,
        start=from_,
        end=to,
        page=page,
        page_size=page_size,
    )
    return ok(items, pagination=pagination)


@router.get(
    "/queue", response_model=ApiResponse[QueueStatus], dependencies=[Depends(flow("FL-45"))]
)
async def queue_status(
    uow: UoWDep,
    _admin: AdminDep,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
) -> ApiResponse[QueueStatus]:
    """#43 (HU-15b): cola de análisis, worker y cuota de correos."""
    return ok(await admin_service.queue_status(uow, queue))


@router.get(
    "/unlisted-suggestions",
    response_model=ApiResponse[list[UnlistedSuggestion]],
    dependencies=[Depends(flow("FL-46"))],
)
async def unlisted_suggestions(
    uow: UoWDep, _admin: AdminDep, scope: AdminScope = "all"
) -> ApiResponse[list[UnlistedSuggestion]]:
    """#44 (HU-15b, CB-65): nombres sugeridos fuera del catálogo, agrupados."""
    return ok(await admin_service.unlisted_suggestions(uow, scope))


_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/reports/excel",
    response_class=Response,
    responses={200: {"content": {_XLSX: {}}}},
    dependencies=[Depends(flow("FL-40"))],
)
async def excel_report(
    uow: UoWDep,
    admin: AdminDep,
    scope: AdminScope = "all",
    from_: From = None,
    to: To = None,
) -> Response:
    """#42 (HU-15b): Excel global sin datos privados; queda en la auditoría."""
    data, name = await admin_service.excel_report(uow, admin, scope=scope, start=from_, end=to)
    return Response(
        content=data,
        media_type=_XLSX,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post(
    "/{entity}/{entity_id}/delete",
    response_model=ApiResponse[DeleteResult],
    dependencies=[Depends(flow("FL-42"))],
)
async def delete(
    entity: AdminEntity, entity_id: uuid.UUID, body: ReasonBody, uow: UoWDep, admin: AdminDep
) -> ApiResponse[DeleteResult]:
    data = await admin_service.delete(uow, admin, entity, entity_id, body.reason)
    return ok(data, message="Eliminado. Puedes restaurarlo desde el panel.")
