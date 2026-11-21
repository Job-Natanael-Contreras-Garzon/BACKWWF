import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.api.deps import OwnerDep, UoWDep
from app.core.enums import BatchStatus
from app.core.logging import flow
from app.core.responses import ApiResponse, ok
from app.integrations.queue import TaskQueue, get_task_queue
from app.schemas.batch import BatchCreate, BatchItem, BatchRead
from app.services import batch_service as service

router = APIRouter(
    prefix="/classification-batches", tags=["Batches"], dependencies=[Depends(flow("FL-08"))]
)
QueueDep = Annotated[TaskQueue, Depends(get_task_queue)]


@router.get("", response_model=ApiResponse[list[BatchRead]])
async def list_batches(
    owner: OwnerDep,
    uow: UoWDep,
    active: bool = False,
    camera_station_id: uuid.UUID | None = None,
    batch_status: Annotated[BatchStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 50,
) -> ApiResponse[list[BatchRead]]:
    data, pagination = await service.list_batches(
        uow,
        owner,
        active=active,
        page=page,
        page_size=page_size,
        camera_station_id=camera_station_id,
        status=batch_status,
    )
    return ok(data, pagination=pagination)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[BatchRead])
async def create_batch(body: BatchCreate, owner: OwnerDep, uow: UoWDep) -> ApiResponse[BatchRead]:
    return ok(await service.create_batch(uow, owner, body), message="Lote creado.")


@router.post("/{batch_id}/files", response_model=ApiResponse[BatchItem])
async def upload_file(
    batch_id: uuid.UUID,
    response: Response,
    owner: OwnerDep,
    uow: UoWDep,
    queue: QueueDep,
    file: Annotated[UploadFile, File()],
    client_index: Annotated[int, Form(ge=0)],
    client_mtime: Annotated[datetime | None, Form()] = None,
) -> ApiResponse[BatchItem]:
    item, http_status = await service.upload_file(
        uow,
        queue,
        owner,
        batch_id,
        upload=file,
        file_name=file.filename or "archivo",
        client_index=client_index,
        client_mtime=client_mtime,
    )
    response.status_code = http_status  # 202 en cola · 200 si el archivo no entra
    message = "Archivo en cola." if http_status == 202 else "El archivo no se puede analizar."
    return ok(item, message=message)


@router.get("/{batch_id}", response_model=ApiResponse[BatchRead])
async def get_batch(
    batch_id: uuid.UUID, owner: OwnerDep, uow: UoWDep, since: datetime | None = None
) -> ApiResponse[BatchRead]:
    return ok(await service.get_batch(uow, owner, batch_id, since))


@router.post("/{batch_id}/cancel", response_model=ApiResponse[BatchRead])
async def cancel_batch(batch_id: uuid.UUID, owner: OwnerDep, uow: UoWDep) -> ApiResponse[BatchRead]:
    return ok(await service.cancel_batch(uow, owner, batch_id), message="Lote cancelado.")


@router.delete(
    "/{batch_id}/items/{client_index}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def cancel_item(
    batch_id: uuid.UUID, client_index: int, owner: OwnerDep, uow: UoWDep
) -> Response:
    await service.cancel_item(uow, owner, batch_id, client_index)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{batch_id}/items/{client_index}/retry", response_model=ApiResponse[BatchItem])
async def retry_item(
    batch_id: uuid.UUID,
    client_index: int,
    response: Response,
    owner: OwnerDep,
    uow: UoWDep,
    queue: QueueDep,
) -> ApiResponse[BatchItem]:
    item, http_status = await service.retry_item(uow, queue, owner, batch_id, client_index)
    response.status_code = http_status
    return ok(item, message="Archivo de vuelta en la cola." if http_status == 202 else "OK")


@router.post("/{batch_id}/complete", response_model=ApiResponse[BatchRead])
async def complete_batch(
    batch_id: uuid.UUID, owner: OwnerDep, uow: UoWDep
) -> ApiResponse[BatchRead]:
    return ok(await service.complete_batch(uow, owner, batch_id))
