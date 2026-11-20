"""SPIKE-01 · UT-2: ai_client habla el contrato real y traduce cada fallo (CA-1, CA-2, CA-4)."""

import json
import logging
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings, settings
from app.integrations import ai_client

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ai"
BASE_URL = "http://ia.test:8001"
API_KEY = "test-key-not-a-secret"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _error(code: str, context: dict | None = None) -> dict:
    return {
        "status": "error",
        "data": None,
        "message": "x",
        "error": {
            "code": code,
            "flow": "FL-08",
            "details": [{"code": code, "context": context or {}}],
        },
        "meta": {"request_id": "r1", "timestamp": "2026-11-20T00:00:00Z"},
    }


def _mock_client(responses: list, calls: list) -> httpx.AsyncClient:
    """Cliente httpx sin red: devuelve `responses` en orden y guarda cada petición en `calls`."""
    pending = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        request.read()
        calls.append(request)
        item = next(pending)
        if isinstance(item, Exception):
            raise item
        status, body = item
        if isinstance(body, bytes):
            return httpx.Response(status, content=body)
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def ai_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AI_SERVICE_URL", BASE_URL)
    monkeypatch.setattr(settings, "AI_API_KEY", API_KEY)


@pytest.fixture
def media(tmp_path: Path) -> Path:
    path = tmp_path / "CAM01_20260315_042210.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 64)
    return path


# --- CA-2: la petición que sale hacia la IA -------------------------------------------------


async def test_success_sends_contract_request_and_returns_detect_result(media: Path) -> None:
    calls: list = []
    async with _mock_client([(200, _fixture("animal_species_video"))], calls) as client:
        result = await ai_client.detect_media(media, request_id="req-123", client=client)

    assert result.result.category.value == "animal"
    assert result.analysis.low_evidence is False
    request = calls[0]
    assert str(request.url) == f"{BASE_URL}/api/v1/detect"
    assert request.headers["X-API-Key"] == API_KEY
    assert request.headers["X-Request-ID"] == "req-123"
    assert request.headers["X-Flow"] == "FL-08"
    assert b'name="file"; filename="CAM01_20260315_042210.mp4"' in request.content
    assert b'name="file_name"' in request.content


def test_settings_default_ai_timeout_is_180_seconds() -> None:
    assert Settings(_env_file=None).AI_TIMEOUT_SECONDS == 180.0


@pytest.mark.parametrize("missing", ["AI_SERVICE_URL", "AI_API_KEY"])
async def test_missing_config_fails_before_calling_ia(
    missing: str, media: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, missing, "")
    calls: list = []
    async with _mock_client([], calls) as client:
        with pytest.raises(ai_client.AiClientError) as exc:
            await ai_client.detect_media(media, client=client)

    assert exc.value.code == "AI_UNAVAILABLE"
    assert calls == []
    assert any(
        r.levelno == logging.CRITICAL and "config.invalid" in r.getMessage() for r in caplog.records
    )


# --- CA-4: traducción de cada error de la IA (Nivel 2, parametrizado) ------------------------

ERROR_CASES = [
    (400, "IA_INVALID_FORMAT", {"errors": ["file"]}, "AI_BAD_RESPONSE"),
    (401, "IA_UNAUTHORIZED", {}, "AI_UNAVAILABLE"),
    (413, "IA_FILE_TOO_LARGE", {"max_mb": 300.0, "size_mb": 301.2}, "MEDIA_TOO_LARGE"),
    (415, "IA_INVALID_FORMAT", {"reason": "extensión"}, "MEDIA_UNSUPPORTED_FORMAT"),
    (422, "IA_DECODE_FAILED", {"reason": "too_many_pixels"}, "MEDIA_TOO_LARGE"),
    (422, "IA_DECODE_FAILED", {"reason": "moov atom not found"}, "MEDIA_DECODE_FAILED"),
    (503, "IA_MODEL_NOT_READY", {}, "AI_NOT_READY"),
    (503, "IA_BUSY", {"queue_size": 2}, "AI_UNAVAILABLE"),
    (504, "IA_PROCESSING_TIMEOUT", {"elapsed_ms": 150000}, "AI_TIMEOUT"),
    (422, "IA_DURATION_EXCEEDED", {}, "AI_BAD_RESPONSE"),  # retirado por F1-D10: código desconocido
]


