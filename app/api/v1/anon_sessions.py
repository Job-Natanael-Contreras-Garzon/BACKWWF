from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.deps import AnonSessionDep, CurrentUserDep, UoWDep
from app.core.logging import flow
from app.core.responses import ApiResponse, ok
from app.schemas.anon_session import (
    AnonSessionCreateData,
    AnonSessionCurrentData,
    ClaimAnonSessionData,
    CloseAnonSessionData,
)
from app.services import anon_session_service

router = APIRouter(prefix="/anon-sessions", tags=["AnonSessions"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[AnonSessionCreateData],
    dependencies=[Depends(flow("FL-03"))],
)
async def create_anon_session(
    request: Request,
    uow: UoWDep,
) -> ApiResponse[AnonSessionCreateData]:
    # IP directa de conexión únicamente; nunca confiar en X-Forwarded-For sin proxies confiables.
    client_ip = request.client.host if request.client else "unknown"
    data = await anon_session_service.create_session(uow, client_ip=client_ip)
    return ok(data, message="Sesión temporal iniciada.")


@router.get(
    "/current",
    response_model=ApiResponse[AnonSessionCurrentData],
    dependencies=[Depends(flow("FL-03"))],
)
async def read_current_anon_session(
    anon_session: AnonSessionDep,
    uow: UoWDep,
) -> ApiResponse[AnonSessionCurrentData]:
    data = await anon_session_service.get_current(uow, anon_session)
    return ok(data)


@router.post(
    "/claim",
    response_model=ApiResponse[ClaimAnonSessionData],
    dependencies=[Depends(flow("FL-04"))],
)
async def claim_anon_session(
    current_user: CurrentUserDep,
    uow: UoWDep,
    x_anon_token: Annotated[str | None, Header(alias="X-Anon-Token")] = None,
) -> ApiResponse[ClaimAnonSessionData]:
    data = await anon_session_service.claim_session(uow, user=current_user, anon_token=x_anon_token)
    return ok(data, message="Datos asociados a tu cuenta.")


@router.post(
    "/current/close",
    response_model=ApiResponse[CloseAnonSessionData],
    dependencies=[Depends(flow("FL-03"))],
)
async def close_current_anon_session(
    anon_session: AnonSessionDep,
    uow: UoWDep,
) -> ApiResponse[CloseAnonSessionData]:
    data = await anon_session_service.close_session(uow, anon_session)
    return ok(data, message="Sesión temporal cerrada.")
