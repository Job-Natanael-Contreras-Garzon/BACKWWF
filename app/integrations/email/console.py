"""Solo desarrollo: escribe el correo en un archivo en vez de enviarlo.

No se registra en los logs, porque el enlace lleva un token secreto. ``Settings`` rechaza este
proveedor en producción cuando la recuperación está activa.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ConsoleEmailProvider:
    def __init__(self, mailbox_path: str | None = None) -> None:
        self._mailbox = Path(mailbox_path or settings.DEV_MAILBOX_PATH)

    async def send(self, *, to: str, subject: str, html: str, text: str) -> str:
        message_id = f"console-{uuid.uuid4().hex}"
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        content = f"To: {to}\nSubject: {subject}\n\n{text}\n"
        await asyncio.to_thread(_write, self._mailbox / f"{stamp}-{message_id}.txt", content)
        return message_id
