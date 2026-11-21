"""HU-02 contra PostgreSQL real: migración, integridad (CB-13, CB-50, dueño XOR), UoW y repos.

Necesita ``TEST_DATABASE_URL`` (una base descartable: se borra y se migra). Sin ella, se salta.
"""

import asyncio
import os
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.enums import ClassificationStatus, MediaType, Visibility
from app.db.uow import UnitOfWork
from app.models import AnonSession, CameraStation, Classification, RefreshToken, User
from app.services.policies import Owner

ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no definida")

CANONICAL_TABLES = {
    "admin_audit_log",
    "anon_purge_runs",
    "anon_sessions",
    "camera_stations",
    "classification_batches",
    "classifications",
    "desktop_imports",
    "email_log",
    "password_reset_tokens",
    "project_camera_stations",
    "projects",
    "refresh_tokens",
    "system_settings",
    "users",
}
# Lo que deja create_all + seed_db.py en una faunadb del hackathon (forma mínima).
LEGACY_SQL = """
DROP SCHEMA public CASCADE; CREATE SCHEMA public;
CREATE TYPE camerastationstatus AS ENUM ('active', 'retrieved');
CREATE TABLE users (id serial PRIMARY KEY, username text);
CREATE TABLE camera_stations (id serial PRIMARY KEY, status camerastationstatus);
CREATE TABLE species (id serial PRIMARY KEY, common_name text);
CREATE TABLE videos (id serial PRIMARY KEY, species_id int REFERENCES species(id));
INSERT INTO users (username) VALUES ('admin@wwf.org');
INSERT INTO species (common_name) VALUES ('Jaguar');
"""


async def _query(sql: str) -> list[Any]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            result = await conn.exec_driver_sql(sql)
            return list(result.scalars()) if result.returns_rows else []
    finally:
        await engine.dispose()


def _public_tables() -> set[str]:
    sql = "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    return set(asyncio.run(_query(sql))) - {"alembic_version"}


def _alembic(action: str, target: str) -> None:
    getattr(command, action)(Config(str(ROOT / "alembic.ini")), target)


@pytest.fixture(scope="session")
def migration_report() -> dict[str, Any]:
    """Base con el esquema legado → upgrade → downgrade → upgrade (CA-2). Deja la base migrada."""
    original_url = settings.DATABASE_URL
    settings.DATABASE_URL = TEST_DATABASE_URL  # env.py de Alembic lee de Settings
    try:
        for statement in filter(str.strip, LEGACY_SQL.split(";")):
            asyncio.run(_query(statement))
        _alembic("upgrade", "head")
        report: dict[str, Any] = {"after_upgrade": _public_tables()}
        report["enum_types"] = asyncio.run(
            _query("SELECT typname FROM pg_type WHERE typtype = 'e'")
        )
        _alembic("downgrade", "base")
        report["after_downgrade"] = _public_tables()
        _alembic("upgrade", "head")
        report["after_reupgrade"] = _public_tables()
        return report
    finally:
        settings.DATABASE_URL = original_url


