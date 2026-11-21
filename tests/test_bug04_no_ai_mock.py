"""BUG-04 (Nivel 1, DD-4): ningún fallo de la IA se convierte en un resultado inventado."""

import logging
from pathlib import Path

import httpx
import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.integrations import ai_client

ROOT = Path(__file__).resolve().parents[1]


def test_ai_failure_never_returns_mock_jaguar() -> None:
    """El servicio legado (timeout=2.0 y Panthera onca al 94,5 %) ya no existe en app/."""
    assert not (ROOT / "app" / "services" / "ai_service.py").exists()
    for path in (ROOT / "app").rglob("*.py"):
        if "ia_contract" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        assert "analyze_media_with_ai" not in source, path
        assert "0.945" not in source, path
        assert "timeout=2.0" not in source, path


@pytest.mark.parametrize(
    ("failure", "code", "http_status", "level"),
    [
        (httpx.ConnectError("refused"), "AI_UNAVAILABLE", 502, logging.ERROR),
        (httpx.ReadTimeout("slow"), "AI_TIMEOUT", 504, logging.ERROR),
    ],
)
async def test_ai_failure_is_an_app_error_for_the_global_handler(
    failure: Exception,
    code: str,
    http_status: int,
    level: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AI_SERVICE_URL", "http://ia.test:8001")
    monkeypatch.setattr(settings, "AI_API_KEY", "test-key")
    media = tmp_path / "CAM01.mp4"
    media.write_bytes(b"demo")

    def handler(request: httpx.Request) -> httpx.Response:
        raise failure

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AppError) as exc:
            await ai_client.detect_media(media, client=client)

    assert (exc.value.code, exc.value.http_status, exc.value.log_level) == (
        code,
        http_status,
        level,
    )
    assert exc.value.message and "httpx" not in exc.value.message
