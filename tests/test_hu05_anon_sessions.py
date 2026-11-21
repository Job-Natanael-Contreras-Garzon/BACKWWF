"""HU-05: Sesiones anónimas, get_owner, claim atómico, register/login hint y purga FL-30."""

import asyncio
import io
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import AnonSessionDep, OwnerDep, get_uow
from app.cli import main as cli_main
from app.core.config import settings
from app.core.enums import AnonSessionStatus, MediaType
from app.core.logging import JsonFormatter
from app.core.security import hash_token
from app.db.uow import UnitOfWork
from app.integrations.storage.local import LocalStorage
from app.main import app, register_exception_handlers
from app.models import (
    AnonPurgeRun,
    CameraStation,
    Classification,
    ClassificationBatch,
    Project,
    SystemSetting,
)
from app.services import anon_session_service, auth_service
from app.services.policies import Owner
from app.worker.cron_anon import purge_anon_sessions

ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
requires_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no definida")


@pytest.fixture(scope="module")
def migrated_test_db() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL no definida")
    original_url = settings.DATABASE_URL
    settings.DATABASE_URL = TEST_DATABASE_URL
    try:
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    finally:
        settings.DATABASE_URL = original_url
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
    anon_session_service.anon_session_rate_limiter.reset()
    auth_service.login_rate_limiter.reset()
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "TRUNCATE classifications, classification_batches, project_camera_stations, "
            "projects, camera_stations, anon_purge_runs, anon_sessions, "
            "refresh_tokens, users CASCADE"
        )
        await conn.exec_driver_sql(
            "INSERT INTO system_settings (key, value) "
            "VALUES ('anon_data_retention', 'true'::jsonb) "
            "ON CONFLICT (key) DO UPDATE SET value = 'true'::jsonb"
        )
    try:
        yield factory
    finally:
        app.dependency_overrides.pop(get_uow, None)
        anon_session_service.anon_session_rate_limiter.reset()
        auth_service.login_rate_limiter.reset()
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                "TRUNCATE classifications, classification_batches, project_camera_stations, "
                "projects, camera_stations, anon_purge_runs, anon_sessions, "
                "refresh_tokens, users CASCADE"
            )
            await conn.exec_driver_sql(
                "INSERT INTO system_settings (key, value) "
                "VALUES ('anon_data_retention', 'true'::jsonb) "
                "ON CONFLICT (key) DO UPDATE SET value = 'true'::jsonb"
            )
        await engine.dispose()


def _client(ip: str = "198.51.100.10") -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 54321)),
        base_url="http://testserver",
    )


def _new_camera(
    owner: Owner,
    code: str,
    *,
    anon_retain: bool = True,
    is_deleted: bool = False,
) -> CameraStation:
    cam = CameraStation(
        code=code,
        name=f"Cam {code}",
        latitude=Decimal("-17.783300"),
        longitude=Decimal("-63.182100"),
        deployed_at=datetime(2026, 3, 15, 8, 0, 0),
        is_deleted=is_deleted,
    )
    owner.assign_to(cam, anon_retain=anon_retain)
    return cam


def _new_project(
    owner: Owner,
    name: str,
    *,
    anon_retain: bool = True,
    is_deleted: bool = False,
) -> Project:
    proj = Project(name=name, is_deleted=is_deleted)
    owner.assign_to(proj, anon_retain=anon_retain)
    return proj


def _new_batch(
    owner: Owner,
    camera_id: uuid.UUID,
    *,
    anon_retain: bool = True,
    is_deleted: bool = False,
) -> ClassificationBatch:
    batch = ClassificationBatch(
        camera_station_id=camera_id,
        expected_files=1,
        is_deleted=is_deleted,
    )
    owner.assign_to(batch, anon_retain=anon_retain)
    return batch


def _new_classification(
    owner: Owner,
    camera_id: uuid.UUID,
    *,
    batch_id: uuid.UUID | None = None,
    seed: str = "a",
    evidence_key: str | None = None,
    anon_retain: bool = True,
    is_deleted: bool = False,
) -> Classification:
    digest = hash_token(f"{seed}-{uuid.uuid4()}")
    row = Classification(
        camera_station_id=camera_id,
        batch_id=batch_id,
        file_name=f"{seed}.jpg",
        file_sha256=digest,
        file_size_bytes=1234,
        media_type=MediaType.IMAGE,
        evidence_key=evidence_key,
        is_deleted=is_deleted,
    )
    owner.assign_to(row, anon_retain=anon_retain)
    return row


async def _register_user(client: httpx.AsyncClient, email: str) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password1", "full_name": "Investigador"},
    )
    assert resp.status_code == 201
    return dict(resp.json()["data"])


async def _create_anon(client: httpx.AsyncClient) -> tuple[str, dict[str, Any]]:
    resp = await client.post("/api/v1/anon-sessions")
    assert resp.status_code == 201
    data = resp.json()["data"]
    return str(data["anon_token"]), dict(data)


