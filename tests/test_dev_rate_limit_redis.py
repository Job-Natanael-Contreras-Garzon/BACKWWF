"""T1: los límites de intentos se comparten entre procesos (Redis) y sobreviven sin Redis."""

import os

import pytest

from app.core import rate_limit
from app.core.config import settings
from app.core.rate_limit import RateLimiter

REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "")


@pytest.fixture
async def fresh_client(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Cliente Redis nuevo por test (el de clase queda atado a un URL y un loop)."""
    await RateLimiter.close()
    monkeypatch.setattr(RateLimiter, "_down_until", 0.0)
    yield
    await RateLimiter.close()


@pytest.mark.skipif(not REDIS_TEST_URL, reason="REDIS_TEST_URL no definida")
async def test_two_api_processes_share_one_limit(
    fresh_client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REDIS_URL", REDIS_TEST_URL)
    worker_a, worker_b = RateLimiter("t1-shared"), RateLimiter("t1-shared")  # 2 procesos
    worker_a.reset(), worker_b.reset()
    results = [
        await (worker_a if i % 2 else worker_b).allow("ip:198.51.100.7", 10) for i in range(12)
    ]
    assert results == [True] * 10 + [False, False]  # 10 en total, no 10 por proceso
    assert worker_a.memory._hits == {} and worker_b.memory._hits == {}  # contó Redis

    client = RateLimiter._redis()
    keys = [k.decode() for k in await client.keys("rl:t1-shared:*")]
    assert keys and all("198.51.100.7" not in k for k in keys)  # clave hasheada


async def test_without_redis_each_process_still_limits(
    fresh_client: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "REDIS_URL", "redis://127.0.0.1:1/0")  # nadie escucha
    limiter = RateLimiter("t1-down")
    results = [await limiter.allow("ip:198.51.100.8", 3) for _ in range(4)]
    assert results == [True, True, True, False]
    assert "rate_limit.redis.unavailable" in caplog.text
    assert rate_limit.RateLimiter._down_until > 0  # no reintenta Redis en cada pedido