@pytest.fixture
async def session_factory(
    migration_report: dict[str, Any],
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    tables = ", ".join(sorted(CANONICAL_TABLES - {"system_settings"}))
    async with engine.begin() as conn:
        await conn.exec_driver_sql(f"TRUNCATE {tables} CASCADE")
    await engine.dispose()


def _user(email: str = "ana@wwf.org") -> User:
    return User(email=email, password_hash="x", full_name="Ana")


def _camera(owner: Owner, code: str = "CAM01", **extra: Any) -> CameraStation:
    camera = CameraStation(
        code=code,
        latitude=Decimal("-17.783450"),
        longitude=Decimal("-63.182110"),
        deployed_at=datetime(2026, 3, 1, 8, 30),
        **extra,
    )
    owner.assign_to(camera, anon_retain=True)
    return camera


def _classification(owner: Owner, camera_id: uuid.UUID, **extra: Any) -> Classification:
    row = Classification(
        camera_station_id=camera_id,
        file_name="CAM01_20260315_042210.mp4",
        file_sha256="a" * 64,
        file_size_bytes=1024,
        media_type=MediaType.VIDEO,
        **extra,
    )
    owner.assign_to(row, anon_retain=True)
    return row


async def _new_user(factory: async_sessionmaker[AsyncSession], email: str) -> Owner:
    async with UnitOfWork(factory) as uow:
        user = uow.users.add(_user(email))
        await uow.commit()
        return Owner(user_id=user.id)


# --- CA-2: migración ---------------------------------------------------------------------------


def test_migration_drops_legacy_schema_and_round_trips(migration_report: dict[str, Any]) -> None:
    assert migration_report["after_upgrade"] == CANONICAL_TABLES
    assert "species" not in migration_report["after_upgrade"]
    assert migration_report["enum_types"] == []  # el ENUM nativo legado también se fue
    assert migration_report["after_downgrade"] == set()
    assert migration_report["after_reupgrade"] == CANONICAL_TABLES


async def test_migration_seeds_anon_data_retention(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with UnitOfWork(session_factory) as uow:
        assert await uow.settings.get_value("anon_data_retention") is True


# --- CA-1 (Nivel 1): integridad en la BD -------------------------------------------------------


async def test_camera_code_is_unique_per_owner_case_insensitive_among_active(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CB-13: borrada + activa con el mismo código: sí. Dos activas ("CAM01"/"cam01"): no."""
    ana = await _new_user(session_factory, "ana@wwf.org")
    luis = await _new_user(session_factory, "luis@wwf.org")
    async with UnitOfWork(session_factory) as uow:
        uow.camera_stations.add(_camera(ana, "CAM01", is_deleted=True))
        uow.camera_stations.add(_camera(ana, "cam01"))
        uow.camera_stations.add(_camera(luis, "CAM01"))  # otro dueño
        await uow.commit()

    async with UnitOfWork(session_factory) as uow:
        uow.camera_stations.add(_camera(ana, "Cam01"))
        with pytest.raises(IntegrityError, match="uq_camera_stations_user_code"):
            await uow.camera_stations.flush()


@pytest.mark.parametrize("owners", ["none", "both"])
async def test_owner_must_be_user_xor_anon_session(
    session_factory: async_sessionmaker[AsyncSession], owners: str
) -> None:
    ana = await _new_user(session_factory, "ana@wwf.org")
    async with UnitOfWork(session_factory) as uow:
        session = uow.anon_sessions.add(
            AnonSession(token_hash="h" * 64, expires_at=datetime(2030, 1, 1, tzinfo=UTC))
        )
        await uow.commit()
    camera = _camera(ana)
    camera.owner_user_id = None if owners == "none" else ana.user_id
    camera.anon_session_id = session.id if owners == "both" else None

    async with UnitOfWork(session_factory) as uow:
        uow.camera_stations.add(camera)
        with pytest.raises(IntegrityError, match="owner_xor"):
            await uow.camera_stations.flush()


async def test_same_file_counts_once_per_camera(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CB-50: mismo sha256 en la misma cámara solo una vez si está activo; en error u otra, sí."""
    ana = await _new_user(session_factory, "ana@wwf.org")
    async with UnitOfWork(session_factory) as uow:
        cam1 = uow.camera_stations.add(_camera(ana, "CAM01"))
        cam2 = uow.camera_stations.add(_camera(ana, "CAM02"))
        await uow.camera_stations.flush()
        uow.classifications.add(_classification(ana, cam1.id, status=ClassificationStatus.DONE))
        uow.classifications.add(_classification(ana, cam1.id, status=ClassificationStatus.ERROR))
        uow.classifications.add(_classification(ana, cam2.id, status=ClassificationStatus.QUEUED))
        await uow.commit()

    async with UnitOfWork(session_factory) as uow:
        assert await uow.classifications.find_active_by_sha256(cam1.id, "a" * 64) is not None
        other = await uow.classifications.find_sha256_in_other_cameras(ana, "a" * 64, cam1.id)
        assert other is not None and other.camera_station_id == cam2.id  # CB-51
        uow.classifications.add(_classification(ana, cam1.id, status=ClassificationStatus.QUEUED))
        with pytest.raises(IntegrityError, match="uq_classifications_camera_sha256_active"):
            await uow.classifications.flush()


async def test_enum_columns_reject_values_outside_the_catalog(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(IntegrityError, match="role"):
            await session.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, full_name, role) "
                    "VALUES (gen_random_uuid(), 'x@x.org', 'x', 'X', 'superadmin')"
                )
            )


# --- CA-3: UnitOfWork y repositorios ----------------------------------------------------------


async def test_unit_of_work_only_persists_on_explicit_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with UnitOfWork(session_factory) as uow:
        uow.users.add(_user("sin-commit@wwf.org"))  # sale sin commit
    with pytest.raises(RuntimeError):
        async with UnitOfWork(session_factory) as uow:
            uow.users.add(_user("con-error@wwf.org"))
            await uow.users.flush()
            raise RuntimeError("falla a mitad del caso de uso")

    async with UnitOfWork(session_factory) as uow:
        assert await uow.users.get_by_email("sin-commit@wwf.org") is None
        assert await uow.users.get_by_email("con-error@wwf.org") is None


def test_repositories_never_commit_and_models_have_no_selectin_cascades() -> None:
    for path in (ROOT / "app" / "repositories").glob("*.py"):
        assert not re.search(r"\.commit\(", path.read_text(encoding="utf-8")), path
    for path in (ROOT / "app" / "models").glob("*.py"):
        assert 'lazy="selectin"' not in path.read_text(encoding="utf-8"), path


async def test_private_resources_of_others_are_invisible(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """S1/IDOR: lo privado ajeno no existe para el repositorio (el servicio responderá 404)."""
    ana = await _new_user(session_factory, "ana@wwf.org")
    luis = await _new_user(session_factory, "luis@wwf.org")
    async with UnitOfWork(session_factory) as uow:
        private = uow.camera_stations.add(_camera(ana, "PRIV"))
        public = uow.camera_stations.add(_camera(ana, "PUB", visibility=Visibility.PUBLIC))
        await uow.camera_stations.flush()
        row = uow.classifications.add(_classification(ana, private.id))
        await uow.commit()

    async with UnitOfWork(session_factory) as uow:
        assert await uow.camera_stations.get_visible(private.id, ana) is not None
        assert await uow.camera_stations.get_visible(private.id, luis) is None
        assert await uow.camera_stations.get_visible(private.id, None) is None
        assert await uow.camera_stations.get_visible(public.id, luis) is not None
        assert await uow.camera_stations.get_owned(public.id, luis) is None
        assert await uow.classifications.get_visible(row.id, luis) is None
        cameras, total = await uow.camera_stations.list_visible(luis)
        assert total == 1 and cameras[0].id == public.id


async def test_user_email_is_unique_case_insensitive(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _new_user(session_factory, "Ana@WWF.org")
    async with UnitOfWork(session_factory) as uow:
        assert await uow.users.get_by_email("  ana@wwf.ORG ") is not None
        uow.users.add(_user("ana@wwf.org"))
        with pytest.raises(IntegrityError, match="uq_users_email_lower"):
            await uow.users.flush()


async def test_revoke_all_refresh_tokens_for_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CB-78: ante reuso de un refresh rotado se revocan todos los activos del usuario."""
    ana = await _new_user(session_factory, "ana@wwf.org")
    assert ana.user_id is not None
    async with UnitOfWork(session_factory) as uow:
        for n in range(3):
            uow.refresh_tokens.add(
                RefreshToken(
                    user_id=ana.user_id,
                    token_hash=f"t{n}",
                    expires_at=datetime(2030, 1, 1, tzinfo=UTC),
                )
            )
        await uow.commit()

    async with UnitOfWork(session_factory) as uow:
        assert await uow.refresh_tokens.revoke_all_for_user(ana.user_id, datetime.now(UTC)) == 3
        await uow.commit()
    async with UnitOfWork(session_factory) as uow:
        token = await uow.refresh_tokens.get_by_hash("t1")
        assert token is not None and token.revoked_at is not None
