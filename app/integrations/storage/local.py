"""``StorageBackend`` sobre disco local (volumen de Docker en ``STORAGE_LOCAL_PATH``)."""

import asyncio
import logging
import os
import uuid
from pathlib import Path

from app.core.errors import AppError

logger = logging.getLogger(__name__)


class LocalStorage:
    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path).resolve()

    def _path(self, key: str) -> Path:
        """Ruta absoluta de ``key``; rechaza claves vacías, absolutas o que salgan de la base."""
        path = (self.base_path / key).resolve()
        if not key or Path(key).is_absolute() or not path.is_relative_to(self.base_path):
            raise ValueError(f"clave de storage inválida: {key!r}")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        try:
            await asyncio.to_thread(_write_atomic, path, data)
        except OSError as exc:
            logger.error(
                "No se pudo escribir en el storage",
                extra={"event": "storage.evidence.failed", "key": key, "error": type(exc).__name__},
            )
            raise AppError(
                "STORAGE_WRITE_FAILED", "No se pudo guardar el archivo.", context={"key": key}
            ) from exc

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).is_file)


def _write_atomic(path: Path, data: bytes) -> None:
    """Escribe a un temporal y lo renombra: nunca queda un archivo a medias con la clave final."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
