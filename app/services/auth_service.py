import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.enums import UserRole
from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    RateLimitError,
    UnauthorizedError,
)
from app.core.logging import log_step
from app.core.rate_limit import RateLimiter
from app.core.security import (
    DUMMY_BCRYPT_HASH,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
    hash_token,
    verify_password,
)
from app.db.uow import UnitOfWork
from app.models.user import RefreshToken, User
from app.schemas.auth import (
    AuthSessionData,
    AuthTokens,
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenData,
    RegisterRequest,
    UpdateMeRequest,
    UserRead,
)
from app.services import anon_session_service

login_rate_limiter = RateLimiter("login")
_LOGIN_RATE_LIMIT_MSG = "Demasiados intentos de inicio de sesión. Espera un minuto."


def validate_password_strength(password: str) -> None:
    has_letter = any(ch.isalpha() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    if len(password) < 8 or not has_letter or not has_digit or len(password.encode("utf-8")) > 72:
        raise BusinessRuleError(
            "AUTH_WEAK_PASSWORD",
            "La contraseña debe tener al menos 8 caracteres, letras y números (máximo 72 bytes).",
        )


def _issue_tokens(uow: UnitOfWork, user: User, now: datetime) -> AuthTokens:
    ttl_minutes = (
        settings.ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES
        if user.role == UserRole.ADMIN
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    token_id = uuid.uuid4()
    access_token = create_access_token(
        user.id,
        session_id=token_id,
        expires_delta=timedelta(minutes=ttl_minutes),
    )
    refresh_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = create_refresh_token(user.id, token_id=token_id, expires_delta=refresh_delta)
    uow.refresh_tokens.add(
        RefreshToken(
            id=token_id,
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=now + refresh_delta,
        )
    )
    return AuthTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ttl_minutes * 60,
    )


async def register(
    uow: UnitOfWork,
    data: RegisterRequest,
    *,
    anon_token: str | None = None,
) -> AuthSessionData:
    normalized_email = data.email.strip().lower()
    with log_step("auth.register", email=normalized_email):
        validate_password_strength(data.password)
        if await uow.users.get_by_email(normalized_email) is not None:
            raise ConflictError("AUTH_EMAIL_TAKEN", "Ya existe una cuenta con ese correo.")

        now = datetime.now(UTC)
        user = User(
            email=normalized_email,
            password_hash=get_password_hash(data.password),
            full_name=data.full_name,
            institution=data.institution,
            role=UserRole.USER,
            is_active=True,
            last_login_at=now,
        )
        uow.users.add(user)
        try:
            await uow.users.flush()
        except IntegrityError as exc:
            await uow.session.rollback()
            raise ConflictError("AUTH_EMAIL_TAKEN", "Ya existe una cuenta con ese correo.") from exc

        tokens = _issue_tokens(uow, user, now)
        anon_hint = await anon_session_service.get_auth_hint(uow, anon_token)
        await uow.commit()
        return AuthSessionData(
            user=UserRead.model_validate(user), tokens=tokens, anon_session=anon_hint
        )


async def login(
    uow: UnitOfWork,
    data: LoginRequest,
    *,
    client_ip: str,
    limiter: RateLimiter = login_rate_limiter,
    anon_token: str | None = None,
) -> AuthSessionData:
    normalized_email = data.email.strip().lower()
    with log_step("auth.login", email=normalized_email):
        # 5/min para todo email (exista o no) antes de consultar BD para evitar oráculo de admin.
        if not await limiter.allow(f"ip:{client_ip}", 10) or not await limiter.allow(
            f"email:{normalized_email}", 5
        ):
            raise RateLimitError("RATE_LIMITED", _LOGIN_RATE_LIMIT_MSG)

        user = await uow.users.get_by_email(normalized_email)

        if user is None:
            verify_password(data.password, DUMMY_BCRYPT_HASH)
            raise UnauthorizedError("AUTH_INVALID_CREDENTIALS", "Correo o contraseña incorrectos.")
        if not verify_password(data.password, user.password_hash):
            raise UnauthorizedError("AUTH_INVALID_CREDENTIALS", "Correo o contraseña incorrectos.")
        if not user.is_active:
            raise ForbiddenError(
                "ACCOUNT_DISABLED", "Tu cuenta está desactivada. Contacta al administrador."
            )

        now = datetime.now(UTC)
        user.last_login_at = now
        tokens = _issue_tokens(uow, user, now)
        anon_hint = await anon_session_service.get_auth_hint(uow, anon_token)
        await uow.commit()
        return AuthSessionData(
            user=UserRead.model_validate(user), tokens=tokens, anon_session=anon_hint
        )


async def refresh(uow: UnitOfWork, refresh_token: str) -> RefreshTokenData:
    with log_step("auth.refresh"):
        decode_refresh_token(refresh_token)
        stored = await uow.refresh_tokens.get_by_hash(hash_token(refresh_token), for_update=True)
        if stored is None:
            raise UnauthorizedError("AUTH_TOKEN_INVALID", "El token de actualización no es válido.")

        now = datetime.now(UTC)
        if stored.revoked_at is not None:
            await uow.refresh_tokens.revoke_all_for_user(stored.user_id, now)
            await uow.commit()
            raise UnauthorizedError(
                "AUTH_TOKEN_INVALID",
                "Se detectó reutilización de sesión. Inicia sesión nuevamente.",
                context={"user_id": str(stored.user_id)},
            )
        if stored.expires_at <= now:
            raise UnauthorizedError("AUTH_TOKEN_EXPIRED", "Tu sesión ha expirado.")

        user = await uow.users.get(stored.user_id)
        if user is None:
            raise UnauthorizedError("AUTH_TOKEN_INVALID", "El token de actualización no es válido.")
        if not user.is_active:
            raise ForbiddenError(
                "ACCOUNT_DISABLED", "Tu cuenta está desactivada. Contacta al administrador."
            )

        if not await uow.refresh_tokens.revoke_if_active(stored.id, now):
            await uow.refresh_tokens.revoke_all_for_user(stored.user_id, now)
            await uow.commit()
            raise UnauthorizedError(
                "AUTH_TOKEN_INVALID",
                "Se detectó reutilización de sesión. Inicia sesión nuevamente.",
            )

        tokens = _issue_tokens(uow, user, now)
        await uow.commit()
        return RefreshTokenData(tokens=tokens)


async def logout(uow: UnitOfWork, user_id: uuid.UUID, refresh_token: str) -> None:
    with log_step("auth.logout"):
        stored = await uow.refresh_tokens.get_by_hash(hash_token(refresh_token))
        if stored is None or stored.user_id != user_id:
            raise UnauthorizedError("AUTH_TOKEN_INVALID", "El token de actualización no es válido.")
        if stored.revoked_at is None:
            await uow.refresh_tokens.revoke_if_active(stored.id, datetime.now(UTC))
            await uow.commit()


async def update_me(uow: UnitOfWork, user_id: uuid.UUID, data: UpdateMeRequest) -> UserRead:
    with log_step("auth.me.update"):
        user = await uow.users.get(user_id)
        if user is None:
            raise UnauthorizedError("AUTH_TOKEN_INVALID", "El token no es válido.")
        if "full_name" in data.model_fields_set:
            if data.full_name is None:
                raise BusinessRuleError(
                    "VALIDATION_ERROR", "El nombre completo no puede estar vacío."
                )
            user.full_name = data.full_name
        if "institution" in data.model_fields_set:
            cleaned = data.institution.strip() if data.institution else ""
            user.institution = cleaned or None
        await uow.commit()
        return UserRead.model_validate(user)


async def change_password(
    uow: UnitOfWork,
    user_id: uuid.UUID,
    current_sid: uuid.UUID | None,
    data: ChangePasswordRequest,
) -> None:
    with log_step("auth.password.change"):
        user = await uow.users.get(user_id)
        if user is None:
            raise UnauthorizedError("AUTH_TOKEN_INVALID", "El token no es válido.")
        if not user.is_active:
            raise ForbiddenError(
                "ACCOUNT_DISABLED", "Tu cuenta está desactivada. Contacta al administrador."
            )
        if not verify_password(data.current_password, user.password_hash):
            raise UnauthorizedError(
                "AUTH_INVALID_CREDENTIALS", "La contraseña actual es incorrecta."
            )

        validate_password_strength(data.new_password)
        user.password_hash = get_password_hash(data.new_password)
        if current_sid is not None:
            await uow.refresh_tokens.delete_all_except(user.id, current_sid)
        else:
            await uow.refresh_tokens.revoke_all_for_user(user.id, datetime.now(UTC))
        await uow.commit()
