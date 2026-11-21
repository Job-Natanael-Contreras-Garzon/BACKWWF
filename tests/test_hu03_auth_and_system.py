"""HU-03: Auth JWT, rotación/reuso CB-78, CB-72, rate limit, /config/public y /health/ready."""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_uow
from app.api.v1.health import get_health_http_client
from app.core import rate_limit
from app.core.config import settings
from app.core.enums import UserRole
from app.core.errors import UnauthorizedError
from app.core.rate_limit import RateLimiter
from app.core.security import (
    DUMMY_BCRYPT_HASH,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    get_password_hash,
    hash_token,
    verify_password,
)
from app.db.uow import UnitOfWork
from app.integrations.ia_contract.formats import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from app.main import app
from app.models import User
from app.services import auth_service

ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
requires_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no definida")


# ---------------------------------------------------------------------------
# Fixtures DB (contra faunadb_test descartable)
# ---------------------------------------------------------------------------


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
    auth_service.login_rate_limiter.reset()
    async with engine.begin() as conn:
        await conn.exec_driver_sql("TRUNCATE refresh_tokens, users CASCADE")
    try:
        yield factory
    finally:
        app.dependency_overrides.pop(get_uow, None)
        auth_service.login_rate_limiter.reset()
        async with engine.begin() as conn:
            await conn.exec_driver_sql("TRUNCATE refresh_tokens, users CASCADE")
        await engine.dispose()


def _client(ip: str = "198.51.100.10") -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 54321)),
        base_url="http://testserver",
    )


# ---------------------------------------------------------------------------
# Tests unitarios de seguridad (sin BD)
# ---------------------------------------------------------------------------


def test_password_hash_uses_bcrypt_cost_12_and_handles_72_byte_limit() -> None:
    hashed = get_password_hash("FaunaWWF2026")
    assert hashed.startswith("$2b$12$")
    assert verify_password("FaunaWWF2026", hashed) is True
    assert verify_password("OtraClave123", hashed) is False
    # bcrypt 5.0 lanza ValueError > 72 bytes: verify_password nunca debe crashear.
    assert verify_password("a" * 100, hashed) is False
    with pytest.raises(ValueError, match="72 bytes"):
        get_password_hash("a" * 73)


def test_hash_token_is_deterministic_sha256_hex() -> None:
    digest = hash_token("sample-refresh-jwt")
    assert len(digest) == 64
    assert digest == hash_token("sample-refresh-jwt")
    assert digest != hash_token("other-refresh-jwt")


