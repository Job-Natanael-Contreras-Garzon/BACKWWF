"""Interfaz de almacenamiento de fotogramas (DD-3, ESTANDARES §9).

La BD guarda solo la clave (``evidence/{yyyy}/{mm}/{classification_id}.jpg``), nunca rutas ni
URLs, así se puede cambiar de backend copiando archivos.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Guarda ``data`` en ``key``. Falla con ``AppError(STORAGE_WRITE_FAILED)``."""

    async def get(self, key: str) -> bytes:
        """Lee ``key``. Lanza ``FileNotFoundError`` si no existe: el 404 lo decide el servicio."""

    async def delete(self, key: str) -> None:
        """Borra ``key``; no falla si ya no existe."""

    async def exists(self, key: str) -> bool: ...

    async def list_keys_older_than(self, prefix: str, cutoff: float) -> list[str]:
        """Claves bajo ``prefix`` modificadas antes de ``cutoff`` (epoch). Para FL-31."""
        ...
