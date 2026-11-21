"""Interfaz de envío de correo (FL-14): Resend en producción, archivo local en desarrollo."""

from typing import Protocol


class EmailSendError(Exception):
    """Fallo del proveedor. ``retryable`` distingue 429/5xx/red (reintentar) de 4xx (no)."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class EmailProvider(Protocol):
    async def send(self, *, to: str, subject: str, html: str, text: str) -> str:
        """Envía el correo y devuelve el id del proveedor."""
        ...
