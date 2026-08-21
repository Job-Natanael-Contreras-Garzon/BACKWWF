from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_auth_service, get_current_user
from app.db.session import get_db
from app.interfaces.auth_service import IAuthService
from app.models.user import User
from app.schemas.auth import LoginSchema, RefreshSchema, RegisterSchema
from app.schemas.response_wrapper import StandardResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: POST /api/v1/auth/register
# Happy Path: Registra un nuevo usuario con contraseña hasheada (bcrypt), persiste
# en BD y retorna HTTP 201 con datos de usuario y tokens JWT (access y refresh).
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registro de nuevo usuario",
)
async def register(
    user_in: RegisterSchema,
    db: AsyncSession = Depends(get_db),
    service: IAuthService = Depends(get_auth_service),
):
    """
    **Physical Path**: `POST /api/v1/auth/register`

    **Happy Path**:
    1. Recibe datos válidos de registro (`full_name`, `email`, `password`, `institucion`, `sexo`).
    2. Comprueba que el correo electrónico no esté registrado previamente.
    3. Hashea la contraseña con algoritmo bcrypt de alta resistencia.
    4. Persiste la entidad `User` en PostgreSQL y genera un `user_id` (UUID).
    5. Emite un par de tokens JWT (`access_token` con expiración corta y `refresh_token` con expiración prolongada).
    6. Retorna HTTP 201 Created con el payload `{status: "success", data: {user, tokens}, message: "Usuario registrado exitosamente"}`.
    """
    data = await service.register_user(db=db, user_in=user_in)
    return StandardResponse(
        status="success",
        data=data,
        message="Usuario registrado exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: POST /api/v1/auth/login
# Happy Path: Valida email y password contra el hash bcrypt, y retorna HTTP 200
# con perfil básico y tokens JWT de acceso y refresco.
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/login",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Inicio de sesión (Login)",
)
async def login(
    credentials: LoginSchema,
    db: AsyncSession = Depends(get_db),
    service: IAuthService = Depends(get_auth_service),
):
    """
    **Physical Path**: `POST /api/v1/auth/login`

    **Happy Path**:
    1. Recibe credenciales válidas (`email`, `password`).
    2. Busca al usuario en la BD por correo electrónico verificado (`is_deleted == False`).
    3. Valida la contraseña en texto plano contra el hash almacenado mediante `verify_password`.
    4. Verifica que la cuenta esté activa (`is_active == True`).
    5. Genera nuevos tokens JWT de acceso y refresco.
    6. Retorna HTTP 200 OK con payload `{status: "success", data: {user, tokens}, message: "Autenticación exitosa"}`.
    """
    data = await service.authenticate_user(db=db, credentials=credentials)
    return StandardResponse(
        status="success",
        data=data,
        message="Autenticación exitosa",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: POST /api/v1/auth/refresh
# Happy Path: Valida la firma y vigencia del refresh_token, extrae el user_id
# y emite un nuevo par de tokens (access y refresh) con HTTP 200.
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/refresh",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Renovación de tokens JWT",
)
async def refresh_tokens(
    data: RefreshSchema,
    db: AsyncSession = Depends(get_db),
    service: IAuthService = Depends(get_auth_service),
):
    """
    **Physical Path**: `POST /api/v1/auth/refresh`

    **Happy Path**:
    1. Recibe un `refresh_token` criptográficamente válido y vigente.
    2. Decodifica el token utilizando `REFRESH_SECRET_KEY` y comprueba que `type == "refresh"`.
    3. Extrae el `user_id` (`sub`) y valida que el usuario exista y esté activo en la BD.
    4. Genera un nuevo par de tokens JWT (`access_token` y `refresh_token`).
    5. Retorna HTTP 200 OK con `{status: "success", data: {access_token, refresh_token, token_type}, message: "Tokens renovados exitosamente"}`.
    """
    tokens = await service.refresh_tokens(db=db, data=data)
    return StandardResponse(
        status="success",
        data=tokens,
        message="Tokens renovados exitosamente",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Path: GET /api/v1/auth/me
# Happy Path: Valida el Access Token activo en cabecera Authorization: Bearer,
# obtiene el usuario autenticado desde BD y retorna HTTP 200 con su perfil.
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Perfil del usuario autenticado",
)
async def get_me(
    current_user: User = Depends(get_current_user),
    service: IAuthService = Depends(get_auth_service),
):
    """
    **Physical Path**: `GET /api/v1/auth/me`

    **Happy Path**:
    1. El cliente envía la petición con cabecera `Authorization: Bearer <access_token>`.
    2. La dependencia `get_current_user` valida la firma, vigencia y permisos del usuario.
    3. El servicio formatea la información de perfil (id, full_name, email, institucion, sexo, created_at).
    4. Retorna HTTP 200 OK con `{status: "success", data: <perfil>, message: "Perfil obtenido exitosamente"}`.
    """
    profile = await service.get_user_profile(current_user=current_user)
    return StandardResponse(
        status="success",
        data=profile,
        message="Perfil obtenido exitosamente",
    )