def test_decode_tokens_distinguishes_expired_invalid_and_wrong_type() -> None:
    uid = uuid.uuid4()
    sid = uuid.uuid4()
    expired_access = create_access_token(uid, session_id=sid, expires_delta=timedelta(seconds=-5))
    expired_refresh = create_refresh_token(uid, token_id=sid, expires_delta=timedelta(seconds=-5))
    valid_access = create_access_token(uid, session_id=sid)
    valid_refresh = create_refresh_token(uid, token_id=sid)

    with pytest.raises(UnauthorizedError) as exc_exp:
        decode_access_token(expired_access)
    assert exc_exp.value.code == "AUTH_TOKEN_EXPIRED"

    with pytest.raises(UnauthorizedError) as exc_rexp:
        decode_refresh_token(expired_refresh)
    assert exc_rexp.value.code == "AUTH_TOKEN_EXPIRED"

    with pytest.raises(UnauthorizedError) as exc_type:
        decode_access_token(valid_refresh)
    assert exc_type.value.code == "AUTH_TOKEN_INVALID"

    with pytest.raises(UnauthorizedError) as exc_rtype:
        decode_refresh_token(valid_access)
    assert exc_rtype.value.code == "AUTH_TOKEN_INVALID"

    with pytest.raises(UnauthorizedError) as exc_bad:
        decode_access_token("not.a.jwt")
    assert exc_bad.value.code == "AUTH_TOKEN_INVALID"

    bad_sub = jwt.encode(
        {
            "sub": "not-a-uuid",
            "type": "access",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(UnauthorizedError) as exc_sub:
        decode_access_token(bad_sub)
    assert exc_sub.value.code == "AUTH_TOKEN_INVALID"


def test_access_token_carries_sid_and_refresh_carries_jti() -> None:
    uid = uuid.uuid4()
    sid = uuid.uuid4()
    access_claims = decode_access_token(create_access_token(uid, session_id=sid))
    refresh_claims = decode_refresh_token(create_refresh_token(uid, token_id=sid))
    assert access_claims["sid"] == str(sid)
    assert refresh_claims["jti"] == str(sid)


async def test_login_unknown_email_executes_dummy_bcrypt_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def spy_verify(plain: str, hashed: str) -> bool:
        calls.append((plain, hashed))
        return False

    class _FakeUsers:
        async def get_by_email(self, email: str) -> User | None:
            return None

    class _FakeUoW:
        users = _FakeUsers()

    monkeypatch.setattr(auth_service, "verify_password", spy_verify)
    limiter = RateLimiter("login-test")
    with pytest.raises(UnauthorizedError) as exc:
        await auth_service.login(
            _FakeUoW(),  # type: ignore[arg-type]
            auth_service.LoginRequest(email="missing@wwf.org", password="Password1"),
            client_ip="127.0.0.1",
            limiter=limiter,
        )
    assert exc.value.code == "AUTH_INVALID_CREDENTIALS"
    assert calls == [("Password1", DUMMY_BCRYPT_HASH)]


def test_rate_limiter_prunes_expired_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now)
    limiter = rate_limit.SlidingWindowRateLimiter(window_seconds=60.0)

    assert limiter.check_and_record("ip:198.51.100.1", 10) is True
    assert "ip:198.51.100.1" in limiter._hits

    now = 160.0  # ventana expirada: la siguiente consulta purga la clave obsoleta
    assert limiter.check_and_record("ip:198.51.100.2", 10) is True
    assert "ip:198.51.100.1" not in limiter._hits
    assert "ip:198.51.100.2" in limiter._hits


# ---------------------------------------------------------------------------
# Health & Readiness (Nivel 1 & Nivel 2)
# ---------------------------------------------------------------------------


async def test_health_moved_to_api_v1_prefix() -> None:
    async with _client() as client:
        v1_resp = await client.get("/api/v1/health")
        root_resp = await client.get("/health")

    assert v1_resp.status_code == 200
    assert v1_resp.json()["data"] == {"status": "ok", "version": settings.APP_VERSION}
    assert root_resp.status_code == 404
    assert root_resp.json()["error"]["code"] == "ROUTE_NOT_FOUND"


class _OkSession:
    async def execute(self, stmt: Any) -> int:
        return 1


class _FailSession:
    async def execute(self, stmt: Any) -> None:
        raise RuntimeError("postgresql://secret:pw@host:5433/db")


class _StubUoW:
    def __init__(self, ok_db: bool = True) -> None:
        self.session = _OkSession() if ok_db else _FailSession()


async def test_health_ready_returns_200_and_sends_no_api_key_to_ai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_headers: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(dict(request.headers))
        assert request.url.path == "/api/v1/health"
        return httpx.Response(200, json={"status": "ok", "models_loaded": True})

    async def override_uow() -> AsyncIterator[_StubUoW]:
        yield _StubUoW(ok_db=True)

    async def override_http() -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            yield c

    monkeypatch.setattr(settings, "STORAGE_LOCAL_PATH", str(tmp_path / "evidence"))
    monkeypatch.setattr(settings, "AI_SERVICE_URL", "http://ia-test:8001")
    app.dependency_overrides[get_uow] = override_uow
    app.dependency_overrides[get_health_http_client] = override_http
    try:
        async with _client() as client:
            resp = await client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"] == {"database": "ok", "ai": "ok", "storage": "ok"}
    assert "x-api-key" not in {k.lower() for k in seen_headers[0]}


@pytest.mark.parametrize(
    ("ai_response", "ai_url"),
    [
        (httpx.Response(503, json={"status": "loading"}), "http://ia:8001"),
        (httpx.Response(503, json={"status": "models_missing"}), "http://ia:8001"),
        (httpx.Response(503, json={"status": "error"}), "http://ia:8001"),
        (httpx.Response(200, text="not-json"), "http://ia:8001"),
        (None, "http://ia:8001"),
        (httpx.Response(200, json={"status": "ok"}), ""),
    ],
)
async def test_health_ready_returns_503_when_ai_unhealthy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ai_response: httpx.Response | None,
    ai_url: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if ai_response is None:
            raise httpx.ConnectError("refused", request=request)
        return ai_response

    async def override_uow() -> AsyncIterator[_StubUoW]:
        yield _StubUoW(ok_db=True)

    async def override_http() -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            yield c

    monkeypatch.setattr(settings, "STORAGE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "AI_SERVICE_URL", ai_url)
    app.dependency_overrides[get_uow] = override_uow
    app.dependency_overrides[get_health_http_client] = override_http
    try:
        async with _client() as client:
            resp = await client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    body = resp.json()
    assert resp.status_code == 503
    assert body["status"] == "error"
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert body["data"] == {"database": "ok", "ai": "down", "storage": "ok"}


async def test_health_ready_returns_503_when_db_and_storage_fail_without_leaking_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    not_a_dir = tmp_path / "blocker"
    not_a_dir.write_bytes(b"x")

    async def override_uow() -> AsyncIterator[_StubUoW]:
        yield _StubUoW(ok_db=False)

    async def override_http() -> AsyncIterator[httpx.AsyncClient]:
        def ok_ai(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "ok"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(ok_ai)) as c:
            yield c

    monkeypatch.setattr(settings, "STORAGE_LOCAL_PATH", str(not_a_dir))
    monkeypatch.setattr(settings, "AI_SERVICE_URL", "http://ia:8001")
    app.dependency_overrides[get_uow] = override_uow
    app.dependency_overrides[get_health_http_client] = override_http
    try:
        async with _client() as client:
            resp = await client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503
    assert resp.json()["data"] == {"database": "down", "ai": "ok", "storage": "down"}
    assert "secret:pw" not in resp.text and str(not_a_dir) not in resp.text


# ---------------------------------------------------------------------------
# Integración Auth + Config contra PostgreSQL real (Nivel 1 & Nivel 2)
# ---------------------------------------------------------------------------


@requires_db
async def test_register_creates_user_hashed_refresh_token_and_ignores_anon_token(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        resp = await client.post(
            "/api/v1/auth/register",
            headers={"X-Anon-Token": "anon-token-ignored"},
            json={
                "email": "Ana@WWF.org.bo",
                "password": "Password1",
                "full_name": "  Ana Rojas ",
                "institution": " WWF Bolivia ",
            },
        )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["anon_session"] is None
    assert data["user"]["email"] == "ana@wwf.org.bo"
    assert data["user"]["full_name"] == "Ana Rojas"
    assert data["user"]["role"] == "user"
    assert data["tokens"]["expires_in"] == 1800

    refresh_raw = data["tokens"]["refresh_token"]
    access_claims = decode_access_token(data["tokens"]["access_token"])
    async with UnitOfWork(db_session_factory) as uow:
        stored = await uow.refresh_tokens.get_by_hash(hash_token(refresh_raw))
        assert stored is not None
        assert str(stored.id) == access_claims["sid"]
        assert stored.token_hash != refresh_raw


@requires_db
async def test_register_duplicate_email_case_insensitive_returns_409_cb72(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        first = await client.post(
            "/api/v1/auth/register",
            json={"email": "Ana@WWF.org", "password": "Password1", "full_name": "Ana"},
        )
        second = await client.post(
            "/api/v1/auth/register",
            json={"email": "ana@wwf.org", "password": "Password1", "full_name": "Ana 2"},
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "AUTH_EMAIL_TAKEN"


@requires_db
@pytest.mark.parametrize(
    "weak_password",
    ["Ab1", "abc1234", "abcdefgh", "12345678", "A1" * 37],
)
async def test_register_weak_password_returns_422(
    db_session_factory: async_sessionmaker[AsyncSession], weak_password: str
) -> None:
    async with _client() as client:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "weak@wwf.org", "password": weak_password, "full_name": "Ana"},
        )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "AUTH_WEAK_PASSWORD"


@requires_db
async def test_login_enumeration_protection_and_72_byte_password(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        await client.post(
            "/api/v1/auth/register",
            json={"email": "ana@wwf.org", "password": "Password1", "full_name": "Ana"},
        )
        unknown_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@wwf.org", "password": "Password1"},
        )
        wrong_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "ana@wwf.org", "password": "WrongPassword1"},
        )
        long_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "ana@wwf.org", "password": "x" * 100},
        )

    for r in (unknown_resp, wrong_resp, long_resp):
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
    assert unknown_resp.json()["message"] == wrong_resp.json()["message"]


