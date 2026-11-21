"""Recuperación de contraseña (HU-04, FL-14).

Contra la enumeración de cuentas (CB-73, CB-77): la petición de ``forgot`` hace el mismo trabajo
para cualquier correo (límite por IP, tope global y encolar). Todo lo que depende de si la cuenta
existe ocurre en segundo plano (``app.worker.send_email_job``).
"""

from datetime import UTC, datetime

from app.core.config import settings
from app.core.enums import EmailType
from app.core.errors import BadRequestError, RateLimitError, ServiceUnavailableError
from app.core.logging import log_step, mask_email
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import get_password_hash, hash_token
from app.db.uow import UnitOfWork
from app.models.user import PasswordResetToken
from app.schemas.auth import ResetTokenValidation
from app.services.auth_service import validate_password_strength

FORGOT_MESSAGE = (
    "Si el correo está registrado, recibirás un enlace en unos minutos. "
    "Revisa también la carpeta de spam."
)
RESET_DONE_MESSAGE = "Contraseña actualizada; inicia sesión"
_EMAIL_UNAVAILABLE_MSG = (
    "No podemos enviar correos en este momento. Intenta mañana o contacta al administrador."
)
_INVALID_TOKEN_MSG = "El enlace venció o ya se usó. Pide otro."  # noqa: S105 (mensaje)

# shortcut: in-memory sliding-window rate limiter (single-process only), migrate to Redis in HU-08.
forgot_ip_limiter = SlidingWindowRateLimiter(window_seconds=3600.0)
forgot_abuse_limiter = SlidingWindowRateLimiter(window_seconds=3600.0)


def ensure_enabled() -> None:
    if not settings.PASSWORD_RECOVERY_ENABLED:
        raise ServiceUnavailableError("EMAIL_TEMPORARILY_UNAVAILABLE", _EMAIL_UNAVAILABLE_MSG)


async def request_reset(uow: UnitOfWork, *, client_ip: str) -> bool:
    """Devuelve True si hay que encolar el envío. No consulta usuarios (anti-enumeración)."""
    with log_step("auth.password.forgot"):
        ensure_enabled()
        ip_key = f"ip:{client_ip}"
        # Abuso evidente por IP → 429 (umbral propio: el contrato no da número).
        if not forgot_abuse_limiter.check_and_record(
            ip_key, settings.PASSWORD_FORGOT_IP_ABUSE_PER_HOUR
        ):
            raise RateLimitError("RATE_LIMITED")

        # CB-76: tope global, igual para todos, así no revela si el correo existe.
        now = datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        daily = await uow.email_log.count_since(EmailType.PASSWORD_RESET, day_start)
        monthly = await uow.email_log.count_since(EmailType.PASSWORD_RESET, month_start)
        if daily >= settings.EMAIL_DAILY_CAP or monthly >= settings.EMAIL_MONTHLY_CAP:
            raise ServiceUnavailableError("EMAIL_TEMPORARILY_UNAVAILABLE", _EMAIL_UNAVAILABLE_MSG)

        # Límite normal por IP: silencioso (misma respuesta genérica, no se envía nada).
        return forgot_ip_limiter.check_and_record(ip_key, settings.PASSWORD_FORGOT_IP_PER_HOUR)


async def _usable_token(
    uow: UnitOfWork, token: str, *, for_update: bool = False
) -> PasswordResetToken | None:
    stored = await uow.password_reset_tokens.get_by_hash(hash_token(token), for_update=for_update)
    if stored is None or stored.used_at is not None or stored.expires_at <= datetime.now(UTC):
        return None
    return stored


async def validate_token(uow: UnitOfWork, token: str) -> ResetTokenValidation:
    # La bandera solo apaga el envío de correos: un enlace emitido por el admin (CB-76, HU-15a)
    # debe poder usarse aunque no haya correo.
    with log_step("auth.password.validate"):
        stored = await _usable_token(uow, token)
        if stored is None:
            return ResetTokenValidation(valid=False)
        user = await uow.users.get(stored.user_id)
        if user is None or not user.is_active:
            return ResetTokenValidation(valid=False)
        return ResetTokenValidation(
            valid=True, expires_at=stored.expires_at, email_hint=mask_email(user.email)
        )


async def reset_password(uow: UnitOfWork, token: str, new_password: str) -> None:
    with log_step("auth.password.reset"):
        # FOR UPDATE: dos envíos simultáneos del mismo enlace no pueden usarlo dos veces (CB-75).
        stored = await _usable_token(uow, token, for_update=True)
        user = await uow.users.get(stored.user_id) if stored is not None else None
        if stored is None or user is None or not user.is_active:
            raise BadRequestError("AUTH_RESET_TOKEN_INVALID", _INVALID_TOKEN_MSG)

        validate_password_strength(new_password)
        now = datetime.now(UTC)
        user.password_hash = get_password_hash(new_password)
        stored.used_at = now
        await uow.password_reset_tokens.invalidate_pending_for_user(user.id, now)
        await uow.refresh_tokens.revoke_all_for_user(user.id, now)  # CB-78
        await uow.commit()
