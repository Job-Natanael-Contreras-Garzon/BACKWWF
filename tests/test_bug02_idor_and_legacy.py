import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/users/"),
        ("POST", "/api/v1/videos/"),
        ("DELETE", "/api/v1/videos/1"),
        ("POST", "/api/v1/species/1/verify"),
        ("DELETE", "/api/v1/species/1"),
        ("GET", "/api/v1/individuals/"),
        ("GET", "/api/v1/reports/"),
        ("POST", "/api/v1/ai/process-video/1"),
    ],
)
def test_legacy_routes_removed_and_idor_blocked(method: str, path: str) -> None:
    """BUG-02 (Nivel 1): Los routers legacy sin autenticación deben estar desmontados (404)."""
    client = TestClient(app)
    response = client.request(method, path)
    assert response.status_code == 404, (
        f"La ruta legacy {method} {path} sigue expuesta (status={response.status_code})"
    )
