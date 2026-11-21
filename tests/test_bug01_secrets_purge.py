import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
LITERAL_DSN_PATTERN = re.compile(r"postgresql(?:\+asyncpg)?://[^${}\s\"']+:[^${}\s\"']+@")


def test_digitalocean_yaml_has_no_literal_db_credentials() -> None:
    """UT-2 (Nivel 1): digitalocean.yaml no debe contener credenciales literales y debe usar ${DATABASE_URL}."""
    content = (ROOT_DIR / "digitalocean.yaml").read_text(encoding="utf-8")

    assert not LITERAL_DSN_PATTERN.search(content), "Se encontró un DSN con credenciales literales en digitalocean.yaml"
    assert "aivencloud.com" not in content, "Se encontró host literal de Aiven en digitalocean.yaml"
    assert "${DATABASE_URL}" in content, "DATABASE_URL debe referenciarse como ${DATABASE_URL}"


def test_check_db_reads_settings_and_has_no_hardcoded_dsn() -> None:
    """UT-2 (Nivel 1): check_db.py debe leer settings.DATABASE_URL sin DSN hardcodeado."""
    content = (ROOT_DIR / "check_db.py").read_text(encoding="utf-8")

    assert not LITERAL_DSN_PATTERN.search(content), "Se encontró un DSN con credenciales literales en check_db.py"
    assert "aivencloud.com" not in content, "Se encontró host literal de Aiven en check_db.py"
    assert "app.core.config" in content and "settings.DATABASE_URL" in content
