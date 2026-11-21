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


def test_app_does_not_use_blocking_copyfileobj() -> None:
    """BUG-03: nada en app/ copia archivos con shutil.copyfileobj síncrono (bloquea el event loop).

    media_service.py, donde estaba el bug, se retiró en HU-02; la ingesta se rehace en HU-08.
    """
    for path in (ROOT_DIR / "app").rglob("*.py"):
        assert "copyfileobj" not in path.read_text(encoding="utf-8"), path