@requires_db
async def test_login_updates_last_login_and_admin_receives_900s_ttl(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with UnitOfWork(db_session_factory) as uow:
        uow.users.add(
            User(
                email="admin@wwf.org",
                password_hash=get_password_hash("AdminPass1"),
                full_name="Admin WWF",
                role=UserRole.ADMIN,
                is_active=True,
            )
        )
        await uow.commit()

    async with _client() as client:
        resp = await client.post(
            "/api/v1/auth/login",
            headers={"X-Anon-Token": "anon-123"},
            json={"email": "ADMIN@wwf.org", "password": "AdminPass1"},
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["anon_session"] is None
    assert data["tokens"]["expires_in"] == 900
    assert data["user"]["last_login_at"] is not None
    claims = decode_access_token(data["tokens"]["access_token"])
    assert claims["exp"] - claims["iat"] == 900


@requires_db
async def test_login_rate_limit_ignores_spoofed_xff_and_limits_5_per_email(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with UnitOfWork(db_session_factory) as uow:
        uow.users.add(
            User(
                email="admin@wwf.org",
                password_hash=get_password_hash("AdminPass1"),
                full_name="Admin",
                role=UserRole.ADMIN,
            )
        )
        uow.users.add(
            User(
                email="normal@wwf.org",
                password_hash=get_password_hash("UserPass1"),
                full_name="User",
                role=UserRole.USER,
            )
        )
        await uow.commit()

    # 1) 10/min por IP real (ignorando X-Forwarded-For falso), usando correos distintos
    async with _client(ip="198.51.100.50") as client:
        for i in range(10):
            r = await client.post(
                "/api/v1/auth/login",
                headers={"X-Forwarded-For": f"203.0.113.{i}"},
                json={"email": f"user{i}@wwf.org", "password": "Wrong123"},
            )
            assert r.status_code == 401
        blocked = await client.post(
            "/api/v1/auth/login",
            headers={"X-Forwarded-For": "203.0.113.99"},
            json={"email": "user10@wwf.org", "password": "Wrong123"},
        )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"

    # Otra IP real no está bloqueada
    async with _client(ip="198.51.100.51") as other_client:
        ok_other = await other_client.post(
            "/api/v1/auth/login", json={"email": "other@wwf.org", "password": "Wrong123"}
        )
        assert ok_other.status_code == 401

    # 2) 5/min por email aplica igual para admin, usuario normal e inexistente (sin oráculo)
    for target_email, valid_pass, ip_base in (
        ("admin@wwf.org", "AdminPass1", 60),
        ("normal@wwf.org", "UserPass1", 70),
        ("ghost@wwf.org", "GhostPass1", 80),
    ):
        for idx in range(5):
            async with _client(ip=f"198.51.100.{ip_base + idx}") as c:
                r = await c.post(
                    "/api/v1/auth/login", json={"email": target_email, "password": "Wrong123"}
                )
                assert r.status_code == 401

        async with _client(ip=f"198.51.100.{ip_base + 5}") as c_sixth:
            r_sixth = await c_sixth.post(
                "/api/v1/auth/login", json={"email": target_email, "password": valid_pass}
            )
        assert r_sixth.status_code == 429
        assert r_sixth.json()["error"]["code"] == "RATE_LIMITED"
        assert blocked.json()["message"] == r_sixth.json()["message"]


@requires_db
async def test_refresh_rotation_and_cb78_reuse_revokes_all_user_tokens(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": "ana@wwf.org", "password": "Password1", "full_name": "Ana"},
        )
        r1 = reg.json()["data"]["tokens"]["refresh_token"]

        login2 = await client.post(
            "/api/v1/auth/login",
            json={"email": "ana@wwf.org", "password": "Password1"},
        )
        r_other = login2.json()["data"]["tokens"]["refresh_token"]

        rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": r1})
        assert rotated.status_code == 200
        r2 = rotated.json()["data"]["tokens"]["refresh_token"]
        assert r2 != r1

        # Reuso del refresh antiguo r1 -> 401 y revoca TODOS los tokens (incluidos r2 y r_other)
        reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": r1})
        assert reuse.status_code == 401
        assert reuse.json()["error"]["code"] == "AUTH_TOKEN_INVALID"

        after_r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": r2})
        after_other = await client.post("/api/v1/auth/refresh", json={"refresh_token": r_other})
        assert after_r2.status_code == 401
        assert after_other.status_code == 401

    async with UnitOfWork(db_session_factory) as uow:
        active_count = await uow.session.scalar(
            text("SELECT COUNT(*) FROM refresh_tokens WHERE revoked_at IS NULL")
        )
        assert active_count == 0


@requires_db
async def test_refresh_returns_401_expired_when_db_expires_at_elapsed(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": "dbexp@wwf.org", "password": "Password1", "full_name": "Ana"},
        )
        refresh_jwt = reg.json()["data"]["tokens"]["refresh_token"]

    async with UnitOfWork(db_session_factory) as uow:
        stored = await uow.refresh_tokens.get_by_hash(hash_token(refresh_jwt))
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await uow.commit()

    async with _client() as client:
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_jwt})

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_TOKEN_EXPIRED"


@requires_db
async def test_disabled_user_rejected_with_403_everywhere(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": "disabled@wwf.org", "password": "Password1", "full_name": "Ana"},
        )
        tokens = reg.json()["data"]["tokens"]
        user_id = uuid.UUID(reg.json()["data"]["user"]["id"])

    async with UnitOfWork(db_session_factory) as uow:
        user = await uow.users.get(user_id)
        assert user is not None
        user.is_active = False
        await uow.commit()

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    async with _client() as client:
        for method, path, body in (
            ("POST", "/api/v1/auth/login", {"email": "disabled@wwf.org", "password": "Password1"}),
            ("POST", "/api/v1/auth/refresh", {"refresh_token": tokens["refresh_token"]}),
            ("GET", "/api/v1/auth/me", None),
            ("PATCH", "/api/v1/auth/me", {"full_name": "X"}),
            ("POST", "/api/v1/auth/logout", {"refresh_token": tokens["refresh_token"]}),
        ):
            r = await client.request(method, path, headers=headers, json=body)
            assert r.status_code == 403
            assert r.json()["error"]["code"] == "ACCOUNT_DISABLED"


@requires_db
async def test_bearer_dependency_distinguishes_required_expired_and_invalid(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": "bearer@wwf.org", "password": "Password1", "full_name": "Ana"},
        )
    uid = reg.json()["data"]["user"]["id"]
    refresh_jwt = reg.json()["data"]["tokens"]["refresh_token"]
    expired_jwt = create_access_token(
        uid, session_id=uuid.uuid4(), expires_delta=timedelta(seconds=-5)
    )

    async with _client() as client:
        r_missing = await client.get("/api/v1/auth/me")
        r_basic = await client.get("/api/v1/auth/me", headers={"Authorization": "Basic abc"})
        r_exp = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_jwt}"}
        )
        r_wrong_type = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_jwt}"}
        )

    assert r_missing.status_code == 401 and r_missing.json()["error"]["code"] == "AUTH_REQUIRED"
    assert r_basic.status_code == 401 and r_basic.json()["error"]["code"] == "AUTH_REQUIRED"
    assert r_exp.status_code == 401 and r_exp.json()["error"]["code"] == "AUTH_TOKEN_EXPIRED"
    assert r_wrong_type.status_code == 401
    assert r_wrong_type.json()["error"]["code"] == "AUTH_TOKEN_INVALID"


