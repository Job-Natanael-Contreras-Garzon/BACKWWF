"""Ráfagas: registros repetidos del mismo animal (§8.8, D10, CB-60..60d, FL-16).

El sistema solo **sugiere**: por defecto cada archivo cuenta como un avistamiento y nada se
descarta sin que el investigador lo decida.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.enums import ClassificationStatus, ValidationStatus
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.logging import log_step
from app.db.uow import UnitOfWork
from app.models.camera_station import CameraStation
from app.models.classification import Classification
from app.schemas.classification import (
    BurstGroup,
    BurstItem,
    BurstTaxonomy,
    DismissRequest,
    DismissResult,
    RepeatBatchRequest,
    RepeatBatchResult,
    ValidationRequest,
)
from app.services.classification_service import apply_validation, evidence_url
from app.services.policies import Owner
from app.services.stats_service import effective


def _taxon_key(row: Classification) -> str | None:
    """CB-60b: misma taxonomía efectiva (especie o el nivel alcanzado)."""
    t = effective(row)
    if t.label_id:
        return t.label_id
    return f"{t.rank}:{t.scientific_name}" if t.scientific_name else None


async def _own_cameras(
    uow: UnitOfWork,
    owner: Owner,
    camera_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
) -> list[CameraStation]:
    if (camera_id is None) == (project_id is None):
        raise BusinessRuleError(
            "VALIDATION_ERROR",
            "Indica una cámara o un proyecto (solo uno).",
            details=[{"field": "camera_station_id"}],
        )
    if camera_id is not None:
        camera = await uow.camera_stations.get_owned(camera_id, owner)
        if camera is None:
            raise NotFoundError("CAMERA_NOT_FOUND", "No encontramos esa cámara.")
        return [camera]
    project = await uow.projects.get_owned(project_id, owner) if project_id else None
    if project is None:
        raise NotFoundError("PROJECT_NOT_FOUND", "No encontramos ese proyecto.")
    ids = await uow.projects.camera_ids(project.id)
    # Un proyecto solo agrupa cámaras de su dueño (CB-23), así que todas son propias.
    return await uow.camera_stations.list_visible_by_ids(ids, owner)


def group_bursts(
    rows: list[Classification], cameras: list[CameraStation], window_minutes: int
) -> list[BurstGroup]:
    """Encadena por cámara y taxón: un registro entra al grupo si está a ≤ ventana del anterior."""
    codes = {c.id: c.code for c in cameras}
    window = timedelta(minutes=window_minutes)
    chains: dict[tuple[uuid.UUID, str], list[list[Classification]]] = {}
    for row in sorted(rows, key=lambda r: (str(r.camera_station_id), r.captured_at)):
        key = _taxon_key(row)
        if key is None or row.captured_at is None:
            continue
        groups = chains.setdefault((row.camera_station_id, key), [])
        last = groups[-1][-1] if groups else None
        if last is not None and last.captured_at and row.captured_at - last.captured_at <= window:
            groups[-1].append(row)
        else:
            groups.append([row])
    result = []
    for (camera_id, key), groups in chains.items():
        for group in groups:
            if len(group) < 2:
                continue
            start, end = group[0].captured_at, group[-1].captured_at
            if start is None or end is None:  # pragma: no cover - filtrado arriba
                continue
            t = effective(group[0])
            keep = max(group, key=lambda r: (float(r.confidence or 0), -group.index(r)))
            result.append(
                BurstGroup(
                    group_key=f"{camera_id}|{key}|{start.isoformat()}",
                    camera_station_id=camera_id,
                    camera_station_code=codes.get(camera_id, ""),
                    taxonomy=BurstTaxonomy(
                        scientific_name=t.scientific_name, common_name=t.common_name, rank=t.rank
                    ),
                    start=start,
                    end=end,
                    span_seconds=int((end - start).total_seconds()),
                    suggested_keep_id=keep.id,
                    items=[
                        BurstItem(
                            id=r.id,
                            file_name=r.file_name,
                            captured_at=r.captured_at,  # type: ignore[arg-type]
                            confidence=float(r.confidence) if r.confidence is not None else None,
                            validation_status=r.validation_status,
                            evidence_url=evidence_url(r.id) if r.evidence_key else None,
                        )
                        for r in group
                    ],
                )
            )
    return sorted(result, key=lambda g: (g.camera_station_code, g.start))


async def burst_candidates(
    uow: UnitOfWork,
    owner: Owner,
    *,
    camera_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    window_minutes: int | None,
    include_reviewed: bool,
) -> list[BurstGroup]:
    with log_step("burst.candidates"):
        cameras = await _own_cameras(uow, owner, camera_id, project_id)
        rows = await uow.classifications.burst_pool(
            [c.id for c in cameras], include_reviewed=include_reviewed
        )
        return group_bursts(rows, cameras, window_minutes or settings.BURST_WINDOW_MINUTES)


async def repeat_batch(
    uow: UnitOfWork, owner: Owner, body: RepeatBatchRequest
) -> RepeatBatchResult:
    """CB-60d: hay que conservar al menos uno; todos de la misma cámara y del dueño."""
    with log_step("burst.repeat_batch", keep=len(body.keep_ids), discard=len(body.discard_ids)):
        if not body.keep_ids:
            raise BusinessRuleError(
                "REPEAT_KEEP_REQUIRED",
                "Conserva al menos un registro. Para conservar todos, descarta la sugerencia.",
            )
        if set(body.keep_ids) & set(body.discard_ids):
            raise BusinessRuleError(
                "VALIDATION_ERROR", "Un registro no puede conservarse y descartarse a la vez."
            )
        ids = list(dict.fromkeys([*body.keep_ids, *body.discard_ids]))
        rows = await uow.classifications.owned_by_ids(ids, owner, for_update=True)
        if len(rows) != len(ids):
            raise NotFoundError("CLASSIFICATION_NOT_FOUND", "No encontramos esa clasificación.")
        if len({r.camera_station_id for r in rows.values()}) > 1:
            raise BusinessRuleError(
                "REPEAT_MIXED_CAMERAS", "Todos los registros deben ser de la misma cámara."
            )
        if any(r.status != ClassificationStatus.DONE for r in rows.values()):
            raise ConflictError(
                "CLASSIFICATION_NOT_DONE", "Hay registros que todavía no terminaron."
            )
        keeper = rows[body.keep_ids[0]]
        now = datetime.now(UTC)
        for cid in body.discard_ids:
            apply_validation(
                rows[cid],
                ValidationRequest(action="discard_repeat", repeat_of=keeper.id, notes=body.notes),
                owner,
                repeat_target=keeper,
            )
        for cid in body.keep_ids:
            if rows[cid].validation_status == ValidationStatus.UNVALIDATED:
                apply_validation(
                    rows[cid], ValidationRequest(action="confirm", notes=body.notes), owner
                )
        for row in rows.values():
            row.burst_reviewed_at = now
        await uow.commit()
        return RepeatBatchResult(kept=len(body.keep_ids), discarded=len(body.discard_ids))


async def dismiss(uow: UnitOfWork, owner: Owner, body: DismissRequest) -> DismissResult:
    """Conservar todos: marca el grupo como revisado y deja de sugerirlo, sin tocar registros."""
    with log_step("burst.dismiss"):
        try:
            camera_id = uuid.UUID(body.group_key.split("|", 1)[0])
        except ValueError as exc:
            raise BusinessRuleError(
                "VALIDATION_ERROR", "group_key inválido.", details=[{"field": "group_key"}]
            ) from exc
        groups = await burst_candidates(
            uow,
            owner,
            camera_id=camera_id,
            project_id=None,
            window_minutes=body.window_minutes,
            include_reviewed=False,
        )
        group = next((g for g in groups if g.group_key == body.group_key), None)
        if group is None:
            return DismissResult(dismissed=0)  # ya revisado o cambió: idempotente
        rows = await uow.classifications.owned_by_ids([i.id for i in group.items], owner)
        now = datetime.now(UTC)
        for row in rows.values():
            row.burst_reviewed_at = now
        await uow.commit()
        return DismissResult(dismissed=len(rows))
