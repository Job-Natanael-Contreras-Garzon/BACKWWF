"""Clasificaciones individuales (HU-11 #27, HU-12 #25, #26, #28, #29; FL-10).

La validación nunca borra lo que dijo la IA: guarda la corrección aparte (``corrected_*``) y la
taxonomía efectiva sale de ``stats_service.effective`` (la misma regla que estadísticas).
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from math import ceil
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.enums import (
    Category,
    ClassificationStatus,
    CorrectionSource,
    MediaType,
    Rank,
    ValidationStatus,
)
from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.core.logging import log_step
from app.core.responses import Pagination
from app.db.uow import UnitOfWork
from app.integrations.storage.base import StorageBackend
from app.models.classification import Classification
from app.repositories.classifications import ClassificationQuery
from app.schemas.classification import (
    ClassificationRead,
    ErrorInfo,
    EvidenceRead,
    ModelRead,
    QueueRef,
    Skipped,
    TaxonomyRead,
    ValidationBatchRequest,
    ValidationBatchResult,
    ValidationRead,
    ValidationRequest,
)
from app.services import media_validator
from app.services.catalog_service import Taxon, get_catalog
from app.services.policies import Owner, is_owner
from app.services.stats_service import EffectiveTaxon, effective

ITEM_MESSAGES = {
    "CANCELLED_BY_USER": "Cancelaste este archivo.",
    "CAMERA_DELETED": "La cámara se eliminó; el archivo no se analizó.",
    "ACCOUNT_DISABLED": "La cuenta se desactivó; el archivo no se analizó.",
    "PROCESSING_EXPIRED": "El archivo estuvo demasiado tiempo en cola.",
    "PROCESSING_INTERRUPTED": "El análisis se interrumpió varias veces.",
    "AI_UNAVAILABLE": "El servicio de análisis no respondió.",
    "AI_TIMEOUT": "El análisis tardó demasiado.",
    "AI_NOT_READY": "El servicio de análisis se está iniciando.",
    "AI_BAD_RESPONSE": "El servicio de análisis respondió algo inesperado.",
    "MEDIA_DECODE_FAILED": "El archivo está dañado o incompleto.",
    "MEDIA_UNSUPPORTED_FORMAT": "El formato del archivo no es compatible.",
    "MEDIA_TOO_LARGE": "El archivo supera el máximo permitido.",
    "STORAGE_WRITE_FAILED": "No se pudo guardar el fotograma.",
}
_NOT_FOUND = "No encontramos esa clasificación."
_CORRECTED = (ValidationStatus.CORRECTED, ValidationStatus.CORRECTED_UNLISTED)


def _not_found() -> NotFoundError:
    return NotFoundError("CLASSIFICATION_NOT_FOUND", _NOT_FOUND)


def evidence_url(classification_id: uuid.UUID) -> str:
    return f"/api/v1/classifications/{classification_id}/evidence"


def _taxonomy(t: EffectiveTaxon) -> TaxonomyRead | None:
    if t.label_id is None and t.scientific_name is None:
        return None
    return TaxonomyRead(
        label_id=t.label_id,
        class_=t.class_,
        order=t.order,
        family=t.family,
        genus=t.genus,
        species=t.species,
        scientific_name=t.scientific_name,
        common_name=t.common_name,
        rank=t.rank,
    )


def _mmss(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def to_read(
    row: Classification, *, position: int | None = None, wait: int | None = None
) -> ClassificationRead:
    """§1.8. En estados distintos de ``done`` todo lo de la IA va en ``null``."""
    done = row.status == ClassificationStatus.DONE
    animal = done and row.category == Category.ANIMAL
    original = EffectiveTaxon(
        row.label_id,
        row.rank,
        row.class_,
        row.order_,
        row.family,
        row.genus,
        row.species,
        row.scientific_name,
        row.common_name,
    )
    corrected = effective(row) if row.validation_status in _CORRECTED else None
    error = None
    if row.status in (ClassificationStatus.ERROR, ClassificationStatus.CANCELLED):
        code = row.error_code or "INTERNAL_ERROR"
        error = ErrorInfo(code=code, message=ITEM_MESSAGES.get(code, "No se pudo procesar."))
    evidence = None
    if done and row.evidence_key:
        is_video = row.media_type == MediaType.VIDEO
        ts = row.evidence_timestamp_seconds
        evidence = EvidenceRead(
            url=evidence_url(row.id),
            frame_index=row.evidence_frame_index,
            timestamp_seconds=ts if is_video else 0,
            timestamp_label=_mmss(ts) if is_video and ts is not None else None,
            bbox=row.evidence_bbox,
            width=row.evidence_width,
            height=row.evidence_height,
        )
    queue = None
    if row.status == ClassificationStatus.QUEUED and position is not None:
        queue = QueueRef(position=position, estimated_wait_seconds=wait or 0)
    return ClassificationRead(
        id=row.id,
        batch_id=row.batch_id,
        camera_station_id=row.camera_station_id,
        source=row.source,
        file_name=row.file_name,
        file_sha256=row.file_sha256,
        media_type=row.media_type,
        duration_seconds=row.duration_seconds,
        captured_at=row.captured_at,
        captured_at_source=row.captured_at_source,
        captured_at_original=row.captured_at_original,
        status=row.status,
        error=error,
        warnings=row.warnings or [],
        queue=queue,
        category=row.category if done else None,
        taxonomy=_taxonomy(original) if animal else None,
        confidence=float(row.confidence) if done and row.confidence is not None else None,
        alternatives=row.alternatives if animal else None,
        frames_analyzed=row.frames_analyzed if done else None,
        evidence=evidence,
        validation=ValidationRead(
            status=row.validation_status,
            correction_source=row.correction_source,
            corrected_taxonomy=_taxonomy(corrected) if corrected else None,
            suggested_name=row.suggested_name,
            repeat_of=row.repeat_of,
            notes=row.validation_notes,
            validated_by=row.validated_by,
            validated_at=row.validated_at,
        ),
        effective_taxonomy=_taxonomy(effective(row)) if animal else None,
        model=(
            ModelRead(
                detector=row.model_detector,
                classifier=row.model_classifier,
                sampling=row.model_sampling,
                pipeline_version=row.pipeline_version,
            )
            if done
            else None
        ),
        low_evidence=bool(row.low_evidence) if done else False,
        created_at=row.created_at,
    )


# --- Consulta (#25, #26) ----------------------------------------------------------------------


def _csv_enum(raw: str | None, enum: Any, field: str) -> tuple[Any, ...] | None:
    if not raw:
        return None
    try:
        return tuple(enum(v.strip()) for v in raw.split(",") if v.strip())
    except ValueError as exc:
        raise BusinessRuleError(
            "VALIDATION_ERROR", "Hay un valor de filtro inválido.", details=[{"field": field}]
        ) from exc


def build_filters(
    *,
    camera_ids: list[uuid.UUID] | None,
    batch_id: uuid.UUID | None,
    status: str,
    category: str | None,
    validation_status: str | None,
    taxon: str | None,
    min_confidence: float | None,
    max_confidence: float | None,
    from_: date | None,
    to: date | None,
    source: Any,
    sort: str,
) -> ClassificationQuery:
    """Valida y arma los filtros de §8.1 (los comparten /classifications y el panel admin)."""
    if from_ and to and from_ > to:
        raise BusinessRuleError("VALIDATION_ERROR", "La fecha inicial es posterior a la final.")
    taxon_filter = None
    if taxon:
        found = get_catalog().by_id.get(taxon)
        if found is None:
            raise BusinessRuleError("CATALOG_TAXON_NOT_FOUND", "Ese taxón no está.")
        taxon_filter = _taxon_filter(found)
    statuses = {
        "done": (ClassificationStatus.DONE,),
        "error": (ClassificationStatus.ERROR,),
        "all": None,
    }[status]
    return ClassificationQuery(
        camera_ids=camera_ids,
        batch_id=batch_id,
        statuses=statuses,
        categories=_csv_enum(category, Category, "category"),
        validation_statuses=_csv_enum(validation_status, ValidationStatus, "validation_status"),
        taxon=taxon_filter,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        start=datetime.combine(from_, time.min) if from_ else None,
        end=datetime.combine(to + timedelta(days=1), time.min) if to else None,
        source=source,
        sort=sort,
    )


async def list_classifications(
    uow: UnitOfWork,
    viewer: Owner | None,
    *,
    camera_station_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    batch_id: uuid.UUID | None,
    status: str,
    category: str | None,
    validation_status: str | None,
    taxon: str | None,
    min_confidence: float | None,
    max_confidence: float | None,
    from_: date | None,
    to: date | None,
    source: Any,
    sort: str,
    page: int,
    page_size: int,
) -> tuple[list[ClassificationRead], Pagination]:
    with log_step("classification.list"):
        camera_ids: list[uuid.UUID] | None = None
        if camera_station_id is not None:
            camera = await uow.camera_stations.get_visible(camera_station_id, viewer)
            if camera is None:
                raise NotFoundError("CAMERA_NOT_FOUND", "No encontramos esa cámara.")
            camera_ids = [camera.id]
        if project_id is not None:
            project = await uow.projects.get_visible(project_id, viewer)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "No encontramos ese proyecto.")
            ids = await uow.projects.camera_ids(project.id)
            visible = [c.id for c in await uow.camera_stations.list_visible_by_ids(ids, viewer)]
            camera_ids = [c for c in visible if camera_ids is None or c in camera_ids]
        if batch_id is not None:  # un lote solo lo ve su dueño
            batch = await uow.batches.get_owned(batch_id, viewer) if viewer else None
            if batch is None:
                raise NotFoundError("BATCH_NOT_FOUND", "No encontramos ese lote.")
        query = build_filters(
            camera_ids=camera_ids,
            batch_id=batch_id,
            status=status,
            category=category,
            validation_status=validation_status,
            taxon=taxon,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            from_=from_,
            to=to,
            source=source,
            sort=sort,
        )
        rows, total = await uow.classifications.search(viewer, query, page, page_size)
        size = max(1, min(page_size, 200))
        pagination = Pagination(
            page=page,
            page_size=size,
            total=total,
            total_pages=ceil(total / size) if total else 0,
        )
        return [to_read(r) for r in rows], pagination


def _taxon_filter(taxon: Taxon) -> tuple[Rank, str]:
    if taxon.rank == Rank.SPECIES:
        return Rank.SPECIES, taxon.label_id
    level = {
        Rank.GENUS: taxon.genus,
        Rank.FAMILY: taxon.family,
        Rank.ORDER: taxon.order,
        Rank.CLASS: taxon.class_,
    }[taxon.rank]
    return taxon.rank, level or ""


async def get_classification(
    uow: UnitOfWork, viewer: Owner | None, classification_id: uuid.UUID, *, history: bool
) -> ClassificationRead:
    row = await uow.classifications.get_visible(classification_id, viewer)
    if row is None:
        raise _not_found()
    read = to_read(row)
    if history and is_owner(row, viewer):  # el historial nombra a quien validó: solo el dueño
        read.validation_history = row.validation_history or []
    return read


async def _owned(uow: UnitOfWork, owner: Owner, classification_id: uuid.UUID) -> Classification:
    rows = await uow.classifications.owned_by_ids([classification_id], owner, for_update=True)
    if classification_id not in rows:
        raise _not_found()
    return rows[classification_id]


async def move_classification(
    uow: UnitOfWork, owner: Owner, classification_id: uuid.UUID, camera_id: uuid.UUID
) -> ClassificationRead:
    """§8.4 / CB-51: solo a otra cámara propia; si allí ya está el archivo, 409."""
    with log_step("classification.move", classification_id=str(classification_id)):
        row = await _owned(uow, owner, classification_id)
        target = await uow.camera_stations.get_owned(camera_id, owner)
        if target is None:
            if await uow.camera_stations.get_visible(camera_id, owner) is not None:
                raise ForbiddenError("CAMERA_NOT_OWNED", "Solo puedes moverla a tus cámaras.")
            raise NotFoundError("CAMERA_NOT_FOUND", "No encontramos esa cámara.")
        if target.id == row.camera_station_id:
            return to_read(row)
        row.camera_station_id = target.id
        try:
            await uow.classifications.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "DUPLICATE_FILE", "Esa cámara ya tiene este mismo archivo."
            ) from exc
        await uow.commit()
        await uow.classifications.refresh(row)
        return to_read(row)


async def delete_classification(
    uow: UnitOfWork, owner: Owner, classification_id: uuid.UUID
) -> None:
    """§8.5: borrado lógico. Si seguía en cola, además se cancela y se borra el temporal."""
    with log_step("classification.delete", classification_id=str(classification_id)):
        row = await _owned(uow, owner, classification_id)
        tmp = None
        if row.status == ClassificationStatus.QUEUED:
            row.status, row.error_code = ClassificationStatus.CANCELLED, "CANCELLED_BY_USER"
            tmp, row.tmp_key = row.tmp_key, None
        row.is_deleted, row.deleted_at, row.deleted_by = True, datetime.now(UTC), owner.user_id
        await uow.commit()
        if tmp:
            await media_validator.discard(Path(settings.TMP_UPLOAD_PATH) / tmp)


# --- Validación (#28, #29) --------------------------------------------------------------------


def _set_correction(row: Classification, taxon: Taxon | None) -> None:
    row.corrected_label_id = taxon.label_id if taxon else None
    row.corrected_rank = taxon.rank if taxon else None
    row.corrected_class = taxon.class_ if taxon else None
    row.corrected_order = taxon.order if taxon else None
    row.corrected_family = taxon.family if taxon else None
    row.corrected_genus = taxon.genus if taxon else None
    row.corrected_species = taxon.species if taxon else None
    row.corrected_scientific_name = taxon.scientific_name if taxon else None
    row.corrected_common_name = taxon.common_name if taxon else None


def _invalid(message: str, field: str) -> BusinessRuleError:
    return BusinessRuleError("VALIDATION_ERROR", message, details=[{"field": field}])


def _catalog_taxon(label_id: str | None) -> Taxon:
    if not label_id:
        raise _invalid("Falta el taxón (label_id).", "label_id")
    taxon = get_catalog().by_id.get(label_id)
    if taxon is None:
        raise BusinessRuleError("CATALOG_TAXON_NOT_FOUND", "Ese taxón no está en el catálogo.")
    return taxon


def apply_validation(
    row: Classification,
    body: ValidationRequest,
    owner: Owner,
    *,
    repeat_target: Classification | None = None,
) -> None:
    """Aplica una acción de §8.6 sobre la fila (sin commit). Lanza ``AppError`` si no se puede."""
    if row.status != ClassificationStatus.DONE:
        raise ConflictError(
            "CLASSIFICATION_NOT_DONE", "Esta clasificación todavía no terminó de analizarse."
        )
    action = body.action
    values: dict[str, Any] = {}
    if action == "confirm":
        row.validation_status, row.correction_source = ValidationStatus.CONFIRMED, None
        _set_correction(row, None)
        row.suggested_name = row.repeat_of = None
    elif action == "correct":
        if body.correction_source is None:
            raise _invalid("Indica de dónde salió la corrección.", "correction_source")
        taxon = _catalog_taxon(body.label_id)
        if body.correction_source == "alternative" and taxon.label_id not in {
            alt.get("label_id") for alt in row.alternatives or []
        }:
            raise _invalid("Ese taxón no está entre las alternativas de la IA.", "label_id")
        row.validation_status = ValidationStatus.CORRECTED
        row.correction_source = CorrectionSource(body.correction_source)
        _set_correction(row, taxon)
        row.suggested_name = row.repeat_of = None
        row.category = Category.ANIMAL  # §8.6: si era persona/vacía, ahora es fauna
        values = {"label_id": taxon.label_id, "correction_source": body.correction_source}
    elif action == "correct_unlisted":
        if not body.suggested_name:
            raise _invalid("Escribe el nombre de la especie.", "suggested_name")
        superior = _catalog_taxon(body.label_id) if body.label_id else None
        if superior is not None and superior.rank == Rank.SPECIES:
            raise _invalid("El taxón debe ser superior a especie.", "label_id")
        row.validation_status = ValidationStatus.CORRECTED_UNLISTED
        row.correction_source = CorrectionSource.UNLISTED
        _set_correction(row, superior)
        row.suggested_name, row.repeat_of = body.suggested_name.strip(), None
        row.category = Category.ANIMAL
        values = {"suggested_name": row.suggested_name, "label_id": body.label_id}
    elif action == "reject":
        row.validation_status = ValidationStatus.REJECTED
    elif action == "discard_repeat":
        if repeat_target is None:
            raise _invalid("Indica qué registro se conserva (repeat_of).", "repeat_of")
        if (
            repeat_target.id == row.id
            or repeat_target.camera_station_id != row.camera_station_id
            or repeat_target.status != ClassificationStatus.DONE
        ):
            raise _invalid("repeat_of debe ser otro registro de la misma cámara.", "repeat_of")
        row.validation_status = ValidationStatus.DISCARDED_REPEAT
        row.repeat_of = repeat_target.id  # conserva su taxonomía (§8.6)
        values = {"repeat_of": str(repeat_target.id)}
    else:  # reset
        row.validation_status, row.correction_source = ValidationStatus.UNVALIDATED, None
        _set_correction(row, None)
        row.suggested_name = row.repeat_of = None
    now = datetime.now(UTC)
    row.validated_by = owner.user_id
    row.validated_at = None if action == "reset" else now
    row.validation_notes = body.notes
    row.validation_history = [
        *(row.validation_history or []),
        {
            "at": now.isoformat(),
            "by": str(owner.user_id) if owner.user_id else "anonymous",
            "action": action,
            "values": values,
            "notes": body.notes,
        },
    ]


async def validate(
    uow: UnitOfWork, owner: Owner, classification_id: uuid.UUID, body: ValidationRequest
) -> ClassificationRead:
    with log_step("classification.validate", classification_id=str(classification_id)):
        row = await _owned(uow, owner, classification_id)
        target = None
        if body.action == "discard_repeat" and body.repeat_of is not None:
            found = await uow.classifications.owned_by_ids([body.repeat_of], owner)
            target = found.get(body.repeat_of)
            if target is None:
                raise _invalid("No encontramos el registro que se conserva.", "repeat_of")
        apply_validation(row, body, owner, repeat_target=target)
        await uow.commit()
        await uow.classifications.refresh(row)
        return to_read(row)


async def validate_batch(
    uow: UnitOfWork, owner: Owner, body: ValidationBatchRequest
) -> ValidationBatchResult:
    """§8.7 / CB-67: lo ajeno o inexistente va a ``skipped`` sin revelar si existe."""
    with log_step("classification.validate_batch", count=len(body.ids)):
        ids = list(dict.fromkeys(body.ids))
        rows = await uow.classifications.owned_by_ids(ids, owner, for_update=True)
        request = ValidationRequest(action=body.action, notes=body.notes)
        updated, skipped = 0, []
        for cid in ids:
            row = rows.get(cid)
            if row is None:
                skipped.append(Skipped(id=cid, code="CLASSIFICATION_NOT_FOUND"))
            elif row.status != ClassificationStatus.DONE:
                skipped.append(Skipped(id=cid, code="CLASSIFICATION_NOT_DONE"))
            else:
                apply_validation(row, request, owner)
                updated += 1
        await uow.commit()
        return ValidationBatchResult(updated=updated, skipped=skipped)


# --- Fotograma (#27) --------------------------------------------------------------------------


async def get_evidence(
    uow: UnitOfWork, storage: StorageBackend, viewer: Owner | None, classification_id: uuid.UUID
) -> bytes:
    """El fotograma solo sale si la clasificación es visible (S1: lo ajeno y privado da 404)."""
    row = await uow.classifications.get_visible(classification_id, viewer)
    if row is None or row.evidence_key is None:
        raise _not_found()
    try:
        return await storage.get(row.evidence_key)
    except FileNotFoundError as exc:  # el archivo se limpió: para el cliente es lo mismo
        raise _not_found() from exc
