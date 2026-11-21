import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import OptionalOwnerDep, OwnerDep, StorageDep, UoWDep
from app.core.enums import ClassificationSource
from app.core.errors import BusinessRuleError
from app.core.logging import flow
from app.core.responses import ApiResponse, ok
from app.schemas.classification import (
    BurstGroup,
    ClassificationRead,
    DismissRequest,
    DismissResult,
    MoveRequest,
    RepeatBatchRequest,
    RepeatBatchResult,
    ValidationBatchRequest,
    ValidationBatchResult,
    ValidationRequest,
)
from app.services import burst_service
from app.services import classification_service as service

router = APIRouter(
    prefix="/classifications", tags=["Classifications"], dependencies=[Depends(flow("FL-10"))]
)
Confidence = Annotated[float | None, Query(ge=0, le=1)]


@router.get("", response_model=ApiResponse[list[ClassificationRead]], response_model_by_alias=True)
async def list_classifications(
    uow: UoWDep,
    viewer: OptionalOwnerDep,
    camera_station_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    status_: Annotated[Literal["done", "error", "all"], Query(alias="status")] = "done",
    category: str | None = None,
    validation_status: str | None = None,
    taxon: Annotated[str | None, Query(max_length=64)] = None,
    min_confidence: Confidence = None,
    max_confidence: Confidence = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    source: ClassificationSource | None = None,
    sort: Literal["-captured_at", "confidence", "-created_at", "file_name"] = "-captured_at",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ApiResponse[list[ClassificationRead]]:
    """#25: sin alcance devuelve lo propio; con cámara o proyecto, lo visible (S1)."""
    if from_ and to and from_ > to:
        raise BusinessRuleError("VALIDATION_ERROR", "La fecha inicial es posterior a la final.")
    data, pagination = await service.list_classifications(
        uow,
        viewer,
        camera_station_id=camera_station_id,
        project_id=project_id,
        batch_id=batch_id,
        status=status_,
        category=category,
        validation_status=validation_status,
        taxon=taxon,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        from_=from_,
        to=to,
        source=source,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return ok(data, pagination=pagination)


@router.post("/validation-batch", response_model=ApiResponse[ValidationBatchResult])
async def validation_batch(
    body: ValidationBatchRequest, owner: OwnerDep, uow: UoWDep
) -> ApiResponse[ValidationBatchResult]:
    """#29: hasta 500; lo ajeno o inexistente queda en ``skipped`` (CB-67)."""
    return ok(await service.validate_batch(uow, owner, body))


@router.get(
    "/burst-candidates",
    response_model=ApiResponse[list[BurstGroup]],
    dependencies=[Depends(flow("FL-16"))],
)
async def burst_candidates(
    owner: OwnerDep,
    uow: UoWDep,
    camera_station_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    window_minutes: Annotated[int | None, Query(ge=1, le=60)] = None,
    include_reviewed: bool = False,
) -> ApiResponse[list[BurstGroup]]:
    """#29b: solo sugiere; nada se descarta sin que el investigador lo decida (D10)."""
    groups = await burst_service.burst_candidates(
        uow,
        owner,
        camera_id=camera_station_id,
        project_id=project_id,
        window_minutes=window_minutes,
        include_reviewed=include_reviewed,
    )
    return ok(groups)


@router.post(
    "/repeat-batch",
    response_model=ApiResponse[RepeatBatchResult],
    dependencies=[Depends(flow("FL-16"))],
)
async def repeat_batch(
    body: RepeatBatchRequest, owner: OwnerDep, uow: UoWDep
) -> ApiResponse[RepeatBatchResult]:
    return ok(await burst_service.repeat_batch(uow, owner, body))


@router.post(
    "/repeat-batch/dismiss",
    response_model=ApiResponse[DismissResult],
    dependencies=[Depends(flow("FL-16"))],
)
async def dismiss_burst(
    body: DismissRequest, owner: OwnerDep, uow: UoWDep
) -> ApiResponse[DismissResult]:
    return ok(await burst_service.dismiss(uow, owner, body))


@router.get(
    "/{classification_id}",
    response_model=ApiResponse[ClassificationRead],
    response_model_by_alias=True,
)
async def get_classification(
    classification_id: uuid.UUID,
    uow: UoWDep,
    viewer: OptionalOwnerDep,
    include: Literal["validation_history"] | None = None,
) -> ApiResponse[ClassificationRead]:
    """#26: privada y ajena → 404 (S1). El historial solo lo ve el dueño."""
    read = await service.get_classification(
        uow, viewer, classification_id, history=include == "validation_history"
    )
    return ok(read)


@router.patch(
    "/{classification_id}",
    response_model=ApiResponse[ClassificationRead],
    response_model_by_alias=True,
)
async def move_classification(
    classification_id: uuid.UUID, body: MoveRequest, owner: OwnerDep, uow: UoWDep
) -> ApiResponse[ClassificationRead]:
    """#26 / CB-51: mover a otra cámara propia."""
    read = await service.move_classification(uow, owner, classification_id, body.camera_station_id)
    return ok(read, message="Clasificación movida")


@router.delete("/{classification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_classification(
    classification_id: uuid.UUID, owner: OwnerDep, uow: UoWDep
) -> Response:
    await service.delete_classification(uow, owner, classification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{classification_id}/validation",
    response_model=ApiResponse[ClassificationRead],
    response_model_by_alias=True,
)
async def validate_classification(
    classification_id: uuid.UUID, body: ValidationRequest, owner: OwnerDep, uow: UoWDep
) -> ApiResponse[ClassificationRead]:
    """#28: confirm · correct · correct_unlisted · reject · discard_repeat · reset (CB-62..66)."""
    return ok(await service.validate(uow, owner, classification_id, body))


@router.get(
    "/{classification_id}/evidence",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def get_evidence(
    classification_id: uuid.UUID, uow: UoWDep, storage: StorageDep, viewer: OptionalOwnerDep
) -> Response:
    """#27: no se monta el volumen como estático; cada fotograma pasa por la visibilidad."""
    data = await service.get_evidence(uow, storage, viewer, classification_id)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
