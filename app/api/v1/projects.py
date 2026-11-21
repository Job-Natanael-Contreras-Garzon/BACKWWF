import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.deps import OptionalOwnerDep, OwnerDep, UoWDep, parse_if_match
from app.core.logging import flow
from app.core.responses import ApiResponse, ok
from app.schemas.project import (
    AssociateCameraRequest,
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    ProjectUpdate,
)
from app.services import project_service as service

router = APIRouter(prefix="/projects", tags=["Projects"], dependencies=[Depends(flow("FL-07"))])


@router.get("", response_model=ApiResponse[list[ProjectRead]])
async def list_projects(
    uow: UoWDep,
    viewer: OptionalOwnerDep,
    scope: Literal["mine", "public", "all"] = "all",
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 50,
    sort: Literal["name", "-created_at"] = "-created_at",
) -> ApiResponse[list[ProjectRead]]:
    data, pagination = await service.list_projects(
        uow, viewer, scope=scope, q=q, page=page, page_size=page_size, sort=sort
    )
    return ok(data, pagination=pagination)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[ProjectDetail])
async def create_project(
    body: ProjectCreate, owner: OwnerDep, uow: UoWDep
) -> ApiResponse[ProjectDetail]:
    return ok(await service.create_project(uow, owner, body), message="Proyecto creado.")


@router.get("/{project_id}", response_model=ApiResponse[ProjectDetail])
async def get_project(
    project_id: uuid.UUID, viewer: OptionalOwnerDep, uow: UoWDep
) -> ApiResponse[ProjectDetail]:
    return ok(await service.get_project(uow, viewer, project_id))


@router.patch("/{project_id}", response_model=ApiResponse[ProjectDetail])
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    owner: OwnerDep,
    uow: UoWDep,
    if_match: Annotated[str, Header(alias="If-Match")],
) -> ApiResponse[ProjectDetail]:
    data = await service.update_project(uow, owner, project_id, parse_if_match(if_match), body)
    return ok(data, message="Proyecto actualizado.")


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_project(project_id: uuid.UUID, owner: OwnerDep, uow: UoWDep) -> Response:
    await service.delete_project(uow, owner, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{project_id}/camera-stations", response_model=ApiResponse[ProjectDetail])
async def add_camera_to_project(
    project_id: uuid.UUID, body: AssociateCameraRequest, owner: OwnerDep, uow: UoWDep
) -> ApiResponse[ProjectDetail]:
    data = await service.add_camera(uow, owner, project_id, body.camera_station_id)
    return ok(data, message="Cámara agregada al proyecto.")


@router.delete(
    "/{project_id}/camera-stations/{camera_station_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_camera_from_project(
    project_id: uuid.UUID, camera_station_id: uuid.UUID, owner: OwnerDep, uow: UoWDep
) -> Response:
    await service.remove_camera(uow, owner, project_id, camera_station_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
