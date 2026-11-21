import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.api.deps import CurrentUserDep, StorageDep, UoWDep
from app.core.logging import flow
from app.core.responses import ApiResponse, ok
from app.schemas.imports import ImportConfirm, ImportListItem, ImportPreview, ImportResult
from app.services import import_service as service
from app.services.policies import Owner

router = APIRouter(prefix="/imports", tags=["Imports"], dependencies=[Depends(flow("FL-23"))])


@router.post(
    "/desktop", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[ImportPreview]
)
async def preview_import(
    user: CurrentUserDep,
    uow: UoWDep,
    package: Annotated[UploadFile, File()],
    camera_station_id: Annotated[uuid.UUID | None, Form()] = None,
    create_camera: Annotated[bool, Form()] = False,
) -> ApiResponse[ImportPreview]:
    """#32: solo con sesión (Bearer). Valida sin escribir clasificaciones; vista previa 1 h."""
    data = await service.preview(
        uow,
        Owner(user_id=user.id),
        package,
        camera_station_id=camera_station_id,
        create_camera=create_camera,
    )
    return ok(data, message="Vista previa lista")


@router.post("/{import_id}/confirm", response_model=ApiResponse[ImportResult])
async def confirm_import(
    import_id: uuid.UUID,
    body: ImportConfirm,
    user: CurrentUserDep,
    uow: UoWDep,
    storage: StorageDep,
) -> ApiResponse[ImportResult]:
    """#33: crea la cámara si hace falta y guarda filas + fotogramas sin EXIF."""
    data = await service.confirm(uow, storage, Owner(user_id=user.id), import_id, body)
    return ok(data, message="Importación completada")


@router.delete("/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_import(import_id: uuid.UUID, user: CurrentUserDep, uow: UoWDep) -> Response:
    await service.cancel(uow, Owner(user_id=user.id), import_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=ApiResponse[list[ImportListItem]])
async def list_imports(
    user: CurrentUserDep,
    uow: UoWDep,
    camera_station_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ApiResponse[list[ImportListItem]]:
    data, pagination = await service.list_imports(
        uow, Owner(user_id=user.id), camera_station_id, page, page_size
    )
    return ok(data, pagination=pagination)
