"""Cola de trabajos (DD-12): arq sobre Redis, detrás de una interfaz.

Redis solo lleva *avisos* ("hay trabajo"); qué archivo procesar lo decide la BD con la cola
justa de ``app.worker.dispatcher``. Si Redis se pierde, el reaper (HU-09) vuelve a avisar
desde la BD (CB-38).
"""

import uuid
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.errors import ServiceUnavailableError

PROCESS_NEXT_JOB = "process_next"  # lo implementa el worker en HU-11
_UNAVAILABLE_MSG = "La cola de análisis no está disponible. Reintentaremos en un momento."


class TaskQueue(Protocol):
    async def ping(self) -> None:
        """Lanza ``QUEUE_UNAVAILABLE`` si Redis no responde (CB-36)."""
        ...

    async def wake(self, classification_id: uuid.UUID) -> None:
        """Avisa a los workers de que hay un archivo en cola."""
        ...


def queue_unavailable() -> ServiceUnavailableError:
    return ServiceUnavailableError("QUEUE_UNAVAILABLE", _UNAVAILABLE_MSG)


class ArqTaskQueue:
    def __init__(self, redis_url: str | None = None) -> None:
        self._settings = RedisSettings.from_dsn(redis_url or settings.REDIS_URL)
        self._settings.conn_timeout = 2
        self._settings.conn_retries = 0
        self._pool: ArqRedis | None = None

    async def _redis(self) -> ArqRedis:
        if self._pool is None:
            try:
                self._pool = await create_pool(self._settings)
            except (OSError, RedisError) as exc:
                raise queue_unavailable() from exc
        return self._pool

    async def ping(self) -> None:
        pool = await self._redis()
        try:
            await pool.ping()
        except (OSError, RedisError) as exc:
            self._pool = None
            raise queue_unavailable() from exc

    async def wake(self, classification_id: uuid.UUID) -> None:
        pool = await self._redis()
        try:
            # _job_id: un solo aviso por archivo aunque se repita (reintentos, reaper).
            await pool.enqueue_job(PROCESS_NEXT_JOB, _job_id=f"wake:{classification_id}")
        except (OSError, RedisError) as exc:
            self._pool = None
            raise queue_unavailable() from exc

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None


_queue: ArqTaskQueue | None = None


def get_task_queue() -> TaskQueue:
    """Dependencia de FastAPI; los tests la reemplazan con una cola falsa."""
    global _queue
    if _queue is None:
        _queue = ArqTaskQueue()
    return _queue
