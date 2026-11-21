from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, status

from app.api.deps import AuthContextDep, CurrentUserDep, UoWDep
from app.core.errors import ServiceUnavailableError
from app.core.logging import flow, logger
from app.core.responses import ApiResponse, ok
from app.integrations.queue import TaskQueue, get_task_queue
from app.schemas.auth import (
    AuthSessionData,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RefreshTokenData,
    RegisterRequest,
    ResetPasswordRequest,
    ResetTokenValidation,
    UpdateMeRequest,
    UserRead,
)
from app.services import auth_service, password_reset_service
from app.worker import send_email_job

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


@router.post(
    "/password/forgot",
    response_model=ApiResponse[None],
    dependencies=[Depends(flow("FL-14"))],
)
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    uow: UoWDep,
    background_tasks: BackgroundTasks,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
) -> ApiResponse[None]:
    client_ip = request.client.host if request.client else "unknown"
    if await password_reset_service.request_reset(uow, client_ip=client_ip):
        try:
            await queue.enqueue_reset_email(body.email, client_ip)
        except ServiceUnavailableError:
            # Sin Redis el pedido no se pierde: lo envía este proceso en segundo plano.
            logger.warning("email.enqueue.fallback: Redis no responde, se envía desde la API")
            background_tasks.add_task(
                send_email_job.send_password_reset_email, body.email, client_ip
            )
    return ok(None, message=password_reset_service.FORGOT_MESSAGE)


@router.get(
    "/password/reset/validate",
    response_model=ApiResponse[ResetTokenValidation],
    dependencies=[Depends(flow("FL-14"))],
)
async def validate_reset_token(
    uow: UoWDep,
    token: Annotated[str, Query(min_length=1, max_length=256)],
) -> ApiResponse[ResetTokenValidation]:
    return ok(await password_reset_service.validate_token(uow, token))


@router.post(
    "/password/reset",
    response_model=ApiResponse[None],
    dependencies=[Depends(flow("FL-14"))],
)
async def reset_password(body: ResetPasswordRequest, uow: UoWDep) -> ApiResponse[None]:
    await password_reset_service.reset_password(uow, body.token, body.new_password)
    return ok(None, message=password_reset_service.RESET_DONE_MESSAGE)
