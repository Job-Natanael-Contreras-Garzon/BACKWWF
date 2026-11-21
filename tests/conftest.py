"""Fixtures compartidas de BD para los tests de HU-04 en adelante.

Los archivos más antiguos definen sus propias fixtures con estos mismos nombres; pytest usa la
del módulo, así que no hay choque. ``TEST_DATABASE_URL`` debe apuntar a una base descartable:
cada test vacía todas las tablas.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_uow
from app.core.config import settings
from app.db.uow import UnitOfWork
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
requires_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no definida")

_RESET_SQL = """
DO $$
DECLARE names text;
BEGIN
  SELECT string_agg(format('%I', tablename), ', ') INTO names
  FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version';
  EXECUTE 'TRUNCATE ' || names || ' CASCADE';
END $$
"""
_SEED_SQL = (
    "INSERT INTO system_settings (key, value) VALUES ('anon_data_retention', 'true'::jsonb) "
    "ON CONFLICT (key) DO UPDATE SET value = 'true'::jsonb"
)


def _reset_rate_limiters() -> None:
    from app.services import anon_session_service, auth_service, password_reset_service

    for limiter in (
        auth_service.login_rate_limiter,
        anon_session_service.anon_session_rate_limiter,
        password_reset_service.forgot_ip_limiter,
        password_reset_service.forgot_abuse_limiter,
    ):
        limiter.reset()


@pytest.fixture(scope="module")
def migrated_test_db() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL no definida")
    original = settings.DATABASE_URL
    settings.DATABASE_URL = TEST_DATABASE_URL
    try:
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    finally:
        settings.DATABASE_URL = original
    return TEST_DATABASE_URL


@pytest.fixture
async def db_session_factory(
    migrated_test_db: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_test_db, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_uow() -> AsyncIterator[UnitOfWork]:
        async with UnitOfWork(factory) as uow:
            yield uow

    app.dependency_overrides[get_uow] = override_get_uow
    _reset_rate_limiters()
    async with engine.begin() as conn:
        await conn.exec_driver_sql(_RESET_SQL)
        await conn.exec_driver_sql(_SEED_SQL)
    try:
        yield factory
    finally:
        app.dependency_overrides.pop(get_uow, None)
        _reset_rate_limiters()
        await engine.dispose()


def make_client(ip: str = "198.51.100.10") -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 54321)),
        base_url="http://testserver",
    )


async def register_user(
    client: httpx.AsyncClient, email: str, password: str = "Password1"
) -> dict[str, object]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Investigador"},
    )
    assert resp.status_code == 201, resp.text
    return dict(resp.json()["data"])


def bearer(session: dict[str, object]) -> dict[str, str]:
    tokens = session["tokens"]
    assert isinstance(tokens, dict)
    return {"Authorization": f"Bearer {tokens['access_token']}"}
