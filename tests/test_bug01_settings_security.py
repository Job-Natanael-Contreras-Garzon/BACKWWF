"""BUG-01 (Nivel 1): Settings separa development y production y aborta ante secretos débiles."""

import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.enums import EnvironmentMode

VALID_PROD_SECRET = "a" * 32
VALID_PROD_REFRESH = "b" * 32
VALID_PROD_DB = "postgresql+asyncpg://user:strongpass@db.example.com:25060/faunadb?ssl=require"
LOCAL_ORIGINS = {"http://localhost:5173", "http://localhost:3000"}
SETTINGS_ENV_VARS = (
    "ENVIRONMENT",
    "DATABASE_URL",
    "SECRET_KEY",
    "REFRESH_SECRET_KEY",
    "ALLOWED_ORIGINS",
    "PASSWORD_RECOVERY_ENABLED",
    "EMAIL_PROVIDER",
    "RESEND_API_KEY",
    "EMAIL_FROM",
    "FRONTEND_BASE_URL",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Las variables del entorno del desarrollador no deben decidir el resultado del test."""
    for var in SETTINGS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _production(**overrides: str) -> Settings:
    params: dict[str, object] = {
        "ENVIRONMENT": EnvironmentMode.PRODUCTION,
        "DATABASE_URL": VALID_PROD_DB,
        "SECRET_KEY": VALID_PROD_SECRET,
        "REFRESH_SECRET_KEY": VALID_PROD_REFRESH,
        "ALLOWED_ORIGINS": "https://app.wwf.org",
        **overrides,
    }
    return Settings(_env_file=None, **params)  # type: ignore[call-arg, arg-type]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"SECRET_KEY": "short-key"}, "SECRET_KEY < 32 bytes"),
        ({"REFRESH_SECRET_KEY": "short-key"}, "REFRESH_SECRET_KEY < 32 bytes"),
        ({"REFRESH_SECRET_KEY": VALID_PROD_SECRET}, "deben ser distintas"),
        (
            {"SECRET_KEY": "super-secret-key-access-change-me-wwf-2026"},
            "SECRET_KEY contiene placeholder",
        ),
        ({"DATABASE_URL": ""}, "DATABASE_URL"),
        ({"DATABASE_URL": "postgresql+asyncpg://user:password@host:5432/db"}, "DATABASE_URL"),
    ],
    ids=[
        "weak_secret_key_under_32_bytes",
        "weak_refresh_key_under_32_bytes",
        "identical_access_and_refresh_keys",
        "placeholder_secret_key",
        "missing_database_url",
        "placeholder_database_url",
    ],
)
def test_production_aborts_with_critical_on_weak_config(
    caplog: pytest.LogCaptureFixture, overrides: dict[str, str], reason: str
) -> None:
    """CA-1: en producción, una config débil impide arrancar y deja CRITICAL config.invalid."""
    with caplog.at_level(logging.CRITICAL), pytest.raises(ValidationError, match=reason):
        _production(**overrides)

    critical = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert critical, "debe registrarse un log CRITICAL"
    assert "config.invalid" in critical[0].getMessage()
    assert "short-key" not in caplog.text, "el valor del secreto no debe aparecer en el log"


def test_valid_production_starts_without_local_cors_origins() -> None:
    """CA-1: producción válida arranca y nunca abre CORS a localhost."""
    settings = _production()

    assert settings.cors_origins == ["https://app.wwf.org"]
    assert not LOCAL_ORIGINS & set(settings.cors_origins)


def test_development_starts_with_local_config_and_local_cors() -> None:
    """CA-2: development arranca con credenciales locales y habilita los orígenes locales."""
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        ENVIRONMENT=EnvironmentMode.DEVELOPMENT,
        DATABASE_URL="postgresql+asyncpg://dev:dev@host.docker.internal:5433/faunadb",
        AI_SERVICE_URL="http://host.docker.internal:8001",
        SECRET_KEY="dev-only",
        REFRESH_SECRET_KEY="dev-only-refresh",
    )

    assert settings.ENVIRONMENT is EnvironmentMode.DEVELOPMENT
    assert set(settings.cors_origins) >= LOCAL_ORIGINS
