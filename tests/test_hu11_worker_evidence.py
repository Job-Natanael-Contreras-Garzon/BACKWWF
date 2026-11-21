"""HU-11: worker de clasificación (FL-08) y fotograma de evidencia (#27)."""

import base64
import copy
import io
import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_storage
from app.core.config import settings
from app.core.enums import BatchStatus, ClassificationStatus
from app.integrations.storage.local import LocalStorage
from app.main import app
from app.worker import classify_file_job as job
from tests.conftest import FakeQueue, bearer, make_client, register_user, requires_db
from tests.test_hu08_batches import _batch, _camera, _jpeg, _tmp_files, _upload
from tests.test_hu09_batch_tracking import _row, _set, _uow

pytestmark = requires_db
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ai"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _big_frame() -> str:
    """Fotograma de 2000x1500 con EXIF: el worker debe achicarlo a 960 px y quitar el EXIF."""
    exif = Image.Exif()
    exif[0x010F] = "CamaraSecreta"
    buf = io.BytesIO()
    Image.new("RGB", (2000, 1500), (10, 120, 30)).save(buf, format="JPEG", exif=exif.tobytes())
    return base64.b64encode(buf.getvalue()).decode()


def _error(code: str, status: int) -> tuple[int, dict[str, Any]]:
    body = {
        "status": "error",
        "data": None,
        "message": "x",
        "error": {"code": code, "flow": "FL-08", "details": []},
        "meta": {"request_id": "r", "timestamp": "2026-11-20T00:00:00Z"},
    }
    return status, body


def _ai(responses: list[tuple[int, dict[str, Any]]], calls: list[httpx.Request]) -> Any:
    pending = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        request.read()
        calls.append(request)
        status, body = next(pending)
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    store = LocalStorage(tmp_path / "evidence")
    monkeypatch.setattr(settings, "AI_SERVICE_URL", "http://ia.test:8001")
    monkeypatch.setattr(settings, "AI_API_KEY", "test-key-not-a-secret")
    app.dependency_overrides[get_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_storage, None)


async def _no_sleep(_: float) -> None:
    return None


async def _one_file(
    c: Any, name: str = "CAM01_20260315_042210.jpg"
) -> tuple[dict[str, str], str, str]:
    h = bearer(await register_user(c, "ana@wwf.org"))
    batch = await _batch(c, h, await _camera(c, h, "CAM01"), n=1)
    resp = await _upload(c, h, batch, name, _jpeg(0), 0)
    assert resp.status_code == 202, resp.text
    done = await c.post(f"/api/v1/classification-batches/{batch}/complete", headers=h)
    assert done.status_code == 200, done.text
    return h, batch, resp.json()["data"]["classification_id"]


async def test_worker_saves_result_evidence_and_closes_batch(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue, storage: LocalStorage
) -> None:
    body = _fixture("animal_image")
    body["data"]["evidence"]["image_base64"] = _big_frame()
    calls: list[httpx.Request] = []
    async with make_client() as c:
        h, batch, cid = await _one_file(c)
        async with _ai([(200, body)], calls) as client:
            row = await job.process_one(
                storage, uow_factory=_uow(db_session_factory), client=client
            )
        assert row is not None and str(row.id) == cid
        evidence = await c.get(f"/api/v1/classifications/{cid}/evidence", headers=h)
        luis = bearer(await register_user(c, "luis@wwf.org"))
        foreign = await c.get(f"/api/v1/classifications/{cid}/evidence", headers=luis)
        anonymous = await c.get(f"/api/v1/classifications/{cid}/evidence")
        detail = await c.get(f"/api/v1/classification-batches/{batch}", headers=h)

    saved = await _row(db_session_factory, cid)
    assert saved.status == ClassificationStatus.DONE and saved.error_code is None
    assert saved.category is not None and saved.scientific_name is not None
    assert saved.model_detector and saved.pipeline_version
    assert saved.evidence_key == f"evidence/{saved.finished_at:%Y/%m}/{cid}.jpg"
    assert max(saved.evidence_width or 0, saved.evidence_height or 0) == 960
    assert saved.tmp_key is None and _tmp_files() == []  # el temporal se borra al terminar
    # El nombre original viaja a la IA (para que lea fecha y cámara del nombre).
    assert b'filename="CAM01_20260315_042210.jpg"' in calls[0].content

    assert evidence.status_code == 200
    assert evidence.headers["content-type"] == "image/jpeg"
    assert evidence.headers["cache-control"] == "private, max-age=3600"
    img = Image.open(io.BytesIO(evidence.content))
    assert max(img.size) == 960 and len(img.getexif()) == 0  # sin EXIF (DD-3)
    # S1: lo privado y ajeno responde 404, igual que lo inexistente.
    for resp in (foreign, anonymous):
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "CLASSIFICATION_NOT_FOUND"
    assert detail.json()["data"]["status"] == BatchStatus.COMPLETED.value


async def test_worker_retries_transient_ai_errors_then_succeeds_cb37(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue, storage: LocalStorage
) -> None:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    calls: list[httpx.Request] = []
    responses = [
        _error("IA_MODEL_NOT_READY", 503),
        _error("IA_MODEL_NOT_READY", 503),
        (200, _fixture("blank_image")),
    ]
    async with make_client() as c:
        _, _, cid = await _one_file(c)
        async with _ai(responses, calls) as client:
            await job.process_one(
                storage, uow_factory=_uow(db_session_factory), client=client, sleep=sleep
            )
    saved = await _row(db_session_factory, cid)
    assert waits == [5.0, 30.0] and len(calls) == 3
    assert saved.status == ClassificationStatus.DONE
    assert saved.category is not None and saved.category.value == "blank"


