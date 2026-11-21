from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.deps import AuthContextDep, CurrentUserDep, UoWDep
from app.core.logging import flow
from app.core.responses import ApiResponse, ok
from app.schemas.auth import (
    AuthSessionData,
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RefreshTokenData,
    RegisterRequest,
    UpdateMeRequest,
    UserRead,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[AuthSessionData],
    dependencies=[Depends(flow("FL-01"))],
)
async def register_user(
    body: RegisterRequest,
    uow: UoWDep,
    x_anon_token: Annotated[str | None, Header(alias="X-Anon-Token")] = None,
) -> ApiResponse[AuthSessionData]:
    data = await auth_service.register(uow, body, anon_token=x_anon_token)
    return ok(data, message="Cuenta creada correctamente.")


@router.post(
    "/login",
    response_model=ApiResponse[AuthSessionData],
    dependencies=[Depends(flow("FL-02"))],
)
async def login_user(
    request: Request,
    body: LoginRequest,
    uow: UoWDep,
    x_anon_token: Annotated[str | None, Header(alias="X-Anon-Token")] = None,
) -> ApiResponse[AuthSessionData]:
    # IP directa de conexión únicamente; nunca confiar en X-Forwarded-For sin proxies confiables.
    client_ip = request.client.host if request.client else "unknown"
    data = await auth_service.login(uow, body, client_ip=client_ip, anon_token=x_anon_token)
    return ok(data, message="Sesión iniciada correctamente.")


@router.post(
    "/refresh",
    response_model=ApiResponse[RefreshTokenData],
    dependencies=[Depends(flow("FL-02"))],
)
async def refresh_tokens(
    body: RefreshRequest,
    uow: UoWDep,
) -> ApiResponse[RefreshTokenData]:
    data = await auth_service.refresh(uow, body.refresh_token)
    return ok(data, message="Sesión renovada.")


@router.post(
    "/logout",
    response_model=ApiResponse[None],
    dependencies=[Depends(flow("FL-02"))],
)
async def logout_user(
    body: LogoutRequest,
    current_user: CurrentUserDep,
    uow: UoWDep,
) -> ApiResponse[None]:
    await auth_service.logout(uow, current_user.id, body.refresh_token)
    return ok(None, message="Sesión cerrada.")


@router.get(
    "/me",
    response_model=ApiResponse[UserRead],
    dependencies=[Depends(flow("FL-02"))],
)
async def read_me(current_user: CurrentUserDep) -> ApiResponse[UserRead]:
    return ok(UserRead.model_validate(current_user))


@router.patch(
    "/me",
    response_model=ApiResponse[UserRead],
    dependencies=[Depends(flow("FL-02"))],
)
async def patch_me(
    body: UpdateMeRequest,
    current_user: CurrentUserDep,
    uow: UoWDep,
) -> ApiResponse[UserRead]:
    data = await auth_service.update_me(uow, current_user.id, body)
    return ok(data, message="Perfil actualizado.")


@router.post(
    "/me/password",
    response_model=ApiResponse[None],
    dependencies=[Depends(flow("FL-02"))],
)
async def change_my_password(
    body: ChangePasswordRequest,
    auth: AuthContextDep,
    uow: UoWDep,
) -> ApiResponse[None]:
    await auth_service.change_password(uow, auth.user.id, auth.session_id, body)
    return ok(None, message="Contraseña actualizada.")
