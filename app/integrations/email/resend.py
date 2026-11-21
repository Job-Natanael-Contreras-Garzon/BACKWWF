"""Resend por su API HTTP con httpx (sin SDK). La clave y la URL vienen de ``Settings``."""

import httpx

from app.core.config import settings
from app.integrations.email.base import EmailSendError


class ResendEmailProvider:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport  # inyectable para tests (httpx.MockTransport)

    async def send(self, *, to: str, subject: str, html: str, text: str) -> str:
        payload = {
            "from": settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        }
        headers = {"Authorization": f"Bearer {settings.RESEND_API_KEY}"}
        try:
            async with httpx.AsyncClient(
                timeout=settings.EMAIL_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(settings.RESEND_API_URL, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise EmailSendError(type(exc).__name__, retryable=True) from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise EmailSendError(f"resend {response.status_code}", retryable=True)
        if response.status_code >= 400:
            raise EmailSendError(f"resend {response.status_code}", retryable=False)
        try:
            provider_id = str(response.json()["id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise EmailSendError("resend respuesta sin id", retryable=False) from exc
        return provider_id
