"""HU-08: lotes, subida validada a la cola justa, duplicados por sha256 y límites."""

import asyncio
import io
import os
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.enums import CaptureSource, ClassificationStatus, MediaType
from app.core.errors import ServiceUnavailableError
from app.db.uow import UnitOfWork
from app.integrations.queue import ArqTaskQueue
from app.models import Classification, ClassificationBatch
from app.services.policies import Owner
from app.worker import dispatcher
from tests.conftest import FakeQueue, bearer, make_client, register_user, requires_db

pytestmark = requires_db
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _jpeg(seed: int = 0, *, exif_date: str | None = "2026:03:15 04:22:10", size: int = 32) -> bytes:
    img = Image.new("RGB", (size, size), (seed % 256, 80, 120))
    buf = io.BytesIO()
    exif = Image.Exif()
    if exif_date:
        exif.get_ifd(0x8769)[36867] = exif_date
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _png(seed: int = 0) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (seed % 256, 1, 2)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def videos(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe no disponibles")
    out: dict[str, bytes] = {}
    base = tmp_path_factory.mktemp("videos")
    for name, seconds in (("short", 2), ("long", 17)):
        path = base / f"{name}.mp4"
        subprocess.run(  # noqa: S603 - argumentos fijos de prueba
            [
                FFMPEG,
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=duration={seconds}:size=64x64:rate=5",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
        )
        out[name] = path.read_bytes()
    return out


async def _camera(c: httpx.AsyncClient, h: dict[str, str], code: str, **extra: Any) -> str:
    resp = await c.post(
        "/api/v1/camera-stations",
        json={
            "code": code,
            "latitude": -17.78,
            "longitude": -63.18,
            "deployed_at": "2026-03-01T00:00:00",
            "still_installed": True,
            **extra,
        },
        headers=h,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def _batch(c: httpx.AsyncClient, h: dict[str, str], camera_id: str, n: int = 5) -> str:
    resp = await c.post(
        "/api/v1/classification-batches",
        json={"camera_station_id": camera_id, "expected_files": n},
        headers=h,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def _upload(
    c: httpx.AsyncClient,
    h: dict[str, str],
    batch_id: str,
    name: str,
    content: bytes,
    index: int = 0,
    **form: str,
) -> httpx.Response:
    return await c.post(
        f"/api/v1/classification-batches/{batch_id}/files",
        files={"file": (name, content)},
        data={"client_index": str(index), **form},
        headers=h,
    )


def _tmp_files() -> list[str]:
    root = Path(settings.TMP_UPLOAD_PATH)
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


async def test_create_batch_requires_own_camera_and_respects_limits(
    db_session_factory: async_sessionmaker[AsyncSession],
    queue: FakeQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        own = await _camera(c, bearer(ana), "CAM01")
        luis_pub = await _camera(c, bearer(luis), "LP", visibility="public")
        luis_pri = await _camera(c, bearer(luis), "LR")
        url = "/api/v1/classification-batches"
        missing = await c.post(url, json={"expected_files": 1}, headers=bearer(ana))
        foreign_pub = await c.post(
            url, json={"camera_station_id": luis_pub, "expected_files": 1}, headers=bearer(ana)
        )
        foreign_pri = await c.post(
            url, json={"camera_station_id": luis_pri, "expected_files": 1}, headers=bearer(ana)
        )
        too_many = await c.post(
            url, json={"camera_station_id": own, "expected_files": 501}, headers=bearer(ana)
        )
        created = await c.post(
            url, json={"camera_station_id": own, "expected_files": 3}, headers=bearer(ana)
        )
        monkeypatch.setattr(settings, "QUEUE_MAX_PENDING_PER_USER", 2)
        over_pending = await c.post(
            url, json={"camera_station_id": own, "expected_files": 3}, headers=bearer(ana)
        )
        anon = {
            "X-Anon-Token": (await c.post("/api/v1/anon-sessions")).json()["data"]["anon_token"]
        }
        anon_cam = await _camera(c, anon, "A1")
        monkeypatch.setattr(settings, "QUEUE_MAX_PENDING_PER_USER", 500)
        monkeypatch.setattr(settings, "ANON_MAX_FILES", 2)
        anon_over = await c.post(
            url, json={"camera_station_id": anon_cam, "expected_files": 3}, headers=anon
        )
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "CAMERA_REQUIRED"
    assert foreign_pub.status_code == 403 and foreign_pub.json()["error"]["code"] == "FORBIDDEN"
    assert (
        foreign_pri.status_code == 404 and foreign_pri.json()["error"]["code"] == "CAMERA_NOT_FOUND"
    )
    assert too_many.status_code == 422
    data = created.json()["data"]
    assert created.status_code == 201
    assert (data["status"], data["items"], data["camera_station_code"]) == ("open", [], "CAM01")
    assert data["counts"] == {
        "received": 0,
        "queued": 0,
        "processing": 0,
        "done": 0,
        "failed": 0,
        "cancelled": 0,
    }
    assert (
        over_pending.status_code == 429
        and over_pending.json()["error"]["code"] == "QUEUE_USER_LIMIT"
    )
    assert (
        anon_over.status_code == 422 and anon_over.json()["error"]["code"] == "ANON_LIMIT_REACHED"
    )
    assert anon_over.json()["message"].startswith("Sin cuenta puedes clasificar hasta 2 archivos")


async def test_valid_upload_is_queued_with_position_exif_date_and_wakes_queue(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    content = _jpeg()
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        cam = await _camera(c, bearer(ana), "CAM01")
        batch = await _batch(c, bearer(ana), cam)
        resp = await _upload(c, bearer(ana), batch, "foto.jpg", content)
    assert resp.status_code == 202, resp.text
    item = resp.json()["data"]
    assert (item["status"], item["client_index"], item["file_name"]) == ("queued", 0, "foto.jpg")
    assert item["queue"] == {"position": 1, "estimated_wait_seconds": 20}
    assert queue.woken == [uuid.UUID(item["classification_id"])]
    async with db_session_factory() as s:
        row = (await s.scalars(select(Classification))).one()
    import hashlib

    assert row.file_sha256 == hashlib.sha256(content).hexdigest()
    assert (row.media_type, row.status, row.file_size_bytes) == (
        MediaType.IMAGE,
        ClassificationStatus.QUEUED,
        len(content),
    )
    assert (row.captured_at, row.captured_at_source) == (
        datetime(2026, 3, 15, 4, 22, 10),
        CaptureSource.EXIF,
    )
    assert row.tmp_key in _tmp_files() and row.tmp_key.endswith(".jpg")
    assert row.anon_retain is None  # usuario con cuenta


async def test_duplicates_by_sha256_same_camera_renamed_other_camera_other_user_cb50_54(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    content = _jpeg(7)
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        cam1 = await _camera(c, bearer(ana), "CAM01")
        cam2 = await _camera(c, bearer(ana), "CAM02")
        b1 = await _batch(c, bearer(ana), cam1)
        b2 = await _batch(c, bearer(ana), cam2)
        first = await _upload(c, bearer(ana), b1, "a.jpg", content, 0)
        same = await _upload(c, bearer(ana), b1, "a.jpg", content, 1)
        renamed = await _upload(c, bearer(ana), b1, "renombrado.jpg", content, 2)
        other_cam = await _upload(c, bearer(ana), b2, "a.jpg", content, 0)
        luis_cam = await _camera(c, bearer(luis), "LCAM")
        luis_batch = await _batch(c, bearer(luis), luis_cam)
        other_user = await _upload(c, bearer(luis), luis_batch, "a.jpg", content, 0)
        batch_view = await c.post(
            f"/api/v1/classification-batches/{b1}/complete", headers=bearer(ana)
        )
    first_id = first.json()["data"]["classification_id"]
    for resp in (same, renamed):
        assert resp.status_code == 200
        err = resp.json()["data"]["error"]
        assert err["code"] == "DUPLICATE_FILE"
        assert err["details"][0]["context"]["classification_id"] == first_id
    err = other_cam.json()["data"]["error"]
    assert other_cam.status_code == 200 and err["code"] == "DUPLICATE_FILE_OTHER_CAMERA"
    assert err["details"][0]["context"] == {
        "classification_id": first_id,
        "camera_station_code": "CAM01",
    }
    assert other_user.status_code == 202  # CB-52: otra cuenta, independiente
    assert len(_tmp_files()) == 2  # los rechazados no dejan temporal
    counts = batch_view.json()["data"]["counts"]
    assert (counts["received"], counts["queued"], counts["failed"]) == (3, 1, 2)


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("informe.mp4", b"%PDF-1.7\n" + b"x" * 600, "MEDIA_UNSUPPORTED_FORMAT"),  # CB-57
        ("foto.heic", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 600, "MEDIA_UNSUPPORTED_FORMAT"),
        ("crudo.cr2", b"II*\x00" + b"\x00" * 600, "MEDIA_UNSUPPORTED_FORMAT"),  # CB-57c
        ("foto.png", _jpeg()[:400], "MEDIA_DECODE_FAILED"),  # truncada (CB-58)
    ],
)
async def test_invalid_files_return_200_error_and_leave_no_temp(
    db_session_factory: async_sessionmaker[AsyncSession],
    queue: FakeQueue,
    name: str,
    content: bytes,
    code: str,
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        batch = await _batch(c, bearer(ana), await _camera(c, bearer(ana), "CAM01"))
        resp = await _upload(c, bearer(ana), batch, name, content)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert (data["status"], data["classification_id"], data["error"]["code"]) == (
        "error",
        None,
        code,
    )
    assert _tmp_files() == [] and queue.woken == []


async def test_size_and_pixel_limits_cb59(
    db_session_factory: async_sessionmaker[AsyncSession],
    queue: FakeQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        batch = await _batch(c, bearer(ana), await _camera(c, bearer(ana), "CAM01"))
        monkeypatch.setattr(settings, "MAX_IMAGE_PIXELS", 100)  # 32x32 = 1024 px
        pixels = await _upload(c, bearer(ana), batch, "grande.jpg", _jpeg(1), 0)
        monkeypatch.setattr(settings, "MAX_IMAGE_PIXELS", 100_000_000)
        monkeypatch.setattr(settings, "MAX_FILE_MB", 0)
        monkeypatch.setattr(settings, "UPLOAD_CHUNK_BYTES", 64)
        size = await _upload(c, bearer(ana), batch, "pesada.jpg", _jpeg(2), 1)
    for resp in (pixels, size):
        assert resp.status_code == 200 and resp.json()["data"]["error"]["code"] == "MEDIA_TOO_LARGE"
    assert _tmp_files() == []


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe no disponibles")
async def test_videos_long_ones_are_accepted_with_warning_and_corrupt_rejected_cb56_cb58(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue, videos: dict[str, bytes]
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        batch = await _batch(c, bearer(ana), await _camera(c, bearer(ana), "CAM01"))
        short = await _upload(
            c, bearer(ana), batch, "CAM01_20260315_042210.mp4", videos["short"], 0
        )
        long = await _upload(c, bearer(ana), batch, "largo.mp4", videos["long"], 1)
        corrupt = await _upload(
            c, bearer(ana), batch, "roto.mp4", videos["short"][:200] + b"\x00" * 2000, 2
        )
    assert short.status_code == 202 and short.json()["data"]["warnings"] == []
    assert long.status_code == 202
    assert [w["code"] for w in long.json()["data"]["warnings"]] == ["VIDEO_TRUNCATED"]
    assert (
        corrupt.status_code == 200
        and corrupt.json()["data"]["error"]["code"] == "MEDIA_DECODE_FAILED"
    )
    async with db_session_factory() as s:
        rows = {r.file_name: r for r in await s.scalars(select(Classification))}
    assert (
        rows["largo.mp4"].duration_seconds is not None and rows["largo.mp4"].duration_seconds > 16
    )
    assert rows["CAM01_20260315_042210.mp4"].media_type == MediaType.VIDEO


async def test_capture_date_fallbacks_and_outside_deployment_warning_cb17(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        batch = await _batch(c, bearer(ana), await _camera(c, bearer(ana), "CAM01"))
        by_name = await _upload(c, bearer(ana), batch, "IMG_20260320-101112.png", _png(1), 0)
        by_mtime = await _upload(
            c, bearer(ana), batch, "sin_fecha.png", _png(2), 1, client_mtime="2026-03-21T10:00:00Z"
        )
        before = await _upload(
            c, bearer(ana), batch, "x.jpg", _jpeg(3, exif_date="2025:01:01 00:00:00"), 2
        )
        upload_time = await _upload(c, bearer(ana), batch, "nada.png", _png(4), 3)
    assert by_name.status_code == 202 and by_mtime.status_code == 202
    assert [w["code"] for w in before.json()["data"]["warnings"]] == ["CAPTURE_OUTSIDE_DEPLOYMENT"]
    assert upload_time.status_code == 202
    async with db_session_factory() as s:
        rows = {r.file_name: r for r in await s.scalars(select(Classification))}
    assert (
        rows["IMG_20260320-101112.png"].captured_at,
        rows["IMG_20260320-101112.png"].captured_at_source,
    ) == (
        datetime(2026, 3, 20, 10, 11, 12),
        CaptureSource.FILENAME,
    )
    assert rows["sin_fecha.png"].captured_at_source == CaptureSource.CLIENT_MTIME
    assert rows["sin_fecha.png"].captured_at == datetime(2026, 3, 21, 10, 0, 0)
    assert rows["nada.png"].captured_at_source == CaptureSource.UPLOAD_TIME


async def test_queue_unavailable_full_and_disk_limits_cb35_cb36(
    db_session_factory: async_sessionmaker[AsyncSession],
    queue: FakeQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        batch = await _batch(c, bearer(ana), await _camera(c, bearer(ana), "CAM01"))
        queue.down = True
        down = await _upload(c, bearer(ana), batch, "a.jpg", _jpeg(1), 0)
        queue.down = False
        monkeypatch.setattr(settings, "QUEUE_MAX_GLOBAL", 0)
        full = await _upload(c, bearer(ana), batch, "a.jpg", _jpeg(1), 0)
        monkeypatch.setattr(settings, "QUEUE_MAX_GLOBAL", 5000)
        monkeypatch.setattr(settings, "TMP_DISK_MAX_USAGE", 0.0)
        disk = await _upload(c, bearer(ana), batch, "a.jpg", _jpeg(1), 0)
        reads = await c.get("/api/v1/camera-stations", headers=bearer(ana))  # el resto sigue
    assert down.status_code == 503 and down.json()["error"]["code"] == "QUEUE_UNAVAILABLE"
    assert full.status_code == 503 and full.json()["error"]["code"] == "QUEUE_FULL"
    assert disk.status_code == 503 and disk.json()["error"]["code"] == "QUEUE_FULL"
    assert reads.status_code == 200
    assert _tmp_files() == []
    async with db_session_factory() as s:
        assert list(await s.scalars(select(Classification))) == []


async def test_batch_rules_closed_index_foreign_idempotent_and_replace(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        batch = await _batch(c, bearer(ana), await _camera(c, bearer(ana), "CAM01"), n=2)
        out_of_range = await _upload(c, bearer(ana), batch, "a.jpg", _jpeg(1), 5)
        foreign = await _upload(c, bearer(luis), batch, "a.jpg", _jpeg(1), 0)
        first = await _upload(c, bearer(ana), batch, "a.jpg", _jpeg(1), 0)
        again = await _upload(c, bearer(ana), batch, "a.jpg", _jpeg(1), 0)
        async with db_session_factory() as s:
            await s.execute(
                update(Classification).values(
                    status=ClassificationStatus.ERROR, error_code="AI_TIMEOUT"
                )
            )
            await s.commit()
        failed_view = await c.post(
            f"/api/v1/classification-batches/{batch}/complete", headers=bearer(ana)
        )
        replaced_closed = await _upload(c, bearer(ana), batch, "a.jpg", _jpeg(1), 0)
    assert out_of_range.status_code == 422
    assert foreign.status_code == 404 and foreign.json()["error"]["code"] == "BATCH_NOT_FOUND"
    assert again.status_code == 202
    assert again.json()["data"]["classification_id"] == first.json()["data"]["classification_id"]
    item = failed_view.json()["data"]["items"][0]
    assert item["error"] == {
        "code": "AI_TIMEOUT",
        "message": "El análisis tardó demasiado.",
        "details": [],
    }
    assert failed_view.json()["data"]["status"] == "completed_with_errors"
    assert (
        replaced_closed.status_code == 409
        and replaced_closed.json()["error"]["code"] == "BATCH_CLOSED"
    )


async def test_reupload_replaces_item_in_error(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        batch = await _batch(c, bearer(ana), await _camera(c, bearer(ana), "CAM01"), n=2)
        first = await _upload(c, bearer(ana), batch, "a.jpg", _jpeg(1), 0)
        async with db_session_factory() as s:
            await s.execute(update(Classification).values(status=ClassificationStatus.ERROR))
            await s.commit()
        retry = await _upload(c, bearer(ana), batch, "a.jpg", _jpeg(1), 0)
    assert retry.status_code == 202
    assert retry.json()["data"]["classification_id"] != first.json()["data"]["classification_id"]
    async with db_session_factory() as s:
        rows = list(await s.scalars(select(Classification).order_by(Classification.created_at)))
    assert [(r.is_deleted, r.status) for r in rows] == [
        (True, ClassificationStatus.ERROR),
        (False, ClassificationStatus.QUEUED),
    ]


async def test_complete_and_active_listing(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        cam = await _camera(c, bearer(ana), "CAM01")
        pending = await _batch(c, bearer(ana), cam, n=2)
        await _upload(c, bearer(ana), pending, "a.jpg", _jpeg(1), 0)
        done_empty = await _batch(c, bearer(ana), cam, n=1)
        old = await _batch(c, bearer(ana), cam, n=1)
        processing = await c.post(
            f"/api/v1/classification-batches/{pending}/complete", headers=bearer(ana)
        )
        twice = await c.post(
            f"/api/v1/classification-batches/{pending}/complete", headers=bearer(ana)
        )
        completed = await c.post(
            f"/api/v1/classification-batches/{done_empty}/complete", headers=bearer(ana)
        )
        await c.post(f"/api/v1/classification-batches/{old}/complete", headers=bearer(ana))
        async with db_session_factory() as s:
            await s.execute(
                update(ClassificationBatch)
                .where(ClassificationBatch.id == uuid.UUID(old))
                .values(closed_at=datetime(2026, 1, 1, tzinfo=UTC))
            )
            await s.commit()
        active = await c.get(
            "/api/v1/classification-batches", params={"active": "true"}, headers=bearer(ana)
        )
        history = await c.get(
            "/api/v1/classification-batches",
            params={"status": "completed", "page_size": 1},
            headers=bearer(ana),
        )
    assert processing.json()["data"]["status"] == "processing"
    assert processing.json()["data"]["queue"]["next_position"] == 1
    assert twice.json()["data"]["status"] == "processing"
    assert completed.json()["data"]["status"] == "completed"
    assert completed.json()["data"]["completed_at"] is not None
    ids = [b["id"] for b in active.json()["data"]]
    assert pending in ids and done_empty in ids and old not in ids
    assert all(b["items"] is None for b in active.json()["data"])
    assert history.json()["meta"]["pagination"]["total"] == 2


async def test_anonymous_upload_freezes_anon_retain_cb42(
    db_session_factory: async_sessionmaker[AsyncSession],
    queue: FakeQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with make_client() as c:
        anon = {
            "X-Anon-Token": (await c.post("/api/v1/anon-sessions")).json()["data"]["anon_token"]
        }
        batch = await _batch(c, anon, await _camera(c, anon, "A1"), n=2)
        await _upload(c, anon, batch, "a.jpg", _jpeg(1), 0)
        async with db_session_factory() as s:
            await s.execute(update(ClassificationBatch).values(anon_retain=True))
            from app.models import SystemSetting

            await s.execute(update(SystemSetting).values(value=False))
            await s.commit()
        await _upload(c, anon, batch, "b.jpg", _jpeg(2), 1)
        monkeypatch.setattr(settings, "ANON_MAX_FILES", 2)
        third_batch = await c.post(
            "/api/v1/classification-batches",
            json={
                "camera_station_id": (
                    await c.get("/api/v1/camera-stations", params={"scope": "mine"}, headers=anon)
                ).json()["data"][0]["id"],
                "expected_files": 1,
            },
            headers=anon,
        )
    async with db_session_factory() as s:
        flags = {r.file_name: r.anon_retain for r in await s.scalars(select(Classification))}
    assert flags == {"a.jpg": True, "b.jpg": False}
    assert (
        third_batch.status_code == 422
        and third_batch.json()["error"]["code"] == "ANON_LIMIT_REACHED"
    )


async def _queued(
    factory: async_sessionmaker[AsyncSession], owner: Owner, camera: str, n: int, tag: str
) -> list[uuid.UUID]:
    ids = []
    async with factory() as s:
        for i in range(n):
            row = Classification(
                camera_station_id=uuid.UUID(camera),
                file_name=f"{tag}{i}.jpg",
                file_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
                file_size_bytes=1,
                media_type=MediaType.IMAGE,
                status=ClassificationStatus.QUEUED,
                queued_at=datetime(2026, 1, 1, 0, 0, i, tzinfo=UTC)
                if tag == "a"
                else datetime(2026, 1, 1, 1, 0, i, tzinfo=UTC),
            )
            owner.assign_to(row, anon_retain=False)
            s.add(row)
            await s.flush()
            ids.append(row.id)
        await s.commit()
    return ids


async def test_fair_queue_positions_and_claim_respect_per_owner_inflight_cb30(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        cam_a = await _camera(c, bearer(ana), "A")
        cam_l = await _camera(c, bearer(luis), "L")
    a_ids = await _queued(
        db_session_factory, Owner(user_id=uuid.UUID(ana["user"]["id"])), cam_a, 4, "a"
    )  # type: ignore[index]
    l_ids = await _queued(
        db_session_factory, Owner(user_id=uuid.UUID(luis["user"]["id"])), cam_l, 1, "l"
    )  # type: ignore[index]

    async with UnitOfWork(db_session_factory) as uow:
        positions = await dispatcher.queue_positions(uow, a_ids + l_ids)
    # Luis llegó después, pero su 1.er archivo va 2.º, no 5.º (round-robin por dueño).
    assert [positions[i] for i in a_ids] == [1, 3, 4, 5]
    assert positions[l_ids[0]] == 2

    claimed = []
    for _ in range(5):
        async with UnitOfWork(db_session_factory) as uow:
            row = await dispatcher.claim_next(uow)
            await uow.commit()
            claimed.append(row.id if row else None)
    # Ana tiene 2 en proceso: no se le despacha un 3.º hasta que termine alguno.
    assert claimed == [a_ids[0], l_ids[0], a_ids[1], None, None]


async def test_concurrent_claims_never_take_the_same_item(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        cam = await _camera(c, bearer(ana), "A")
    await _queued(db_session_factory, Owner(user_id=uuid.UUID(ana["user"]["id"])), cam, 2, "a")  # type: ignore[index]

    async def claim() -> uuid.UUID | None:
        async with UnitOfWork(db_session_factory) as uow:
            row = await dispatcher.claim_next(uow)
            await asyncio.sleep(0.2)  # mantiene el bloqueo mientras el otro intenta
            await uow.commit()
            return row.id if row else None

    first, second = await asyncio.gather(claim(), claim())
    assert first is not None and second is not None and first != second


@pytest.mark.skipif(not os.environ.get("REDIS_TEST_URL"), reason="REDIS_TEST_URL no definida")
async def test_arq_queue_against_real_redis() -> None:
    real = ArqTaskQueue(os.environ["REDIS_TEST_URL"])
    target = uuid.uuid4()
    await real.ping()
    await real.wake(target)
    await real.wake(target)  # mismo _job_id: un solo aviso
    pool = await real._redis()
    assert await pool.exists(f"arq:job:wake:{target}") == 1
    assert await pool.zcard("arq:queue") == 1
    await pool.flushdb()
    await real.close()

    dead = ArqTaskQueue("redis://127.0.0.1:1/0")
    with pytest.raises(ServiceUnavailableError) as exc:
        await dead.ping()
    assert exc.value.code == "QUEUE_UNAVAILABLE"
