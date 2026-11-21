"""Worker de clasificación (HU-11, FL-08): toma el siguiente archivo de la cola justa, llama a la
IA, guarda el fotograma y la fila ``done``.

Cada aviso (``process_next``) procesa **un** archivo. Lo elige ``dispatcher.claim_next``, no el
aviso, así que da igual qué aviso llegue primero. Al terminar deja otro aviso, para que avance lo
que estaba frenado por el límite por dueño.
"""

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.enums import ClassificationStatus
from app.core.errors import AppError
from app.core.logging import flow_var, logger, request_id_var
from app.db.uow import UnitOfWork
from app.integrations import ai_client
from app.integrations.ai_client import AiClientError
from app.integrations.ia_contract.contract import DetectResult
from app.integrations.storage.base import StorageBackend
from app.models.classification import Classification
from app.services import batch_service, evidence, media_validator
from app.worker import dispatcher

# CB-37: errores transitorios que el worker reintenta con espera (5 s y 30 s).
TRANSIENT = {"AI_UNAVAILABLE", "AI_TIMEOUT", "AI_NOT_READY"}
# Errores del propio archivo: reintentar no sirve, así que el temporal se borra.
FILE_ERRORS = {"MEDIA_UNSUPPORTED_FORMAT", "MEDIA_TOO_LARGE", "MEDIA_DECODE_FAILED"}
PROCESS_NEXT = "process_next"


async def _heartbeat(factory: Callable[[], UnitOfWork], classification_id: uuid.UUID) -> None:
    """Latido cada ``WORKER_HEARTBEAT_SECONDS``: sin él, el reaper lo devuelve a la cola (CB-38)."""
    while True:
        await asyncio.sleep(settings.WORKER_HEARTBEAT_SECONDS)
        async with factory() as uow:
            await uow.session.execute(
                update(Classification)
                .where(
                    Classification.id == classification_id,
                    Classification.status == ClassificationStatus.PROCESSING,
                )
                .values(heartbeat_at=datetime.now(UTC))
            )
            await uow.commit()


async def _detect_with_backoff(
    row: Classification,
    client: httpx.AsyncClient | None,
    sleep: Callable[[float], Awaitable[None]],
) -> DetectResult:
    tmp = Path(settings.TMP_UPLOAD_PATH) / (row.tmp_key or "")
    delays = settings.worker_retry_delays
    for attempt in range(len(delays) + 1):
        try:
            return await ai_client.detect_media(
                tmp,
                request_id=f"w-{row.id.hex[:10]}",
                flow="FL-08",
                client=client,
                file_name=row.file_name,
            )
        except AiClientError as exc:
            if exc.code not in TRANSIENT or attempt == len(delays):
                raise
            logger.warning(
                "IA no disponible; se reintenta",
                extra={"event": "classification.ai_call.retry", "error_code": exc.code},
            )
            await sleep(delays[attempt])
    raise AssertionError("inalcanzable")  # pragma: no cover


def _apply_result(row: Classification, result: DetectResult) -> None:
    """Copia el resultado de la IA a la fila (sin geofence: no existe en el contrato 1.0.0)."""
    res = result.result
    row.category = res.category
    row.confidence = res.confidence  # type: ignore[assignment]
    row.alternatives = [alt.model_dump(mode="json") for alt in res.alternatives]
    tax = res.taxonomy
    if tax is not None:
        row.label_id, row.label_raw = tax.label_id, tax.label_raw
        row.class_, row.order_, row.family = tax.class_, tax.order, tax.family
        row.genus, row.species = tax.genus, tax.species
        row.scientific_name, row.common_name, row.rank = (
            tax.scientific_name,
            tax.common_name,
            tax.rank,
        )
    analysis = result.analysis
    row.frames_analyzed = analysis.frames_sampled
    row.low_evidence = analysis.low_evidence
    row.truncated_at_seconds = analysis.truncated_at_seconds
    if row.duration_seconds is None:
        row.duration_seconds = result.media.duration_seconds
    model = result.model
    row.model_detector, row.model_classifier = model.detector, model.classifier
    row.model_sampling, row.pipeline_version = model.sampling, model.pipeline_version
    # El aviso definitivo de video truncado lo da la IA (F1-D10); reemplaza al de la subida.
    warnings = [w for w in (row.warnings or []) if w.get("code") != "VIDEO_TRUNCATED"]
    if analysis.truncated_at_seconds is not None:
        warnings.append(
            {
                "code": "VIDEO_TRUNCATED",
                "message": (
                    f"Se analizaron los primeros {analysis.truncated_at_seconds:g} s del video."
                ),
                "context": {"truncated_at_seconds": analysis.truncated_at_seconds},
            }
        )
    row.warnings = warnings