@requires_db
async def test_logout_revokes_owned_token_and_rejects_foreign_token(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        a = (
            await client.post(
                "/api/v1/auth/register",
                json={"email": "a@wwf.org", "password": "Password1", "full_name": "A"},
            )
        ).json()["data"]["tokens"]
        b = (
            await client.post(
                "/api/v1/auth/register",
                json={"email": "b@wwf.org", "password": "Password1", "full_name": "B"},
            )
        ).json()["data"]["tokens"]

        foreign = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {a['access_token']}"},
            json={"refresh_token": b["refresh_token"]},
        )
        assert foreign.status_code == 401
        assert foreign.json()["error"]["code"] == "AUTH_TOKEN_INVALID"

        own = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {a['access_token']}"},
            json={"refresh_token": a["refresh_token"]},
        )
        assert own.status_code == 200
        assert own.json()["data"] is None

        # Token B sigue vivo; token A ya fue revocado
        b_refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": b["refresh_token"]}
        )
        a_refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": a["refresh_token"]}
        )
        assert b_refresh.status_code == 200
        assert a_refresh.status_code == 401


@requires_db
async def test_me_get_patch_and_password_change_keeps_current_session_only(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        s1 = (
            await client.post(
                "/api/v1/auth/register",
                json={"email": "me@wwf.org", "password": "Password1", "full_name": "Ana"},
            )
        ).json()["data"]["tokens"]
        s2 = (
            await client.post(
                "/api/v1/auth/login",
                json={"email": "me@wwf.org", "password": "Password1"},
            )
        ).json()["data"]["tokens"]
        s3 = (
            await client.post(
                "/api/v1/auth/login",
                json={"email": "me@wwf.org", "password": "Password1"},
            )
        ).json()["data"]["tokens"]

        me = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {s1['access_token']}"}
        )
        assert me.status_code == 200 and me.json()["data"]["email"] == "me@wwf.org"

        patched = await client.patch(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {s1['access_token']}"},
            json={"full_name": "Ana Rojas", "institution": "WWF Bolivia"},
        )
        assert patched.status_code == 200
        assert patched.json()["data"]["full_name"] == "Ana Rojas"
        assert patched.json()["data"]["institution"] == "WWF Bolivia"

        forbidden_fields = await client.patch(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {s1['access_token']}"},
            json={"role": "admin"},
        )
        assert forbidden_fields.status_code == 422

        wrong_pw = await client.post(
            "/api/v1/auth/me/password",
            headers={"Authorization": f"Bearer {s1['access_token']}"},
            json={"current_password": "WrongPassword1", "new_password": "NewPassword1"},
        )
        assert wrong_pw.status_code == 401
        assert wrong_pw.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"

        changed = await client.post(
            "/api/v1/auth/me/password",
            headers={"Authorization": f"Bearer {s1['access_token']}"},
            json={"current_password": "Password1", "new_password": "NewPassword1"},
        )
        assert changed.status_code == 200
        assert changed.json()["data"] is None

        # Sesiones 2 y 3 eliminadas en BD; sesión 1 (sid actual) sigue válida y puede rotarse
        # incluso si S2 intenta refrescar ANTES que S1 (regresión Bug 1) o después (S3).
        async with UnitOfWork(db_session_factory) as uow:
            t1 = await uow.refresh_tokens.get_by_hash(hash_token(s1["refresh_token"]))
            t2 = await uow.refresh_tokens.get_by_hash(hash_token(s2["refresh_token"]))
            t3 = await uow.refresh_tokens.get_by_hash(hash_token(s3["refresh_token"]))
            assert t1 is not None and t1.revoked_at is None
            assert t2 is None
            assert t3 is None

        s2_refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": s2["refresh_token"]}
        )
        assert s2_refresh.status_code == 401
        assert s2_refresh.json()["error"]["code"] == "AUTH_TOKEN_INVALID"

        s1_refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": s1["refresh_token"]}
        )
        assert s1_refresh.status_code == 200
        s1_rotated = s1_refresh.json()["data"]["tokens"]["refresh_token"]

        s3_refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": s3["refresh_token"]}
        )
        assert s3_refresh.status_code == 401
        assert s3_refresh.json()["error"]["code"] == "AUTH_TOKEN_INVALID"

        s1_rotated_refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": s1_rotated}
        )
        assert s1_rotated_refresh.status_code == 200


