"""Límites de intentos (login, sesiones anónimas, recuperación de contraseña).

Ventana deslizante compartida en Redis, así el límite vale para todos los procesos de la API
(el ``Dockerfile`` arranca 2 workers de uvicorn). Si Redis no responde, cada proceso cuenta en su
memoria hasta que vuelva: el login nunca se cae por Redis (y el límite sigue existiendo).
En Redis la clave va hasheada: ni IPs ni correos en texto plano.
"""

import hashlib
import time
import uuid
from collections import deque

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import logger

# Ventana deslizante atómica: limpia lo vencido, cuenta y, si hay cupo, anota este intento.
_SLIDING_WINDOW = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1] - ARGV[2])
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then return 0 end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('PEXPIRE', KEYS[1], math.ceil(ARGV[2] * 1000))
return 1
"""
_RETRY_REDIS_AFTER_SECONDS = 30.0


class SlidingWindowRateLimiter:
    """Contador en memoria de un solo proceso: respaldo cuando Redis no responde."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def check_and_record(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        for stale_key in [k for k, b in self._hits.items() if not b or b[-1] <= cutoff]:
            del self._hits[stale_key]

        bucket = self._hits.get(key)
        if bucket is None:
            if limit <= 0:
                return False
            self._hits[key] = deque([now])
            return True
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


class RateLimiter:
    """Límite compartido entre procesos (Redis) con respaldo en memoria."""

    _client: Redis | None = None
    _down_until = 0.0

    def __init__(self, name: str, window_seconds: float = 60.0) -> None:
        self.name = name
        self.window_seconds = window_seconds
        self.memory = SlidingWindowRateLimiter(window_seconds)
        self._generation = 0  # reset() empieza claves nuevas sin borrar en Redis

    @classmethod
    def _redis(cls) -> Redis:
        if cls._client is None:
            cls._client = Redis.from_url(
                settings.REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5
            )
        return cls._client

    def _key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return f"rl:{self.name}:{self._generation}:{digest}"

    async def allow(self, key: str, limit: int) -> bool:
        """Registra el intento y dice si entra en el límite."""
        if limit <= 0:
            return False
        if time.monotonic() >= RateLimiter._down_until:
            try:
                result = await self._redis().eval(  # type: ignore[misc]
                    _SLIDING_WINDOW,
                    1,
                    self._key(key),
                    str(time.time()),
                    str(self.window_seconds),
                    str(limit),
                    uuid.uuid4().hex,
                )
                return bool(int(result))
            except (RedisError, OSError):
                RateLimiter._down_until = time.monotonic() + _RETRY_REDIS_AFTER_SECONDS
                logger.warning(
                    "rate_limit.redis.unavailable: se cuenta en memoria por %ss",
                    int(_RETRY_REDIS_AFTER_SECONDS),
                )
        return self.memory.check_and_record(key, limit)

    def reset(self) -> None:
        self._generation += 1
        self.memory.reset()

    @classmethod
    async def close(cls) -> None:
        if cls._client is not None:
            await cls._client.aclose()
            cls._client = None
