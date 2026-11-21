import uuid

from fastapi import APIRouter, Depends, Response

from app.api.deps import OptionalOwnerDep, StatsFiltersDep, UoWDep
from app.core.logging import flow
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["Reports"], dependencies=[Depends(flow("FL-12"))])

_MEDIA = {
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


async def _download(
    kind: str,
    uow: UoWDep,
    viewer: OptionalOwnerDep,
    filters: StatsFiltersDep,
    camera_station_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
) -> Response:
    data, name = await report_service.build_report(
        uow, viewer, filters, kind=kind, camera_id=camera_station_id, project_id=project_id
    )
    return Response(
        content=data,
        media_type=_MEDIA[kind],
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/excel", response_class=Response, responses={200: {"content": {_MEDIA["excel"]: {}}}})
async def excel_report(
    uow: UoWDep,
    viewer: OptionalOwnerDep,
    filters: StatsFiltersDep,
    camera_station_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> Response:
    """#31: binario directo; los errores sí van con la envoltura JSON (§11)."""
    return await _download("excel", uow, viewer, filters, camera_station_id, project_id)


@router.get("/pdf", response_class=Response, responses={200: {"content": {_MEDIA["pdf"]: {}}}})
async def pdf_report(
    uow: UoWDep,
    viewer: OptionalOwnerDep,
    filters: StatsFiltersDep,
    camera_station_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> Response:
    return await _download("pdf", uow, viewer, filters, camera_station_id, project_id)
