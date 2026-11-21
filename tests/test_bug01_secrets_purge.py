import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
LITERAL_DSN_PATTERN = re.compile(r"postgresql(?:\+asyncpg)?://[^${}\s\"']+:[^${}\s\"']+@")


def test_compose_and_manifests_have_no_literal_db_credentials() -> None:
    """UT-2 (Nivel 1): ningún manifiesto YAML del repo trae credenciales literales.

    Los manifiestos de despliegue (DigitalOcean, Koyeb) se retiraron: el cliente elige dónde
    desplegar al final del proyecto. Queda docker-compose.yml para desarrollo.
    """
    manifests = sorted([*ROOT_DIR.glob("*.yml"), *ROOT_DIR.glob("*.yaml")])
    assert manifests, "Debe existir al menos docker-compose.yml"
    for path in manifests:
        content = path.read_text(encoding="utf-8")
        assert not LITERAL_DSN_PATTERN.search(content), f"DSN con credenciales en {path.name}"
        assert "aivencloud.com" not in content, f"Host literal de Aiven en {path.name}"


def test_check_db_reads_settings_and_has_no_hardcoded_dsn() -> None:
    """UT-2 (Nivel 1): check_db.py debe leer settings.DATABASE_URL sin DSN hardcodeado."""
    content = (ROOT_DIR / "check_db.py").read_text(encoding="utf-8")

    assert not LITERAL_DSN_PATTERN.search(content), "Se encontró un DSN con credenciales literales en check_db.py"
    assert "aivencloud.com" not in content, "Se encontró host literal de Aiven en check_db.py"
    assert "app.core.config" in content and "settings.DATABASE_URL" in content
