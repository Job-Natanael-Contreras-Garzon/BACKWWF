"""Envío del correo de recuperación (FL-14), fuera de la petición.

Lo corre el worker ``arq`` (job ``send_reset_email``): si la API se reinicia, el pedido sigue en
Redis. Si Redis no responde al encolar, la API lo corre en segundo plano (``BackgroundTasks``) para
no perder el pedido. Abre su propia UnitOfWork porque la de la petición ya se cerró. Nunca
registra el correo en claro, el token ni el enlace.
"""

import asyncio
import hashlib
import hmac
import html
import json
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.enums import EmailStatus, EmailType
from app.core.logging import flow_var, logger
from app.core.security import hash_token
from app.db.uow import UnitOfWork
from app.integrations.email import EmailProvider, EmailSendError, get_email_provider
from app.integrations.queue import RESET_EMAIL_TICKET_PREFIX
from app.models.admin import EmailLog
from app.models.user import PasswordResetToken

RETRY_DELAYS_SECONDS = (1.0, 3.0)  # 2 reintentos ante 429/5xx (FL-14 paso 3)


def _ip_hash(client_ip: str) -> str:
    """HMAC de la IP: permite agrupar abusos sin guardar la IP en claro."""
    return hmac.new(settings.SECRET_KEY.encode(), client_ip.encode(), hashlib.sha256).hexdigest()


def build_message(link: str) -> tuple[str, str, str]:
    minutes = settings.PASSWORD_RESET_TTL_MINUTES
    subject = "Restablece tu contraseña · Monitoreo de Fauna WWF"
    text = (
        "Recibimos una solicitud para restablecer tu contraseña.\n\n"
        f"Abre este enlace para elegir una nueva (vale {minutes} minutos y se usa una sola vez):\n"
        f"{link}\n\n"
        "Si no fuiste tú, ignora este correo: tu contraseña no cambia."
    )
    safe_link = html.escape(link, quote=True)
    body = (
        "<p>Recibimos una solicitud para restablecer tu contraseña.</p>"
        f'<p><a href="{safe_link}">Elegir una contraseña nueva</a></p>'
        f"<p>El enlace vale {minutes} minutos y se usa una sola vez.</p>"
        "<p>Si no fuiste tú, ignora este correo: tu contraseña no cambia.</p>"
    )
    return subject, body, text


async def send_password_reset_email(
    email: str,
    client_ip: str,
    *,
    uow_factory: Callable[[], UnitOfWork] | None = None,
    provider: EmailProvider | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> EmailStatus | None:
    """Crea el token y envía el correo. Devuelve el estado final (None: nada que enviar)."""
    factory = uow_factory or UnitOfWork
    flow_var.set("FL-14")
    normalized = email.strip().lower()
    now = datetime.now(UTC)

    async with factory() as uow:
        user = await uow.users.get_by_email(normalized)
        if user is None or not user.is_active:  # CB-73, CB-77: nada que enviar
            return None
        log = EmailLog(
            type=EmailType.PASSWORD_RESET, to_hash=hash_token(normalized), status=EmailStatus.QUEUED
        )
        per_hour = await uow.password_reset_tokens.count_created_since(
            user.id, now - timedelta(hours=1)
        )
        per_day = await uow.password_reset_tokens.count_created_since(
            user.id, now - timedelta(days=1)
        )
        if (
            per_hour >= settings.PASSWORD_FORGOT_EMAIL_PER_HOUR
            or per_day >= settings.PASSWORD_FORGOT_EMAIL_PER_DAY
        ):
            log.status = EmailStatus.SKIPPED_LIMIT
            uow.email_log.add(log)
            await uow.commit()
            return EmailStatus.SKIPPED_LIMIT

        await uow.password_reset_tokens.invalidate_pending_for_user(user.id, now)  # CB-74
        token = secrets.token_urlsafe(32)
        uow.password_reset_tokens.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES),
                request_ip_hash=_ip_hash(client_ip),
                created_at=now,
            )
        )
        uow.email_log.add(log)
        await uow.commit()
        log_id = log.id

    link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/restablecer?token={token}"
    subject, body, text = build_message(link)
    sender = provider or get_email_provider()
    status, provider_id = EmailStatus.FAILED, None
    for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
        try:
            provider_id = await sender.send(to=normalized, subject=subject, html=body, text=text)
            status = EmailStatus.SENT
            break
        except EmailSendError as exc:
            logger.warning(
                "No se pudo enviar el correo de recuperación",
                extra={"event": "email.send.failed", "attempt": attempt + 1, "error": str(exc)},
            )
            if not exc.retryable or attempt == len(RETRY_DELAYS_SECONDS):
                break
            await sleep(RETRY_DELAYS_SECONDS[attempt])

    async with factory() as uow:
        stored_log = await uow.email_log.get(log_id)
        if stored_log is not None:
            stored_log.status = status
            stored_log.provider_id = provider_id
            await uow.commit()
    logger.info("Correo de recuperación procesado", extra={"event": f"email.{status.value}"})
    return status


async def send_reset_email(ctx: dict[str, Any], ticket: str) -> None:
    """Job de arq (FL-14). Recibe solo un id: el correo y la IP los lee (y borra) de Redis, así
    no quedan en el log de arq. Los reintentos ante el proveedor ya están dentro del envío."""
    flow_var.set("FL-14")
    raw = await ctx["redis"].getdel(RESET_EMAIL_TICKET_PREFIX + ticket)
    if raw is None:  # venció (> 1 h en cola) o ya se usó
        logger.warning("email.ticket.missing: pedido de recuperación vencido o repetido")
        return
    data = json.loads(raw)
    await send_password_reset_email(data["email"], data["client_ip"])
