"""HU-01: envoltura ApiResponse, AppError, logs JSON con contexto y LocalStorage (CA-1..CA-3)."""

import json
import logging
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.errors import AppError, NotFoundError
from app.core.logging import JsonFormatter, flow, flow_var, log_step, request_id_var, step_var
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.integrations.storage.base import StorageBackend
from app.integrations.storage.local import LocalStorage
from app.main import app, register_exception_handlers

ENVELOPE_KEYS = {"status", "data", "message", "error", "meta"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def probe_client() -> TestClient:
    """App mínima con el mismo cableado que main.py y rutas que fallan a propósito."""
    probe = FastAPI()
    register_exception_handlers(probe)
    probe.add_middleware(SecurityHeadersMiddleware)
    probe.add_middleware(RequestContextMiddleware)

    @probe.get("/boom", dependencies=[Depends(flow("FL-08"))])
    async def boom() -> None:
        raise RuntimeError("password=hunter2 at /srv/app/secret.py line 42")

    @probe.get("/camera", dependencies=[Depends(flow("FL-05"))])
    async def camera() -> None:
        raise NotFoundError("CAMERA_NOT_FOUND", "La cámara no existe.", context={"camera_id": "c1"})

    return TestClient(probe, raise_server_exceptions=False)


# --- CA-1 (Nivel 1): errores internos sin fuga y logs JSON enmascarados ----------------------


def test_unexpected_exception_returns_generic_500_with_request_id(
    probe_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    response = probe_client.get("/boom", headers={"X-Request-ID": "req-boom-1"})

    body = response.json()
    assert response.status_code == 500
    assert set(body) == ENVELOPE_KEYS
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["meta"]["request_id"] == "req-boom-1"
    assert response.headers["X-Request-ID"] == "req-boom-1"
    assert "hunter2" not in response.text and "secret.py" not in response.text
    assert any(r.levelno == logging.ERROR and r.exc_info for r in caplog.records)


def test_json_formatter_emits_one_line_with_context_and_masks_sensitive_data() -> None:
    tokens = [request_id_var.set("req-log-1"), flow_var.set("FL-01"), step_var.set("auth.login")]
    try:
        record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "login", None, None)
        record.__dict__.update(
            {
                "event": "auth.login.failed",
                "email": "diego@gmail.com",
                "authorization": "Bearer eyJhbGciOi",
                "x_anon_token": "anon-secret",
                "password": "hunter2",
            }
        )
        line = JsonFormatter().format(record)
    finally:
        for var, token in zip((request_id_var, flow_var, step_var), tokens, strict=True):
            var.reset(token)

    assert "\n" not in line
    entry = json.loads(line)
    required = {"ts", "level", "service", "env", "version", "request_id", "event", "message"}
    assert required <= set(entry)
    assert (entry["request_id"], entry["flow"], entry["step"]) == (
        "req-log-1",
        "FL-01",
        "auth.login",
    )
    assert entry["email"] == "d***@gmail.com"
    assert "eyJhbGciOi" not in line and "anon-secret" not in line and "hunter2" not in line


# --- CA-2: envoltura estándar y correlación --------------------------------------------------


def test_success_uses_api_response_and_echoes_request_id(client: TestClient) -> None:
    response = client.get("/", headers={"X-Request-ID": "front-abc-123"})

    body = response.json()
    assert response.status_code == 200
    assert set(body) == ENVELOPE_KEYS
    assert body["status"] == "success" and body["error"] is None
    assert body["meta"]["request_id"] == "front-abc-123"
    assert body["meta"]["timestamp"].endswith("Z")
    assert response.headers["X-Request-ID"] == "front-abc-123"


@pytest.mark.parametrize("bad_id", ["x" * 65, "id con espacios", "<script>alert(1)</script>"])
def test_untrusted_request_id_is_replaced(client: TestClient, bad_id: str) -> None:
    response = client.get("/", headers={"X-Request-ID": bad_id})

    generated = response.headers["X-Request-ID"]
    assert generated != bad_id
    assert response.json()["meta"]["request_id"] == generated


def test_health_is_liveness_without_internal_details(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


def test_routes_live_under_api_v1_prefix(client: TestClient) -> None:
    legacy = client.post("/auth/login", json={})
    current = client.post("/api/v1/auth/login", json={})

    assert legacy.status_code == 404 and legacy.json()["error"]["code"] == "ROUTE_NOT_FOUND"
    assert current.status_code == 422


def test_validation_error_lists_fields_without_echoing_input(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": "no-es-correo", "password": 12345678901234}
    )

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"] and all(d.get("field") for d in body["error"]["details"])
    assert "no-es-correo" not in response.text and "12345678901234" not in response.text


def test_app_error_uses_its_code_status_and_flow(probe_client: TestClient) -> None:
    response = probe_client.get("/camera")

    body = response.json()
    assert response.status_code == 404
    assert body["error"] == {"code": "CAMERA_NOT_FOUND", "flow": "FL-05", "details": []}
    assert body["message"] == "La cámara no existe."
    assert "camera_id" not in response.text  # el context va al log, no a la respuesta


def test_security_headers_are_present(client: TestClient) -> None:
    headers = client.get("/").headers

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_log_step_logs_success_and_failure_with_duration(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO), log_step("storage.put"):
        pass
    with caplog.at_level(logging.INFO), pytest.raises(NotFoundError), log_step("ai.call"):
        raise NotFoundError("CLASSIFICATION_NOT_FOUND")

    events = {getattr(r, "event", ""): r for r in caplog.records}
    assert "duration_ms" in events["storage.put.succeeded"].__dict__
    failed = events["ai.call.failed"]
    assert failed.__dict__["error_code"] == "CLASSIFICATION_NOT_FOUND"
    assert failed.levelno == logging.INFO  # NotFoundError es un error esperado


# --- CA-3: LocalStorage detrás de StorageBackend ---------------------------------------------


async def test_local_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    key = "evidence/2026/11/abc.jpg"

    assert isinstance(storage, StorageBackend)
    assert await storage.exists(key) is False
    await storage.put(key, b"\xff\xd8jpeg", "image/jpeg")
    assert await storage.exists(key) is True
    assert await storage.get(key) == b"\xff\xd8jpeg"
    await storage.delete(key)
    await storage.delete(key)  # idempotente
    assert await storage.exists(key) is False


@pytest.mark.parametrize("bad_key", ["../escape.jpg", "/etc/passwd", "evidence/../../x.jpg", ""])
async def test_local_storage_rejects_keys_outside_base(tmp_path: Path, bad_key: str) -> None:
    with pytest.raises(ValueError):
        await LocalStorage(tmp_path).put(bad_key, b"x", "image/jpeg")


async def test_local_storage_disk_failure_raises_storage_write_failed(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_bytes(b"")

    with pytest.raises(AppError) as exc:
        await LocalStorage(blocker).put("evidence/a.jpg", b"x", "image/jpeg")

    assert exc.value.code == "STORAGE_WRITE_FAILED"
    assert exc.value.http_status == 500


async def test_local_storage_get_missing_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await LocalStorage(tmp_path).get("evidence/none.jpg")