@pytest.mark.parametrize(("status", "ia_code", "context", "expected"), ERROR_CASES)
async def test_ia_error_is_translated_without_retry(
    status: int, ia_code: str, context: dict, expected: str, media: Path
) -> None:
    calls: list = []
    async with _mock_client([(status, _error(ia_code, context))], calls) as client:
        with pytest.raises(ai_client.AiClientError) as exc:
            await ai_client.detect_media(media, client=client)

    assert (exc.value.code, exc.value.ia_code, exc.value.http_status) == (expected, ia_code, status)
    assert len(calls) == 1


async def test_ia_internal_retries_once_then_succeeds(media: Path) -> None:
    calls: list = []
    responses = [(500, _error("IA_INTERNAL")), (200, _fixture("blank_image"))]
    async with _mock_client(responses, calls) as client:
        result = await ai_client.detect_media(media, client=client)

    assert result.result.category.value == "blank"
    assert len(calls) == 2


async def test_ia_internal_twice_is_bad_response(media: Path) -> None:
    calls: list = []
    responses = [(500, _error("IA_INTERNAL")), (500, _error("IA_INTERNAL"))]
    async with _mock_client(responses, calls) as client:
        with pytest.raises(ai_client.AiClientError) as exc:
            await ai_client.detect_media(media, client=client)

    assert exc.value.code == "AI_BAD_RESPONSE"
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("failure", "expected"),
    [(httpx.ConnectError("refused"), "AI_UNAVAILABLE"), (httpx.ReadTimeout("slow"), "AI_TIMEOUT")],
)
async def test_network_failure_is_translated(
    failure: Exception, expected: str, media: Path
) -> None:
    calls: list = []
    async with _mock_client([failure], calls) as client:
        with pytest.raises(ai_client.AiClientError) as exc:
            await ai_client.detect_media(media, client=client)

    assert exc.value.code == expected
    assert len(calls) == 1


# --- CA-1: nunca inventar datos ni filtrar secretos (Nivel 1, DD-4) --------------------------


async def test_out_of_contract_200_is_bad_response_and_logs_keys_without_base64(
    media: Path, caplog: pytest.LogCaptureFixture
) -> None:
    body = _fixture("animal_species_video")
    image_b64 = body["data"]["evidence"]["image_base64"]
    del body["data"]["result"]
    calls: list = []
    async with _mock_client([(200, body)], calls) as client:
        with pytest.raises(ai_client.AiClientError) as exc:
            await ai_client.detect_media(media, client=client)

    assert exc.value.code == "AI_BAD_RESPONSE"
    assert "media" in caplog.text and "evidence" in caplog.text
    assert image_b64[:40] not in caplog.text


async def test_non_json_200_is_bad_response(media: Path) -> None:
    calls: list = []
    async with _mock_client([(200, b"<html>proxy</html>")], calls) as client:
        with pytest.raises(ai_client.AiClientError) as exc:
            await ai_client.detect_media(media, client=client)

    assert exc.value.code == "AI_BAD_RESPONSE"


async def test_unauthorized_logs_critical_without_api_key(
    media: Path, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list = []
    async with _mock_client([(401, _fixture("error_unauthorized"))], calls) as client:
        with pytest.raises(ai_client.AiClientError):
            await ai_client.detect_media(media, client=client)

    assert any(
        r.levelno == logging.CRITICAL and "ai.unauthorized" in r.getMessage()
        for r in caplog.records
    )
    assert API_KEY not in caplog.text
    assert len(calls) == 1
