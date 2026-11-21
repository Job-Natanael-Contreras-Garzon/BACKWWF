import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.deps import OptionalOwnerDep, OwnerDep, StatsFiltersDep, UoWDep, parse_if_match
from app.core.config import settings
from app.core.errors import BusinessRuleError
from app.core.logging import flow
from app.core.responses import ApiResponse, ok
from app.schemas.camera_station import (
    CameraStationCreate,
    CameraStationMapItem,
    CameraStationRead,
    CameraStationUpdate,
    NearbyData,
    RedeployData,
    RedeployRequest,
    TimeOffsetRequest,
    TimeOffsetResult,
)
from app.schemas.stats import ALL_SECTIONS, Stats, StatsSection
from app.services import camera_station_service as service
from app.services import stats_service

router = APIRouter(prefix="/camera-stations", tags=["CameraStations"])


def _sections(raw: str | None) -> list[StatsSection] | None:
    if not raw:
        return None
    chosen = [s.strip() for s in raw.split(",") if s.strip()]
    unknown = [s for s in chosen if s not in ALL_SECTIONS]
    if unknown:
        raise BusinessRuleError(
            "VALIDATION_ERROR",
            "Sección de estadísticas desconocida.",
            details=[{"field": "sections", "value": v} for v in unknown],
        )
    return [s for s in ALL_SECTIONS if s in chosen]


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None:
        return None
    try:
        min_lng, min_lat, max_lng, max_lat = (float(v) for v in raw.split(","))
    except ValueError as exc:
        raise BusinessRuleError(
            "VALIDATION_ERROR", "bbox debe ser minLng,minLat,maxLng,maxLat."
        ) from exc
    return min_lng, min_lat, max_lng, max_lat


@router.get(
    "",
    response_model=ApiResponse[list[CameraStationRead] | list[CameraStationMapItem]],
    dependencies=[Depends(flow("FL-13"))],
)
async def list_camera_stations(
    uow: UoWDep,
    viewer: OptionalOwnerDep,
    scope: Literal["mine", "public", "all"] = "all",
    view: Literal["full", "map"] = "full",
    project_id: uuid.UUID | None = None,
    bbox: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    still_installed: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 50,
    sort: Literal["code", "-created_at", "-last_capture_at"] = "-created_at",
) -> ApiResponse[list[CameraStationRead] | list[CameraStationMapItem]]:
    data, pagination = await service.list_cameras(
        uow,
        viewer,
        scope=scope,
        view=view,
        page=page,
        page_size=page_size,
        sort=sort,
        project_id=project_id,
        bbox=_parse_bbox(bbox),
        q=q,
        still_installed=still_installed,
    )
    return ok(data, pagination=pagination)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[CameraStationRead],
    dependencies=[Depends(flow("FL-05"))],
)
async def create_camera_station(
    body: CameraStationCreate, owner: OwnerDep, uow: UoWDep
) -> ApiResponse[CameraStationRead]:
    camera, warnings = await service.create_camera(uow, owner, body)
    return ok(camera, message="Cámara registrada.", warnings=warnings)


@router.get(
    "/nearby",
    response_model=ApiResponse[NearbyData],
    dependencies=[Depends(flow("FL-05"))],
)
async def nearby_camera_stations(
    owner: OwnerDep,
    uow: UoWDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    radius_m: Annotated[int, Query(ge=1)] = settings.NEARBY_RADIUS_M,
    exclude_id: uuid.UUID | None = None,
    deployed_at: datetime | None = None,
    retrieved_at: datetime | None = None,
) -> ApiResponse[NearbyData]:
    data = await service.nearby(
        uow,
        owner,
        lat=lat,
        lng=lng,
        radius_m=radius_m,
        exclude_id=exclude_id,
        deployed_at=deployed_at.replace(tzinfo=None) if deployed_at else None,
        retrieved_at=retrieved_at.replace(tzinfo=None) if retrieved_at else None,
    )
    return ok(data)


@router.get(
    "/{camera_id}",
    response_model=ApiResponse[CameraStationRead],
    dependencies=[Depends(flow("FL-06"))],
)
async def get_camera_station(
    camera_id: uuid.UUID, viewer: OptionalOwnerDep, uow: UoWDep
) -> ApiResponse[CameraStationRead]:
    return ok(await service.get_camera(uow, viewer, camera_id))


@router.patch(
    "/{camera_id}",
    response_model=ApiResponse[CameraStationRead],
    dependencies=[Depends(flow("FL-06"))],
)
async def update_camera_station(
    camera_id: uuid.UUID,
    body: CameraStationUpdate,
    owner: OwnerDep,
    uow: UoWDep,
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ApiResponse[CameraStationRead]:
    camera, warnings = await service.update_camera(
        uow, owner, camera_id, parse_if_match(if_match), body
    )
    return ok(camera, message="Cámara actualizada.", warnings=warnings)


@router.delete(
    "/{camera_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(flow("FL-06"))],
)
async def delete_camera_station(camera_id: uuid.UUID, owner: OwnerDep, uow: UoWDep) -> Response:
    await service.delete_camera(uow, owner, camera_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{camera_id}/redeploy",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[RedeployData],
    dependencies=[Depends(flow("FL-15"))],
)
async def redeploy_camera_station(
    camera_id: uuid.UUID, body: RedeployRequest, owner: OwnerDep, uow: UoWDep
) -> ApiResponse[RedeployData]:
    data = await service.redeploy(uow, owner, camera_id, body)
    return ok(data, message="Nueva instalación registrada.")


@router.post(
    "/{camera_id}/time-offset",
    response_model=ApiResponse[TimeOffsetResult],
    dependencies=[Depends(flow("FL-06"))],
)
async def time_offset_camera_station(
    camera_id: uuid.UUID, body: TimeOffsetRequest, owner: OwnerDep, uow: UoWDep
) -> ApiResponse[TimeOffsetResult]:
    """#15d / CB-18: corrige la hora de la cámara y guarda el valor original (auditado)."""
    data = await service.time_offset(uow, owner, camera_id, body)
    return ok(data, message="Hora de la cámara corregida.")


@router.get(
    "/{camera_id}/stats",
    response_model=ApiResponse[Stats],
    response_model_by_alias=True,
    dependencies=[Depends(flow("FL-11"))],
)
async def camera_station_stats(
    camera_id: uuid.UUID,
    uow: UoWDep,
    viewer: OptionalOwnerDep,
    filters: StatsFiltersDep,
    sections: str | None = None,
) -> ApiResponse[Stats]:
    """#15: privada y ajena → 404 ``CAMERA_NOT_FOUND`` (S1)."""
    stats = await stats_service.get_stats(
        uow, viewer, filters, _sections(sections), camera_id=camera_id
    )
    return ok(stats)