@requires_db
async def test_public_config_reads_formats_settings_and_db_retention(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client() as client:
        resp = await client.get("/api/v1/config/public")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["anon_data_retention"] is True
    assert data["password_recovery"] == {"enabled": False}
    assert data["media"]["max_file_mb"] == settings.MAX_FILE_MB == 300
    assert data["media"]["max_video_seconds"] == settings.MAX_VIDEO_SECONDS == 15
    assert data["media"]["image_extensions"] == sorted(e.lstrip(".") for e in IMAGE_EXTENSIONS)
    assert data["media"]["video_extensions"] == sorted(e.lstrip(".") for e in VIDEO_EXTENSIONS)
    assert "heic" not in data["media"]["image_extensions"]
    assert "mts" not in data["media"]["video_extensions"]
    assert data["anon_limits"] == {"max_files": 50, "max_camera_stations": 5}
    assert data["upload"] == {
        "max_parallel_files": 3,
        "max_pending_per_user": 500,
        "poll_interval_seconds": 3,
    }
    assert data["import"] == {"max_package_mb": 200, "supported_format_versions": ["1.0"]}
    assert data["map"] == {
        "default_center": {"lat": -17.7833, "lng": -63.1821},
        "default_zoom": 8,
        "label": "Santa Cruz, Bolivia",
    }
    assert data["app_version"] == settings.APP_VERSION