# ---------------------------------------------------------------------------
# Creación, hash, redacción de logs y rate limit IP (FL-03)
# ---------------------------------------------------------------------------


@requires_db
async def test_create_anon_session_hashes_token_and_never_logs_raw_token(
    db_session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    async with _client() as client:
        token, payload = await _create_anon(client)

    assert len(token) == 43
    assert payload["data_retention"] is True
    expires_at = datetime.fromisoformat(payload["expires_at"])
    remaining_hours = (expires_at - datetime.now(UTC)).total_seconds() / 3600
    assert 23.9 <= remaining_hours <= 24.1

    async with UnitOfWork(db_session_factory) as uow:
        stored = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert stored is not None
        assert stored.token_hash != token
        assert stored.status == AnonSessionStatus.ACTIVE

    formatter = JsonFormatter()
    formatted_logs = "\n".join(formatter.format(rec) for rec in caplog.records)
    assert token not in formatted_logs


@requires_db
async def test_create_anon_session_rate_limit_5_per_hour_ignores_xff(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(ip="198.51.100.77") as client:
        for i in range(5):
            r = await client.post(
                "/api/v1/anon-sessions",
                headers={"X-Forwarded-For": f"203.0.113.{i}"},
            )
            assert r.status_code == 201

        blocked = await client.post(
            "/api/v1/anon-sessions",
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"

    async with _client(ip="198.51.100.78") as other:
        ok_other = await other.post("/api/v1/anon-sessions")
        assert ok_other.status_code == 201


# ---------------------------------------------------------------------------
# get_anon_session, sliding expiry, /current y get_owner
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.parametrize(
    "case",
    ["missing", "blank", "unknown", "expired_time", "status_expired", "status_claimed"],
)
async def test_anon_session_rejects_invalid_or_expired_tokens_with_401(
    db_session_factory: async_sessionmaker[AsyncSession],
    case: str,
) -> None:
    headers: dict[str, str] = {}
    async with _client() as client:
        if case == "missing":
            headers = {}
        elif case == "blank":
            headers = {"X-Anon-Token": "   "}
        elif case == "unknown":
            headers = {"X-Anon-Token": "non-existent-token-123"}
        else:
            token, _ = await _create_anon(client)
            headers = {"X-Anon-Token": token}
            async with UnitOfWork(db_session_factory) as uow:
                row = await uow.anon_sessions.get_by_token_hash(hash_token(token))
                assert row is not None
                if case == "expired_time":
                    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                elif case == "status_expired":
                    row.status = AnonSessionStatus.EXPIRED
                elif case == "status_claimed":
                    row.status = AnonSessionStatus.CLAIMED
                await uow.commit()

        resp = await client.get("/api/v1/anon-sessions/current", headers=headers)

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "ANON_SESSION_EXPIRED"


@requires_db
async def test_sliding_expiry_commits_touch_over_60s_even_on_downstream_rollback(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        token, _ = await _create_anon(client)

    # 1) Menos de 60s desde last_activity_at: no escribe nuevo expires_at
    async with UnitOfWork(db_session_factory) as uow:
        row = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert row is not None
        recent_touch = datetime.now(UTC) - timedelta(seconds=20)
        fixed_exp = datetime.now(UTC) + timedelta(hours=12)
        row.last_activity_at = recent_touch
        row.expires_at = fixed_exp
        await uow.commit()

    async with _client() as client:
        r_recent = await client.get(
            "/api/v1/anon-sessions/current", headers={"X-Anon-Token": token}
        )
        assert r_recent.status_code == 200

    async with UnitOfWork(db_session_factory) as uow:
        row_after = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert row_after is not None
        assert row_after.expires_at == fixed_exp

    # 2) >= 60s y el endpoint falla después: el touch persiste tras rollback del UoW
    probe_app = FastAPI()
    register_exception_handlers(probe_app)

    async def override_uow() -> AsyncIterator[UnitOfWork]:
        async with UnitOfWork(db_session_factory) as uow:
            yield uow

    probe_app.dependency_overrides[get_uow] = override_uow

    @probe_app.get("/probe/fail")
    async def fail_after_anon(anon: AnonSessionDep) -> None:
        raise RuntimeError(f"fallo posterior para {anon.id}")

    async with UnitOfWork(db_session_factory) as uow:
        row2 = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert row2 is not None
        row2.last_activity_at = datetime.now(UTC) - timedelta(seconds=120)
        row2.expires_at = datetime.now(UTC) + timedelta(hours=1)
        await uow.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=probe_app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as probe_client:
        fail_resp = await probe_client.get("/probe/fail", headers={"X-Anon-Token": token})
        assert fail_resp.status_code == 500

    async with UnitOfWork(db_session_factory) as uow:
        touched = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert touched is not None
        assert (touched.expires_at - datetime.now(UTC)).total_seconds() > 23 * 3600


@requires_db
async def test_current_counts_exclude_soft_deleted_and_expose_limits(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        token, _ = await _create_anon(client)

    async with UnitOfWork(db_session_factory) as uow:
        session = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert session is not None
        owner = Owner(anon_session_id=session.id)
        c1 = uow.camera_stations.add(_new_camera(owner, "CAM01"))
        c_del = uow.camera_stations.add(_new_camera(owner, "CAMDEL", is_deleted=True))
        await uow.camera_stations.flush()
        uow.projects.add(_new_project(owner, "P1"))
        uow.projects.add(_new_project(owner, "P2", is_deleted=True))
        uow.classifications.add(_new_classification(owner, c1.id, seed="ok1"))
        uow.classifications.add(_new_classification(owner, c1.id, seed="ok2"))
        uow.classifications.add(_new_classification(owner, c_del.id, seed="del", is_deleted=True))
        await uow.commit()

    async with _client() as client:
        resp = await client.get("/api/v1/anon-sessions/current", headers={"X-Anon-Token": token})

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["status"] == "active"
    assert body["data_retention"] is True
    assert body["counts"] == {"classifications": 2, "camera_stations": 1, "projects": 1}
    assert body["limits"] == {
        "max_files": settings.ANON_MAX_FILES,
        "max_camera_stations": settings.ANON_MAX_CAMERAS,
        "used_files": 2,
        "used_camera_stations": 1,
    }


@requires_db
async def test_get_owner_bearer_wins_over_anon_and_missing_returns_401(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    probe_app = FastAPI()
    register_exception_handlers(probe_app)

    async def override_uow() -> AsyncIterator[UnitOfWork]:
        async with UnitOfWork(db_session_factory) as uow:
            yield uow

    probe_app.dependency_overrides[get_uow] = override_uow

    @probe_app.get("/probe/owner")
    async def whoami(owner: OwnerDep) -> dict[str, str | None]:
        return {
            "user_id": str(owner.user_id) if owner.user_id else None,
            "anon_session_id": str(owner.anon_session_id) if owner.anon_session_id else None,
        }

    async with _client() as main_client:
        user_data = await _register_user(main_client, "owner@wwf.org")
        token, _ = await _create_anon(main_client)

    async with UnitOfWork(db_session_factory) as uow:
        anon_row = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert anon_row is not None
        anon_id = str(anon_row.id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=probe_app),
        base_url="http://testserver",
    ) as probe_client:
        both = await probe_client.get(
            "/probe/owner",
            headers={
                "Authorization": f"Bearer {user_data['tokens']['access_token']}",
                "X-Anon-Token": "invalid-ignored-because-bearer-wins",
            },
        )
        only_anon = await probe_client.get(
            "/probe/owner",
            headers={"X-Anon-Token": token},
        )
        none = await probe_client.get("/probe/owner")

    assert both.status_code == 200
    assert both.json() == {"user_id": user_data["user"]["id"], "anon_session_id": None}
    assert only_anon.status_code == 200
    assert only_anon.json() == {"user_id": None, "anon_session_id": anon_id}
    assert none.status_code == 401
    assert none.json()["error"]["code"] == "AUTH_REQUIRED"


# ---------------------------------------------------------------------------
# Claim atómico, idempotencia, conflicto, colisiones y concurrencia (FL-04)
# ---------------------------------------------------------------------------


@requires_db
async def test_claim_moves_all_4_tables_including_soft_deleted_and_handles_idempotency_conflict(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        ana = await _register_user(client, "ana@wwf.org")
        luis = await _register_user(client, "luis@wwf.org")
        token, _ = await _create_anon(client)

    ana_id = uuid.UUID(ana["user"]["id"])
    async with UnitOfWork(db_session_factory) as uow:
        session = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert session is not None
        anon_owner = Owner(anon_session_id=session.id)
        cam = uow.camera_stations.add(_new_camera(anon_owner, "CAM01"))
        cam_del = uow.camera_stations.add(_new_camera(anon_owner, "CAMDEL", is_deleted=True))
        await uow.camera_stations.flush()
        uow.projects.add(_new_project(anon_owner, "Proyecto 1"))
        batch = uow.batches.add(_new_batch(anon_owner, cam.id))
        await uow.batches.flush()
        uow.classifications.add(
            _new_classification(anon_owner, cam.id, batch_id=batch.id, seed="c1")
        )
        uow.classifications.add(
            _new_classification(anon_owner, cam_del.id, seed="c_del", is_deleted=True)
        )
        await uow.commit()

    ana_headers = {
        "Authorization": f"Bearer {ana['tokens']['access_token']}",
        "X-Anon-Token": token,
    }
    luis_headers = {
        "Authorization": f"Bearer {luis['tokens']['access_token']}",
        "X-Anon-Token": token,
    }
    async with _client() as client:
        claimed = await client.post("/api/v1/anon-sessions/claim", headers=ana_headers)
        again = await client.post("/api/v1/anon-sessions/claim", headers=ana_headers)
        conflict = await client.post("/api/v1/anon-sessions/claim", headers=luis_headers)
        after_current = await client.get(
            "/api/v1/anon-sessions/current", headers={"X-Anon-Token": token}
        )

    assert claimed.status_code == 200
    assert claimed.json()["data"] == {
        "claimed": {"classifications": 1, "camera_stations": 1, "projects": 1},
        "renamed_camera_stations": [],
    }
    assert again.status_code == 200
    assert again.json()["data"] == {
        "claimed": {"classifications": 0, "camera_stations": 0, "projects": 0},
        "renamed_camera_stations": [],
    }
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ANON_SESSION_ALREADY_CLAIMED"
    assert after_current.status_code == 401
    assert after_current.json()["error"]["code"] == "ANON_SESSION_EXPIRED"

    async with UnitOfWork(db_session_factory) as uow:
        s_db = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert s_db is not None
        assert s_db.status == AnonSessionStatus.CLAIMED
        assert s_db.claimed_by_user_id == ana_id
        for model in (CameraStation, Project, ClassificationBatch, Classification):
            remaining_anon = await uow.session.scalar(
                select(func.count()).select_from(model).where(model.anon_session_id == s_db.id)
            )
            moved_rows = list(
                await uow.session.scalars(select(model).where(model.owner_user_id == ana_id))
            )
            assert remaining_anon == 0
            assert len(moved_rows) >= 1
            assert all(r.anon_retain is None for r in moved_rows)


@requires_db
async def test_claim_renames_camera_collisions_case_insensitively_within_50_chars(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        ana = await _register_user(client, "rename@wwf.org")
        token, _ = await _create_anon(client)

    ana_id = uuid.UUID(ana["user"]["id"])
    long_code = "X" * 50
    async with UnitOfWork(db_session_factory) as uow:
        ana_owner = Owner(user_id=ana_id)
        uow.camera_stations.add(_new_camera(ana_owner, "CAM01"))
        uow.camera_stations.add(_new_camera(ana_owner, long_code))

        session = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert session is not None
        anon_owner = Owner(anon_session_id=session.id)
        # "cam01" choca con "CAM01"; además la sesión ya tiene "CAM01-2" -> debe saltar a "-3"
        c_coll = uow.camera_stations.add(_new_camera(anon_owner, "cam01"))
        c_existing_2 = uow.camera_stations.add(_new_camera(anon_owner, "CAM01-2"))
        c_long = uow.camera_stations.add(_new_camera(anon_owner, long_code.lower()))
        await uow.commit()

    async with _client() as client:
        resp = await client.post(
            "/api/v1/anon-sessions/claim",
            headers={
                "Authorization": f"Bearer {ana['tokens']['access_token']}",
                "X-Anon-Token": token,
            },
        )

    assert resp.status_code == 200
    renames = {r["id"]: r for r in resp.json()["data"]["renamed_camera_stations"]}
    assert set(renames.keys()) == {str(c_coll.id), str(c_long.id)}
    assert renames[str(c_coll.id)]["old_code"] == "cam01"
    assert renames[str(c_coll.id)]["new_code"] == "cam01-3"
    assert renames[str(c_long.id)]["new_code"] == f"{'x' * 48}-2"
    assert len(renames[str(c_long.id)]["new_code"]) == 50

    async with UnitOfWork(db_session_factory) as uow:
        codes = set(await uow.camera_stations.list_active_codes_for_user(ana_id))
        assert codes == {"CAM01", "cam01-3", "CAM01-2", long_code, f"{'x' * 48}-2"}
        kept = await uow.camera_stations.get(c_existing_2.id)
        assert kept is not None and kept.code == "CAM01-2"


@requires_db
async def test_claim_rejects_expired_closed_and_missing_tokens(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        ana = await _register_user(client, "expclaim@wwf.org")
        token_closed, _ = await _create_anon(client)
        token_time, _ = await _create_anon(client)

        bearer = {"Authorization": f"Bearer {ana['tokens']['access_token']}"}
        close_resp = await client.post(
            "/api/v1/anon-sessions/current/close", headers={"X-Anon-Token": token_closed}
        )
        assert close_resp.status_code == 200

    async with UnitOfWork(db_session_factory) as uow:
        s_time = await uow.anon_sessions.get_by_token_hash(hash_token(token_time))
        assert s_time is not None
        s_time.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await uow.commit()

    async with _client() as client:
        for bad_headers in (
            bearer,
            {**bearer, "X-Anon-Token": "unknown-token"},
            {**bearer, "X-Anon-Token": token_closed},
            {**bearer, "X-Anon-Token": token_time},
        ):
            r = await client.post("/api/v1/anon-sessions/claim", headers=bad_headers)
            assert r.status_code == 401
            assert r.json()["error"]["code"] == "ANON_SESSION_EXPIRED"


@requires_db
async def test_claim_is_atomic_on_forced_mid_transaction_failure(
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _client() as client:
        ana = await _register_user(client, "atomic@wwf.org")
        token, _ = await _create_anon(client)

    async with UnitOfWork(db_session_factory) as uow:
        session = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert session is not None
        anon_owner = Owner(anon_session_id=session.id)
        cam = uow.camera_stations.add(_new_camera(anon_owner, "CAM_ATOM"))
        await uow.camera_stations.flush()
        uow.projects.add(_new_project(anon_owner, "Proj Atom"))
        uow.classifications.add(_new_classification(anon_owner, cam.id, seed="atom"))
        await uow.commit()

    original_transfer = anon_session_service.ClaimAnonSessionData

    async def boom_commit(self: UnitOfWork) -> None:
        raise RuntimeError("fallo forzado antes de commit")

    monkeypatch.setattr(UnitOfWork, "commit", boom_commit)
    _ = original_transfer

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            "/api/v1/anon-sessions/claim",
            headers={
                "Authorization": f"Bearer {ana['tokens']['access_token']}",
                "X-Anon-Token": token,
            },
        )
    assert resp.status_code == 500
    monkeypatch.undo()

    async with UnitOfWork(db_session_factory) as uow:
        s_db = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert s_db is not None
        assert s_db.status == AnonSessionStatus.ACTIVE
        assert s_db.claimed_by_user_id is None
        counts = await uow.anon_sessions.count_active_resources(s_db.id)
        assert counts == (1, 1, 1)


@requires_db
async def test_claim_concurrent_double_claim_two_connections(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        ana = await _register_user(client, "race1@wwf.org")
        luis = await _register_user(client, "race2@wwf.org")
        t_same, _ = await _create_anon(client)
        t_diff, _ = await _create_anon(client)

    async with UnitOfWork(db_session_factory) as uow:
        s_same = await uow.anon_sessions.get_by_token_hash(hash_token(t_same))
        s_diff = await uow.anon_sessions.get_by_token_hash(hash_token(t_diff))
        assert s_same is not None and s_diff is not None
        uow.camera_stations.add(_new_camera(Owner(anon_session_id=s_same.id), "RACE1"))
        uow.camera_stations.add(_new_camera(Owner(anon_session_id=s_diff.id), "RACE2"))
        await uow.commit()

    # Mismo usuario en dos conexiones independientes -> ambos 200 (uno 1, otro 0 idempotente)
    async with _client() as c1, _client() as c2:
        ana_h = {
            "Authorization": f"Bearer {ana['tokens']['access_token']}",
            "X-Anon-Token": t_same,
        }
        r1, r2 = await asyncio.gather(
            c1.post("/api/v1/anon-sessions/claim", headers=ana_h),
            c2.post("/api/v1/anon-sessions/claim", headers=ana_h),
        )
    assert {r1.status_code, r2.status_code} == {200}
    cam_counts = sorted(
        [
            r1.json()["data"]["claimed"]["camera_stations"],
            r2.json()["data"]["claimed"]["camera_stations"],
        ]
    )
    assert cam_counts == [0, 1]

    # Dos usuarios distintos en paralelo -> uno 200 y el otro 409 ANON_SESSION_ALREADY_CLAIMED
    async with _client() as c1, _client() as c2:
        res_a, res_b = await asyncio.gather(
            c1.post(
                "/api/v1/anon-sessions/claim",
                headers={
                    "Authorization": f"Bearer {ana['tokens']['access_token']}",
                    "X-Anon-Token": t_diff,
                },
            ),
            c2.post(
                "/api/v1/anon-sessions/claim",
                headers={
                    "Authorization": f"Bearer {luis['tokens']['access_token']}",
                    "X-Anon-Token": t_diff,
                },
            ),
        )
    statuses = sorted([res_a.status_code, res_b.status_code])
    assert statuses == [200, 409]
    conflict_resp = res_a if res_a.status_code == 409 else res_b
    assert conflict_resp.json()["error"]["code"] == "ANON_SESSION_ALREADY_CLAIMED"


@requires_db
async def test_claim_concurrent_cross_session_same_user_camera_collision_two_connections(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        ana = await _register_user(client, "crossrace@wwf.org")
        t1, _ = await _create_anon(client)
        t2, _ = await _create_anon(client)

    ana_id = uuid.UUID(ana["user"]["id"])
    async with UnitOfWork(db_session_factory) as uow:
        s1 = await uow.anon_sessions.get_by_token_hash(hash_token(t1))
        s2 = await uow.anon_sessions.get_by_token_hash(hash_token(t2))
        assert s1 is not None and s2 is not None
        uow.camera_stations.add(_new_camera(Owner(anon_session_id=s1.id), "CAM01"))
        uow.camera_stations.add(_new_camera(Owner(anon_session_id=s2.id), "CAM01"))
        await uow.commit()

    # Dos sesiones anónimas distintas reclamadas en paralelo por el mismo usuario: ambas 200
    async with _client() as c1, _client() as c2:
        r1, r2 = await asyncio.gather(
            c1.post(
                "/api/v1/anon-sessions/claim",
                headers={
                    "Authorization": f"Bearer {ana['tokens']['access_token']}",
                    "X-Anon-Token": t1,
                },
            ),
            c2.post(
                "/api/v1/anon-sessions/claim",
                headers={
                    "Authorization": f"Bearer {ana['tokens']['access_token']}",
                    "X-Anon-Token": t2,
                },
            ),
        )

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["data"]["claimed"]["camera_stations"] == 1
    assert r2.json()["data"]["claimed"]["camera_stations"] == 1
    all_renames = (
        r1.json()["data"]["renamed_camera_stations"] + r2.json()["data"]["renamed_camera_stations"]
    )
    assert len(all_renames) == 1
    assert all_renames[0]["old_code"] == "CAM01"
    assert all_renames[0]["new_code"] == "CAM01-2"

    async with UnitOfWork(db_session_factory) as uow:
        codes = set(await uow.camera_stations.list_active_codes_for_user(ana_id))
        assert codes == {"CAM01", "CAM01-2"}


# ---------------------------------------------------------------------------
# Close ("No asociar") y register/login anon_session hint
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.parametrize(
    ("row_retain", "setting_value", "expected_retained"),
    [
        (False, True, False),
        (True, False, True),
        (None, False, False),
        (None, True, True),
    ],
)
async def test_close_session_sets_expired_without_deleting_and_computes_data_retained(
    db_session_factory: async_sessionmaker[AsyncSession],
    row_retain: bool | None,
    setting_value: bool,
    expected_retained: bool,
) -> None:
    async with _client() as client:
        token, _ = await _create_anon(client)

    async with UnitOfWork(db_session_factory) as uow:
        setting = await uow.session.get(SystemSetting, "anon_data_retention")
        assert setting is not None
        setting.value = setting_value
        session = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert session is not None
        if row_retain is not None:
            uow.camera_stations.add(
                _new_camera(Owner(anon_session_id=session.id), "C_CLOSE", anon_retain=row_retain)
            )
        await uow.commit()

    async with _client() as client:
        resp = await client.post(
            "/api/v1/anon-sessions/current/close",
            headers={"X-Anon-Token": token},
        )
        after = await client.get("/api/v1/anon-sessions/current", headers={"X-Anon-Token": token})

    assert resp.status_code == 200
    assert resp.json()["data"] == {"status": "expired", "data_retained": expected_retained}
    assert after.status_code == 401

    if row_retain is not None:
        async with UnitOfWork(db_session_factory) as uow:
            cams = await uow.camera_stations.list_active_for_anon(session.id)
            assert len(cams) == 1  # No borra físicamente: eso es trabajo de FL-30


@requires_db
async def test_register_and_login_return_anon_session_hint_without_claiming_or_failing(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        token_with_data, _ = await _create_anon(client)
        token_empty, _ = await _create_anon(client)
        token_closed, _ = await _create_anon(client)
        await client.post(
            "/api/v1/anon-sessions/current/close",
            headers={"X-Anon-Token": token_closed},
        )

    async with UnitOfWork(db_session_factory) as uow:
        s_data = await uow.anon_sessions.get_by_token_hash(hash_token(token_with_data))
        assert s_data is not None
        owner = Owner(anon_session_id=s_data.id)
        cam = uow.camera_stations.add(_new_camera(owner, "CAM_HINT"))
        await uow.camera_stations.flush()
        uow.classifications.add(_new_classification(owner, cam.id, seed="hint"))
        await uow.commit()

    async with _client() as client:
        reg_with_data = await client.post(
            "/api/v1/auth/register",
            headers={"X-Anon-Token": token_with_data},
            json={"email": "hint@wwf.org", "password": "Password1", "full_name": "Hint"},
        )
        login_empty = await client.post(
            "/api/v1/auth/login",
            headers={"X-Anon-Token": token_empty},
            json={"email": "hint@wwf.org", "password": "Password1"},
        )
        login_expired = await client.post(
            "/api/v1/auth/login",
            headers={"X-Anon-Token": token_closed},
            json={"email": "hint@wwf.org", "password": "Password1"},
        )
        login_bad = await client.post(
            "/api/v1/auth/login",
            headers={"X-Anon-Token": "bad-token"},
            json={"email": "hint@wwf.org", "password": "Password1"},
        )

    assert reg_with_data.status_code == 201
    assert reg_with_data.json()["data"]["anon_session"] == {
        "has_data": True,
        "counts": {"classifications": 1, "camera_stations": 1, "projects": 0},
    }
    assert login_empty.status_code == 200
    assert login_empty.json()["data"]["anon_session"] == {
        "has_data": False,
        "counts": {"classifications": 0, "camera_stations": 0, "projects": 0},
    }
    assert login_expired.status_code == 200 and login_expired.json()["data"]["anon_session"] is None
    assert login_bad.status_code == 200 and login_bad.json()["data"]["anon_session"] is None

    # Nunca hace auto-claim: la sesión anónima sigue activa y dueña de sus datos
    async with UnitOfWork(db_session_factory) as uow:
        s_still = await uow.anon_sessions.get_by_token_hash(hash_token(token_with_data))
        assert s_still is not None and s_still.status == AnonSessionStatus.ACTIVE
        assert await uow.anon_sessions.count_active_resources(s_still.id) == (1, 1, 0)


# ---------------------------------------------------------------------------
# Purga FL-30 + CLI + CB-42/43
# ---------------------------------------------------------------------------


@requires_db
async def test_fl30_purge_retains_true_deletes_false_and_frames_post_commit_idempotent(
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = LocalStorage(tmp_path)
    await storage.put("evidence/2026/11/purge1.jpg", b"jpg-1", "image/jpeg")
    await storage.put("evidence/2026/11/keep1.jpg", b"jpg-2", "image/jpeg")

    async with _client() as client:
        t_exp, _ = await _create_anon(client)
        t_live, _ = await _create_anon(client)

    past = datetime.now(UTC) - timedelta(hours=25)
    async with UnitOfWork(db_session_factory) as uow:
        s_exp = await uow.anon_sessions.get_by_token_hash(hash_token(t_exp))
        s_live = await uow.anon_sessions.get_by_token_hash(hash_token(t_live))
        assert s_exp is not None and s_live is not None
        s_exp.expires_at = past  # sigue ACTIVE en BD hasta que FL-30 la venza

        o_exp = Owner(anon_session_id=s_exp.id)
        # CB-42/CB-43: mezcla anon_retain=false (incl. batch false con hijo true) y anon_retain=true
        cam_false = uow.camera_stations.add(_new_camera(o_exp, "CAM_F", anon_retain=False))
        cam_mixed = uow.camera_stations.add(_new_camera(o_exp, "CAM_MIX", anon_retain=False))
        cam_true = uow.camera_stations.add(_new_camera(o_exp, "CAM_T", anon_retain=True))
        await uow.camera_stations.flush()

        uow.projects.add(_new_project(o_exp, "P_FALSE", anon_retain=False))
        uow.projects.add(_new_project(o_exp, "P_TRUE", anon_retain=True))

        batch_false = uow.batches.add(_new_batch(o_exp, cam_false.id, anon_retain=False))
        batch_mixed = uow.batches.add(_new_batch(o_exp, cam_mixed.id, anon_retain=False))
        await uow.batches.flush()

        # Clasificación a purgar (con archivo), clasificación sin archivo en disco, y retenida
        uow.classifications.add(
            _new_classification(
                o_exp,
                cam_false.id,
                batch_id=batch_false.id,
                seed="p1",
                evidence_key="evidence/2026/11/purge1.jpg",
                anon_retain=False,
            )
        )
        uow.classifications.add(
            _new_classification(
                o_exp,
                cam_false.id,
                seed="missing_frame",
                evidence_key="evidence/2026/11/missing.jpg",
                anon_retain=False,
            )
        )
        uow.classifications.add(
            _new_classification(
                o_exp,
                cam_mixed.id,
                batch_id=batch_mixed.id,
                seed="keep_child",
                evidence_key="evidence/2026/11/keep1.jpg",
                anon_retain=True,
            )
        )
        uow.classifications.add(
            _new_classification(o_exp, cam_true.id, seed="keep_true", anon_retain=True)
        )

        # Sesión vigente con anon_retain=false NO debe tocarse
        uow.camera_stations.add(
            _new_camera(Owner(anon_session_id=s_live.id), "CAM_LIVE", anon_retain=False)
        )
        await uow.commit()

    def uow_factory() -> UnitOfWork:
        return UnitOfWork(db_session_factory)

    log_buf = io.StringIO()
    json_handler = logging.StreamHandler(log_buf)
    json_handler.setFormatter(JsonFormatter())
    app_logger = logging.getLogger("app")
    app_logger.addHandler(json_handler)
    caplog.set_level(logging.INFO)
    try:
        first = await purge_anon_sessions(uow_factory=uow_factory, storage=storage)
        assert first.sessions == 1
        assert first.classifications == 2
        assert first.classification_batches == 1
        assert first.camera_stations == 1
        assert first.projects == 1
        assert first.frames == 1
        assert first.retained == 4
        assert first.storage_failures == 0

        assert not await storage.exists("evidence/2026/11/purge1.jpg")
        assert await storage.exists("evidence/2026/11/keep1.jpg")

        # Segunda ejecución: idempotente, no borra ni inserta AnonPurgeRun
        second = await purge_anon_sessions(uow_factory=uow_factory, storage=storage)
        assert second.sessions == 0
        assert second.classifications == 0
        assert second.frames == 0
    finally:
        app_logger.removeHandler(json_handler)

    async with UnitOfWork(db_session_factory) as uow:
        runs = list(await uow.session.scalars(select(AnonPurgeRun)))
        assert len(runs) == 1
        assert runs[0].classifications == 2
        assert runs[0].camera_stations == 1
        assert runs[0].projects == 1
        assert runs[0].frames == 1

        s_exp_db = await uow.anon_sessions.get_by_token_hash(hash_token(t_exp))
        s_live_db = await uow.anon_sessions.get_by_token_hash(hash_token(t_live))
        assert s_exp_db is not None and s_exp_db.status == AnonSessionStatus.EXPIRED
        assert s_live_db is not None and s_live_db.status == AnonSessionStatus.ACTIVE

    parsed = [
        json.loads(line)
        for line in log_buf.getvalue().splitlines()
        if '"anon.purge.completed"' in line
    ]
    assert len(parsed) == 2
    assert parsed[0]["flow"] == "FL-30"
    assert parsed[0]["retained"] == first.retained
    assert parsed[0]["purged"]["classifications"] == 2
    dumped = log_buf.getvalue()
    assert t_exp not in dumped and hash_token(t_exp) not in dumped


@requires_db
async def test_fl30_does_not_delete_frames_if_db_commit_fails_and_counts_storage_warnings(
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = LocalStorage(tmp_path)
    await storage.put("evidence/2026/11/keep_on_err.jpg", b"keep", "image/jpeg")

    async with _client() as client:
        token, _ = await _create_anon(client)

    async with UnitOfWork(db_session_factory) as uow:
        s = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert s is not None
        s.status = AnonSessionStatus.EXPIRED
        o = Owner(anon_session_id=s.id)
        cam = uow.camera_stations.add(_new_camera(o, "C_ERR", anon_retain=False))
        await uow.camera_stations.flush()
        uow.classifications.add(
            _new_classification(
                o,
                cam.id,
                seed="err",
                evidence_key="evidence/2026/11/keep_on_err.jpg",
                anon_retain=False,
            )
        )
        await uow.commit()

    # 1) Si commit de BD falla, el fotograma NO se borra del disco
    async def fail_commit(self: UnitOfWork) -> None:
        raise RuntimeError("db commit error")

    monkeypatch.setattr(UnitOfWork, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="db commit error"):
        await purge_anon_sessions(
            uow_factory=lambda: UnitOfWork(db_session_factory),
            storage=storage,
        )
    monkeypatch.undo()
    assert await storage.exists("evidence/2026/11/keep_on_err.jpg")

    # 2) Si el storage falla después del commit, se registra WARNING y se cuenta en storage_failures
    class _BrokenStorage:
        async def put(self, key: str, data: bytes, content_type: str) -> None:
            raise OSError("disk full")

        async def get(self, key: str) -> bytes:
            raise FileNotFoundError(key)

        async def delete(self, key: str) -> None:
            raise OSError("permission denied")

        async def exists(self, key: str) -> bool:
            return True

    caplog.set_level(logging.WARNING)
    res = await purge_anon_sessions(
        uow_factory=lambda: UnitOfWork(db_session_factory),
        storage=_BrokenStorage(),
    )
    assert res.classifications == 1
    assert res.frames == 0
    assert res.storage_failures == 1
    assert any(
        r.levelno == logging.WARNING and getattr(r, "event", "") == "anon.purge.frame_delete_failed"
        for r in caplog.records
    )


@requires_db
async def test_fl30_no_deletions_creates_no_anon_purge_run_and_cli_runs(
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with _client() as client:
        token, _ = await _create_anon(client)

    async with UnitOfWork(db_session_factory) as uow:
        s = await uow.anon_sessions.get_by_token_hash(hash_token(token))
        assert s is not None
        s.status = AnonSessionStatus.EXPIRED
        uow.camera_stations.add(
            _new_camera(Owner(anon_session_id=s.id), "ONLY_RETAIN", anon_retain=True)
        )
        await uow.commit()

    summary = await purge_anon_sessions(
        uow_factory=lambda: UnitOfWork(db_session_factory),
        storage=LocalStorage(tmp_path),
    )
    assert summary.classifications == 0
    assert summary.camera_stations == 0
    assert summary.retained == 1

    async with UnitOfWork(db_session_factory) as uow:
        runs = list(await uow.session.scalars(select(AnonPurgeRun)))
        assert runs == []

    # Verificación del CLI app.cli purge-anon
    async def fake_purge() -> Any:
        return summary

    monkeypatch.setattr("app.cli.purge_anon_sessions", fake_purge)
    exit_code = await asyncio.to_thread(cli_main, ["purge-anon"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert json.loads(out)["retained"] == 1
