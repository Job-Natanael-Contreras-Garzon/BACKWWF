"""HU-04: recuperación de contraseña (FL-14): sin enumeración, de un solo uso y apagada."""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, settings
from app.core.enums import EmailStatus, EmailType
from app.core.logging import JsonFormatter
from app.core.security import hash_token
from app.db.uow import UnitOfWork
from app.integrations.email import ConsoleEmailProvider, ResendEmailProvider
from app.models.admin import EmailLog
from app.models.user import PasswordResetToken, RefreshToken, User
from app.repositories.users import UserRepository
from app.worker import send_email_job
from tests.conftest import make_client, register_user, requires_db

pytestmark = requires_db


class FakeProvider:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, *, to: str, subject: str, html: str, text: str) -> str:
        self.sent.append({"to": to, "subject": subject, "html": html, "text": text})
        return f"fake-{len(self.sent)}"


def _token_from(message: dict[str, str]) -> str:
    match = re.search(r"\?token=([A-Za-z0-9_\-]+)", message["text"])
    assert match is not None
    return match.group(1)


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture(autouse=True)
def _recovery_on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "PASSWORD_RECOVERY_ENABLED", True)
    monkeypatch.setattr(settings, "DEV_MAILBOX_PATH", str(tmp_path / "mailbox"))


@pytest.fixture
def provider(
    monkeypatch: pytest.MonkeyPatch, db_session_factory: async_sessionmaker[AsyncSession]
) -> FakeProvider:
    """Hace que el job de fondo use la BD de pruebas y un proveedor falso."""
    fake = FakeProvider()
    monkeypatch.setattr(send_email_job, "UnitOfWork", lambda: UnitOfWork(db_session_factory))
    monkeypatch.setattr(send_email_job, "get_email_provider", lambda: fake)
    return fake


def _uow(factory: async_sessionmaker[AsyncSession]) -> Callable[[], UnitOfWork]:
    return lambda: UnitOfWork(factory)


async def _deactivate(factory: async_sessionmaker[AsyncSession], email: str) -> None:
    async with factory() as s:
        await s.execute(update(User).where(User.email == email).values(is_active=False))
        await s.commit()


async def _counts(factory: async_sessionmaker[AsyncSession]) -> tuple[int, int]:
    async with factory() as s:
        tokens = len(list(await s.scalars(select(PasswordResetToken))))
        logs = len(list(await s.scalars(select(EmailLog))))
    return tokens, logs


async def test_forgot_is_indistinguishable_for_existing_unknown_and_inactive_cb73_cb77(
    db_session_factory: async_sessionmaker[AsyncSession], provider: FakeProvider
) -> None:
    async with make_client() as c:
        await register_user(c, "ana@wwf.org")
        await register_user(c, "off@wwf.org")
        await _deactivate(db_session_factory, "off@wwf.org")

        responses = []
        for email in ("ghost@wwf.org", "off@wwf.org"):
            responses.append(await c.post("/api/v1/auth/password/forgot", json={"email": email}))
        assert await _counts(db_session_factory) == (0, 0)  # ni token ni correo

        responses.append(
            await c.post("/api/v1/auth/password/forgot", json={"email": "Ana@WWF.org"})
        )

    shapes = {(r.status_code, r.json()["message"], json.dumps(r.json()["data"])) for r in responses}
    assert len(shapes) == 1
    assert shapes.pop()[0] == 200
    assert [m["to"] for m in provider.sent] == ["ana@wwf.org"]
    async with db_session_factory() as s:
        log = (await s.scalars(select(EmailLog))).one()
    assert log.status == EmailStatus.SENT
    assert log.to_hash == hash_token("ana@wwf.org")
    assert log.provider_id == "fake-1"