async def _finish(
    factory: Callable[[], UnitOfWork],
    classification_id: uuid.UUID,
    *,
    status: ClassificationStatus,
    result: DetectResult | None = None,
    frame: tuple[str, int, int] | None = None,
    error_code: str | None = None,
    drop_tmp: bool,
) -> str | None:
    """Escribe el estado final y cierra el lote si ya no le queda nada. Devuelve el tmp_key."""
    async with factory() as uow:
        row = await uow.classifications.get(classification_id)
        if row is None or row.status != ClassificationStatus.PROCESSING:
            return None  # se canceló o el reaper la devolvió a la cola: no se pisa
        if result is not None:
            _apply_result(row, result)
            if result.evidence is not None and frame is not None:
                row.evidence_key, row.evidence_width, row.evidence_height = frame
                row.evidence_frame_index = result.evidence.frame_index
                row.evidence_timestamp_seconds = result.evidence.timestamp_seconds
                row.evidence_bbox = list(result.evidence.bbox)
        row.status, row.error_code = status, error_code
        row.finished_at = datetime.now(UTC)
        tmp_key = row.tmp_key
        if drop_tmp:
            row.tmp_key = None
        if row.batch_id is not None:
            batch = await uow.batches.get(row.batch_id)
            if batch is not None:
                await uow.classifications.flush()
                await batch_service.refresh_batch_status(uow, batch)
        await uow.commit()
        return tmp_key if drop_tmp else None


async def process_one(
    storage: StorageBackend,
    *,
    uow_factory: Callable[[], UnitOfWork] = UnitOfWork,
    client: httpx.AsyncClient | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Classification | None:
    """Procesa el siguiente archivo de la cola justa. None si no había nada que tomar."""
    async with uow_factory() as uow:
        row = await dispatcher.claim_next(uow)
        await uow.commit()
    if row is None:
        return None

    request_token = request_id_var.set(f"w-{row.id.hex[:10]}")
    flow_token = flow_var.set("FL-08")
    beat = asyncio.create_task(_heartbeat(uow_factory, row.id))
    key: str | None = None
    try:
        try:
            result = await _detect_with_backoff(row, client, sleep)
        except AiClientError as exc:  # DD-4: nunca se inventa un resultado
            tmp = await _finish(
                uow_factory,
                row.id,
                status=ClassificationStatus.ERROR,
                error_code=exc.code,
                drop_tmp=exc.code in FILE_ERRORS,  # en errores de la IA se conserva para reintentar
            )
            if tmp:
                await media_validator.discard(Path(settings.TMP_UPLOAD_PATH) / tmp)
            return row

        frame = None
        if result.evidence is not None:
            try:
                data, width, height = await asyncio.to_thread(
                    evidence.reencode, result.evidence.image_base64
                )
            except evidence.EvidenceInvalid:
                await _finish(
                    uow_factory,
                    row.id,
                    status=ClassificationStatus.ERROR,
                    error_code="AI_BAD_RESPONSE",
                    drop_tmp=False,
                )
                return row
            key = evidence.evidence_key(row.id, datetime.now(UTC))
            try:
                await storage.put(key, data, "image/jpeg")  # primero el archivo, después la fila
            except AppError as exc:  # STORAGE_WRITE_FAILED: sin archivo no se crea la fila done
                await _finish(
                    uow_factory,
                    row.id,
                    status=ClassificationStatus.ERROR,
                    error_code=exc.code,
                    drop_tmp=False,
                )
                return row
            frame = (key, width, height)

        try:
            tmp = await _finish(
                uow_factory,
                row.id,
                status=ClassificationStatus.DONE,
                result=result,
                frame=frame,
                drop_tmp=True,
            )
        except SQLAlchemyError:
            if key is not None:  # falló la fila: no dejar el fotograma huérfano (CA-3)
                await storage.delete(key)
            raise
        if tmp:
            await media_validator.discard(Path(settings.TMP_UPLOAD_PATH) / tmp)
        return row
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat
        flow_var.reset(flow_token)
        request_id_var.reset(request_token)


async def process_next(ctx: dict[str, Any]) -> str:
    """Job de arq. ``ctx`` trae ``redis``, ``storage`` y ``http`` (ver ``app.worker.main``)."""
    row = await process_one(ctx["storage"], client=ctx.get("http"))
    if row is None:
        return "idle"
    # Otro aviso: si había archivos frenados por el límite por dueño, ahora pueden avanzar.
    await ctx["redis"].enqueue_job(PROCESS_NEXT, _job_id=f"wake:after:{row.id}")
    return str(row.id)
