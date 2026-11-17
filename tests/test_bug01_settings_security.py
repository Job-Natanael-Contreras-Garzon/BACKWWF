import logging
import pytest
from pydantic import ValidationError
from app.core.config import Settings
from app.core.enums import EnvironmentMode
VALID_PROD_SECRET = "a" * 32
VALID_PROD_REFRESH = "b" * 32
VALID_PROD_DB = "postgresql+asyncpg://user:strongpass@db.example.com:25060/faunadb?ssl=require"
@pytest.mark.parametrize(
    "overrides",
    [
        {"SECRET_KEY": "short-key", "REFRESH_SECRET_KEY": VALID_PROD_REFRESH},
        {"SECRET_KEY": VALID_PROD_SECRET, "REFRESH_SECRET_KEY": "short-key"},
        {"SECRET_KEY": VALID_PROD_SECRET, "REFRESH_SECRET_KEY": VALID_PROD_SECRET},
        {
            "SECRET_KEY": "super-secret-key-access-change-me-wwf-2026",
            "REFRESH_SECRET_KEY": VALID_PROD_REFRESH,
        },
        {"DATABASE_URL": "", "SECRET_KEY": VALID_PROD_SECRET, "REFRESH_SECRET_KEY": VALID_PROD_REFRESH},
    ],
    ids=[
        "weak_secret_key_under_32_bytes",
        "weak_refresh_key_under_32_bytes",
        "identical_access_and_refresh_keys",
        "placeholder_default_secret_key",
        "missing_database_url",
    ],
)
def test_settings_rejects_weak_jwt_secrets_in_production(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    overrides: dict[str, str],
) -> None:
    """CA-1: En producción, Settings debe abortar con CRITICAL config.invalid ante secretos débiles o faltantes."""
    for var in ("ENVIRONMENT", "DATABASE_URL", "SECRET_KEY", "REFRESH_SECRET_KEY", "ALLOWED_ORIGINS"):
        monkeypatch.delenv(var, raising=False)
    params = {
        "ENVIRONMENT": EnvironmentMode.PRODUCTION,
        "DATABASE_URL": VALID_PROD_DB,
        "SECRET_KEY": VALID_PROD_SECRET,
        "REFRESH_SECRET_KEY": VALID_PROD_REFRESH,
        "ALLOWED_ORIGINS": "https://app.wwf.org",
        **overrides,
    }
    with caplog.at_level(logging.CRITICAL):
        with pytest.raises((ValidationError, ValueError)):