async def test_worker_keeps_tmp_on_ai_failure_and_drops_it_on_media_error_dd4(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue, storage: LocalStorage
) -> None:
    async with make_client() as c:
        h = bearer(await register_user(c, "ana@wwf.org"))
        batch = await _batch(c, h, await _camera(c, h, "CAM01"), n=2)
        first = (await _upload(c, h, batch, "a.jpg", _jpeg(0), 0)).json()["data"]
        second = (await _upload(c, h, batch, "b.jpg", _jpeg(60), 1)).json()["data"]
        await c.post(f"/api/v1/classification-batches/{batch}/complete", headers=h)
        down = [_error("IA_MODEL_NOT_READY", 503)] * 3
        async with _ai(down, []) as client:
            await job.process_one(
                storage, uow_factory=_uow(db_session_factory), client=client, sleep=_no_sleep
            )
        async with _ai([_error("IA_DECODE_FAILED", 422)], []) as client:
            await job.process_one(
                storage, uow_factory=_uow(db_session_factory), client=client, sleep=_no_sleep
            )
        detail = await c.get(f"/api/v1/classification-batches/{batch}", headers=h)

    ai_down = await _row(db_session_factory, first["classification_id"])
    bad_file = await _row(db_session_factory, second["classification_id"])
    # DD-4: nunca se inventa un resultado; el error queda en la fila.
    assert ai_down.status == ClassificationStatus.ERROR and ai_down.category is None
    assert ai_down.error_code == "AI_NOT_READY" and ai_down.tmp_key is not None  # reintentable
    assert bad_file.error_code == "MEDIA_DECODE_FAILED" and bad_file.tmp_key is None
    assert _tmp_files() == [ai_down.tmp_key]
    data = detail.json()["data"]
    assert data["status"] == BatchStatus.COMPLETED_WITH_ERRORS.value


async def test_worker_replaces_upload_truncation_warning_with_ai_one(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue, storage: LocalStorage
) -> None:
    body = copy.deepcopy(_fixture("animal_video_truncated"))
    async with make_client() as c:
        _, _, cid = await _one_file(c)
        await _set(
            db_session_factory,
            cid,
            warnings=[{"code": "VIDEO_TRUNCATED", "message": "subida", "context": {}}],
        )
        async with _ai([(200, body)], []) as client:
            await job.process_one(storage, uow_factory=_uow(db_session_factory), client=client)
    saved = await _row(db_session_factory, cid)
    truncated = [w for w in saved.warnings or [] if w["code"] == "VIDEO_TRUNCATED"]
    assert len(truncated) == 1
    assert truncated[0]["context"]["truncated_at_seconds"] == saved.truncated_at_seconds


async def test_worker_skips_row_cancelled_while_processing(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue, storage: LocalStorage
) -> None:
    async with make_client() as c:
        _, _, cid = await _one_file(c)
        factory = _uow(db_session_factory)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_fixture("animal_image"))

        # Se cancela mientras la IA trabaja: el worker no debe pisar el estado.
        original = job._detect_with_backoff

        async def cancel_then_detect(row: Any, client: Any, sleep: Any) -> Any:
            await _set(db_session_factory, cid, status=ClassificationStatus.CANCELLED)
            return await original(row, client, sleep)

        job_detect = job._detect_with_backoff
        job._detect_with_backoff = cancel_then_detect  # type: ignore[assignment]
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                await job.process_one(storage, uow_factory=factory, client=client)
        finally:
            job._detect_with_backoff = job_detect  # type: ignore[assignment]
    saved = await _row(db_session_factory, cid)
    assert saved.status == ClassificationStatus.CANCELLED and saved.category is None


async def test_worker_idle_and_followup_wake(
    db_session_factory: async_sessionmaker[AsyncSession],
    queue: FakeQueue,
    storage: LocalStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[str] = []

    class Redis:
        async def enqueue_job(self, name: str, *, _job_id: str) -> None:
            enqueued.append(_job_id)

    async def fake_one(storage: Any, client: Any = None) -> Any:
        return None

    monkeypatch.setattr(job, "process_one", fake_one)
    assert await job.process_next({"redis": Redis(), "storage": storage}) == "idle"
    assert enqueued == []

    marker = uuid.uuid4()

    class Row:
        id = marker

    async def fake_done(storage: Any, client: Any = None) -> Any:
        return Row()

    monkeypatch.setattr(job, "process_one", fake_done)
    assert await job.process_next({"redis": Redis(), "storage": storage}) == str(marker)
    assert enqueued == [f"wake:after:{marker}"]


async def test_evidence_404_when_no_frame(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue, storage: LocalStorage
) -> None:
    async with make_client() as c:
        h, _, cid = await _one_file(c)
        pending = await c.get(f"/api/v1/classifications/{cid}/evidence", headers=h)
        missing = await c.get(f"/api/v1/classifications/{uuid.uuid4()}/evidence", headers=h)
    assert pending.status_code == 404 and missing.status_code == 404
