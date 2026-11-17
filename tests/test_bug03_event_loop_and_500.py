from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_500_handler_hides_internal_exception_details() -> None:
    """BUG-03 (Nivel 1): El handler 500 no debe exponer str(exc) ni detalles internos."""
    secret_marker = "INTERNAL_DB_PATH_LEAK_XYZ"

    @app.get("/_test/boom-500")
    async def _boom() -> None:
        raise RuntimeError(secret_marker)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/_test/boom-500")

    assert response.status_code == 500
    assert secret_marker not in response.text


def test_media_service_does_not_use_blocking_copyfileobj() -> None:
    """BUG-03: media_service.py no debe usar shutil.copyfileobj síncrono en async def."""
    content = (ROOT_DIR / "app" / "services" / "media_service.py").read_text(encoding="utf-8")
    assert "copyfileobj" not in content