async def test_forgot_request_path_never_looks_up_the_user(
    db_session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(self: UserRepository, email: str) -> User | None:
        raise AssertionError("la petición no debe consultar usuarios")

    scheduled: list[tuple[str, str]] = []

    async def fake_job(email: str, client_ip: str) -> None:
        scheduled.append((email, client_ip))

    monkeypatch.setattr(UserRepository, "get_by_email", boom)
    monkeypatch.setattr(send_email_job, "send_password_reset_email", fake_job)
    async with make_client(ip="203.0.113.5") as c:
        resp = await c.post("/api/v1/auth/password/forgot", json={"email": "x@wwf.org"})
    assert resp.status_code == 200
    assert scheduled == [("x@wwf.org", "203.0.113.5")]


async def test_only_last_token_is_valid_and_validate_hints_masked_email_cb74(
    db_session_factory: async_sessionmaker[AsyncSession], provider: FakeProvider
) -> None:
    async with make_client() as c:
        await register_user(c, "ana@wwf.org")
        await c.post("/api/v1/auth/password/forgot", json={"email": "ana@wwf.org"})
        await c.post("/api/v1/auth/password/forgot", json={"email": "ana@wwf.org"})
        first, second = (_token_from(m) for m in provider.sent)

        old = await c.get("/api/v1/auth/password/reset/validate", params={"token": first})
        new = await c.get("/api/v1/auth/password/reset/validate", params={"token": second})

    assert old.status_code == 200 and old.json()["data"] == {
        "valid": False,
        "expires_at": None,
        "email_hint": None,
    }
    assert new.json()["data"]["valid"] is True
    assert new.json()["data"]["email_hint"] == "a***@wwf.org"


@pytest.mark.parametrize("case", ["unknown", "expired", "used"])
async def test_unusable_token_is_invalid_on_validate_and_reset_cb75(
    db_session_factory: async_sessionmaker[AsyncSession], provider: FakeProvider, case: str
) -> None:
    async with make_client() as c:
        await register_user(c, "ana@wwf.org")
        await c.post("/api/v1/auth/password/forgot", json={"email": "ana@wwf.org"})
        token = _token_from(provider.sent[0]) if case != "unknown" else "no-existe-123"
        async with db_session_factory() as s:
            if case == "expired":
                past = datetime.now(UTC) - timedelta(minutes=1)
                await s.execute(update(PasswordResetToken).values(expires_at=past))
            if case == "used":
                await s.execute(update(PasswordResetToken).values(used_at=datetime.now(UTC)))
            await s.commit()

        check = await c.get("/api/v1/auth/password/reset/validate", params={"token": token})
        reset = await c.post(
            "/api/v1/auth/password/reset", json={"token": token, "new_password": "NuevaClave9"}
        )
    assert check.json()["data"]["valid"] is False
    assert reset.status_code == 400
    assert reset.json()["error"]["code"] == "AUTH_RESET_TOKEN_INVALID"


async def test_reset_is_single_use_under_concurrency_and_revokes_all_refresh_cb78(
    db_session_factory: async_sessionmaker[AsyncSession], provider: FakeProvider
) -> None:
    async with make_client() as c:
        session = await register_user(c, "ana@wwf.org")
        old_refresh = session["tokens"]["refresh_token"]  # type: ignore[index]
        await c.post("/api/v1/auth/password/forgot", json={"email": "ana@wwf.org"})
        token = _token_from(provider.sent[0])

    async with make_client() as c1, make_client() as c2:
        body = {"token": token, "new_password": "NuevaClave9"}
        r1, r2 = await asyncio.gather(
            c1.post("/api/v1/auth/password/reset", json=body),
            c2.post("/api/v1/auth/password/reset", json=body),
        )
    assert sorted([r1.status_code, r2.status_code]) == [200, 400]
    done = r1 if r1.status_code == 200 else r2
    assert done.json()["data"] is None
    assert done.json()["message"] == "Contraseña actualizada; inicia sesión"

    async with make_client() as c:
        refresh = await c.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        old_login = await c.post(
            "/api/v1/auth/login", json={"email": "ana@wwf.org", "password": "Password1"}
        )
        new_login = await c.post(
            "/api/v1/auth/login", json={"email": "ana@wwf.org", "password": "NuevaClave9"}
        )
    assert refresh.status_code == 401 and refresh.json()["error"]["code"] == "AUTH_TOKEN_INVALID"
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    async with db_session_factory() as s:
        active = [t for t in await s.scalars(select(RefreshToken)) if t.revoked_at is None]
    assert len(active) == 1  # solo la sesión del login nuevo


async def test_weak_new_password_is_rejected_and_token_stays_usable(
    db_session_factory: async_sessionmaker[AsyncSession], provider: FakeProvider
) -> None:
    async with make_client() as c:
        await register_user(c, "ana@wwf.org")
        await c.post("/api/v1/auth/password/forgot", json={"email": "ana@wwf.org"})
        token = _token_from(provider.sent[0])
        weak = await c.post(
            "/api/v1/auth/password/reset", json={"token": token, "new_password": "corta"}
        )
        check = await c.get("/api/v1/auth/password/reset/validate", params={"token": token})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "AUTH_WEAK_PASSWORD"
    assert check.json()["data"]["valid"] is True


async def test_global_daily_cap_returns_503_for_everyone_cb76(
    db_session_factory: async_sessionmaker[AsyncSession],
    provider: FakeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMAIL_DAILY_CAP", 2)
    async with db_session_factory() as s:
        for status in (EmailStatus.SENT, EmailStatus.QUEUED, EmailStatus.FAILED):
            s.add(EmailLog(type=EmailType.PASSWORD_RESET, to_hash="h" * 64, status=status))
        await s.commit()
    async with make_client() as c:
        await register_user(c, "ana@wwf.org")
        known = await c.post("/api/v1/auth/password/forgot", json={"email": "ana@wwf.org"})
        unknown = await c.post("/api/v1/auth/password/forgot", json={"email": "no@wwf.org"})
    for resp in (known, unknown):
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "EMAIL_TEMPORARILY_UNAVAILABLE"
    assert provider.sent == []


async def test_ip_limit_is_silent_and_abuse_threshold_returns_429(
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PASSWORD_FORGOT_IP_PER_HOUR", 2)
    monkeypatch.setattr(settings, "PASSWORD_FORGOT_IP_ABUSE_PER_HOUR", 4)
    scheduled: list[str] = []

    async def fake_job(email: str, client_ip: str) -> None:
        scheduled.append(email)

    monkeypatch.setattr(send_email_job, "send_password_reset_email", fake_job)
    async with make_client(ip="203.0.113.9") as c:
        statuses = [
            (await c.post("/api/v1/auth/password/forgot", json={"email": f"u{i}@wwf.org"}))
            for i in range(5)
        ]
    assert [r.status_code for r in statuses] == [200, 200, 200, 200, 429]
    assert statuses[4].json()["error"]["code"] == "RATE_LIMITED"
    assert scheduled == ["u0@wwf.org", "u1@wwf.org"]  # el 3.º y el 4.º, silenciosos


async def test_per_email_limits_skip_sending_and_are_logged(
    db_session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with make_client() as c:
        await register_user(c, "ana@wwf.org")
    fake = FakeProvider()
    statuses = [
        await send_email_job.send_password_reset_email(
            "ana@wwf.org", "203.0.113.1", uow_factory=_uow(db_session_factory), provider=fake
        )
        for _ in range(4)
    ]
    assert statuses == [EmailStatus.SENT] * 3 + [EmailStatus.SKIPPED_LIMIT]
    assert len(fake.sent) == 3
    async with db_session_factory() as s:
        token = (await s.scalars(select(PasswordResetToken))).first()
    assert token is not None and token.request_ip_hash is not None
    assert "203.0.113.1" not in token.request_ip_hash and len(token.request_ip_hash) == 64


async def test_logs_never_contain_token_link_or_email(
    db_session_factory: async_sessionmaker[AsyncSession],
    provider: FakeProvider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with make_client() as c:
        await register_user(c, "secret.person@wwf.org")
        await c.post("/api/v1/auth/password/forgot", json={"email": "secret.person@wwf.org"})
        token = _token_from(provider.sent[0])
        await c.get("/api/v1/auth/password/reset/validate", params={"token": token})
        await c.post(
            "/api/v1/auth/password/reset", json={"token": token, "new_password": "NuevaClave9"}
        )
    formatter = JsonFormatter()
    # "httpx" es el cliente de pruebas registrando la URL que él mismo pide, no la app.
    output = "\n".join(formatter.format(r) for r in caplog.records if r.name != "httpx")
    assert "auth.password.reset.succeeded" in output
    leaks = [line for line in output.splitlines() if token in line]
    assert not leaks, leaks
    assert "restablecer?token" not in output
    assert "secret.person@wwf.org" not in output


def _resend_transport(statuses: list[int], seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        code = statuses.pop(0)
        return httpx.Response(code, json={"id": "re_123"} if code == 200 else {"error": "x"})

    return httpx.MockTransport(handler)


async def test_resend_provider_sends_expected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(settings, "EMAIL_FROM", "WWF <no-reply@wwf.test>")
    seen: list[httpx.Request] = []
    provider = ResendEmailProvider(transport=_resend_transport([200], seen))
    provider_id = await provider.send(to="ana@wwf.org", subject="S", html="<p>h</p>", text="t")
    assert provider_id == "re_123"
    request = seen[0]
    assert str(request.url) == settings.RESEND_API_URL
    assert request.headers["Authorization"] == "Bearer re_test_key"
    assert json.loads(request.content) == {
        "from": "WWF <no-reply@wwf.test>",
        "to": ["ana@wwf.org"],
        "subject": "S",
        "html": "<p>h</p>",
        "text": "t",
    }


@pytest.mark.parametrize(
    ("statuses", "expected", "calls"),
    [
        ([503, 429, 200], EmailStatus.SENT, 3),
        ([503, 503, 503], EmailStatus.FAILED, 3),
        ([400], EmailStatus.FAILED, 1),
    ],
)
async def test_job_retries_twice_on_429_and_5xx_only(
    db_session_factory: async_sessionmaker[AsyncSession],
    statuses: list[int],
    expected: EmailStatus,
    calls: int,
) -> None:
    async with make_client() as c:
        await register_user(c, "ana@wwf.org")
    seen: list[httpx.Request] = []
    result = await send_email_job.send_password_reset_email(
        "ana@wwf.org",
        "203.0.113.1",
        uow_factory=_uow(db_session_factory),
        provider=ResendEmailProvider(transport=_resend_transport(list(statuses), seen)),
        sleep=_no_sleep,
    )
    assert result == expected
    assert len(seen) == calls
    async with db_session_factory() as s:
        log = (await s.scalars(select(EmailLog))).one()
    assert log.status == expected


async def test_console_provider_writes_mailbox_file(tmp_path: Path) -> None:
    mailbox = tmp_path / "box"
    provider_id = await ConsoleEmailProvider(str(mailbox)).send(
        to="ana@wwf.org", subject="Asunto", html="<p>x</p>", text="enlace: https://f/r?token=abc"
    )
    files = list(mailbox.iterdir())
    assert provider_id.startswith("console-") and len(files) == 1
    assert "token=abc" in files[0].read_text(encoding="utf-8")


async def test_disabled_recovery_blocks_sending_only_and_public_config_reports_it(
    db_session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "PASSWORD_RECOVERY_ENABLED", False)
    async with make_client() as c:
        responses = [
            await c.post("/api/v1/auth/password/forgot", json={"email": "a@wwf.org"}),
            await c.get("/api/v1/auth/password/reset/validate", params={"token": "x"}),
            await c.post(
                "/api/v1/auth/password/reset", json={"token": "x", "new_password": "Clave1234"}
            ),
        ]
        config = await c.get("/api/v1/config/public")
    # Solo el envío se apaga; validar/usar un enlace sigue (enlace del admin, CB-76/HU-15a).
    forgot, validate, reset = responses
    assert forgot.status_code == 503
    assert forgot.json()["error"]["code"] == "EMAIL_TEMPORARILY_UNAVAILABLE"
    assert validate.status_code == 200 and validate.json()["data"]["valid"] is False
    assert reset.status_code == 400
    assert reset.json()["error"]["code"] == "AUTH_RESET_TOKEN_INVALID"
    assert config.json()["data"]["password_recovery"] == {"enabled": False}


_PROD: dict[str, Any] = {
    "ENVIRONMENT": "production",
    "DATABASE_URL": "postgresql+asyncpg://u:p@db.example.com/fauna",
    "SECRET_KEY": "a" * 40,
    "REFRESH_SECRET_KEY": "b" * 40,
    "PASSWORD_RECOVERY_ENABLED": True,
}


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        ({"EMAIL_PROVIDER": "console"}, "EMAIL_PROVIDER"),
        (
            {"EMAIL_PROVIDER": "resend", "EMAIL_FROM": "x@y", "FRONTEND_BASE_URL": "https://f"},
            "RESEND_API_KEY",
        ),
        (
            {"EMAIL_PROVIDER": "resend", "RESEND_API_KEY": "k", "FRONTEND_BASE_URL": "https://f"},
            "EMAIL_FROM",
        ),
        (
            {
                "EMAIL_PROVIDER": "resend",
                "RESEND_API_KEY": "k",
                "EMAIL_FROM": "x@y",
                "FRONTEND_BASE_URL": "http://f",
            },
            "FRONTEND_BASE_URL",
        ),
    ],
)
def test_production_settings_require_email_config_when_enabled(
    overrides: dict[str, Any], expected_error: str
) -> None:
    with pytest.raises(ValueError, match=expected_error):
        Settings(_env_file=None, **{**_PROD, **overrides})  # type: ignore[call-arg]


def test_production_settings_accept_complete_email_config() -> None:
    ok = Settings(
        _env_file=None,  # type: ignore[call-arg]
        **{
            **_PROD,
            "EMAIL_PROVIDER": "resend",
            "RESEND_API_KEY": "re_live",
            "EMAIL_FROM": "WWF <no-reply@wwf.org>",
            "FRONTEND_BASE_URL": "https://fauna.wwf.org",
        },
    )
    assert ok.PASSWORD_RECOVERY_ENABLED is True
