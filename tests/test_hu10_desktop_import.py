"""HU-10: importación segura de paquetes .wwm.zip de escritorio (#32–#35, CB-80..87)."""

import io
import stat
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_storage
from app.core.config import settings
from app.integrations.storage.local import LocalStorage
from app.main import app
from app.models import Classification
from app.models.desktop_import import DesktopImport
from app.services import import_service
from app.worker import cron_jobs
from tests.conftest import FakeQueue, bearer, make_client, register_user, requires_db
from tests.test_hu07_projects import _camera
from tests.test_hu09_batch_tracking import _uow
from tests.test_hu13_catalog_stats import _row, _taxon

pytestmark = requires_db
PACKAGES = Path(__file__).resolve().parent / "fixtures" / "package"
API = "/api/v1/imports"


def _pkg(name: str) -> bytes:
    return (PACKAGES / f"{name}.wwm.zip").read_bytes()


def _zip(entries: dict[str, bytes], *, symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
    return buf.getvalue()


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, queue: FakeQueue) -> Any:
    store = LocalStorage(tmp_path / "evidence")
    monkeypatch.setattr(settings, "TMP_UPLOAD_PATH", str(tmp_path / "tmp"))
    app.dependency_overrides[get_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_storage, None)


async def _confirm(
    c: Any,
    h: dict[str, str],
    import_id: str,
    factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    **body: Any,
) -> tuple[Any, Any]:
    """D10: confirmar responde 202; el worker (acá, directo) importa; GET muestra el resultado."""
    accepted = await c.post(f"{API}/{import_id}/confirm", json=body, headers=h)
    if accepted.status_code == 202:
        await import_service.run_import(uuid.UUID(import_id), storage, uow_factory=_uow(factory))
    return accepted, await c.get(f"{API}/{import_id}", headers=h)


def _tmp_imports() -> list[str]:
    root = import_service.imports_dir()
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


async def _upload(c: Any, h: dict[str, str], content: bytes, **form: str) -> Any:
    return await c.post(
        f"{API}/desktop", files={"package": ("p.wwm.zip", content)}, data=form, headers=h
    )


async def _count(factory: async_sessionmaker[AsyncSession], model: Any) -> int:
    async with factory() as s:
        return int(await s.scalar(select(func.count()).select_from(model)) or 0)


async def test_rejects_unsafe_packages_without_writing_ca1(
    db_session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = zipfile.ZipFile(io.BytesIO(_pkg("sample_valid")))
    base = {n: valid.read(n) for n in valid.namelist()}
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        h = bearer(ana)
        cam = await _camera(c, h, "CAM01")
        cases = {
            "IMPORT_INVALID_PACKAGE": [
                _pkg("invalid_zip_slip"),
                _pkg("invalid_no_manifest"),
                b"no soy un zip",
                _zip(base, symlink="evidence/" + "a" * 64 + ".jpg"),
                _zip({**base, "extra.txt": b"x"}),
            ],
            "IMPORT_CHECKSUM_MISMATCH": [_pkg("invalid_checksum")],
            "IMPORT_UNSUPPORTED_VERSION": [_pkg("invalid_version_2")],
            "IMPORT_TOO_LARGE": [
                _zip({f"evidence/{i:064x}.jpg": b"" for i in range(20_001)}),
            ],
        }
        results = {
            code: [await _upload(c, h, body, camera_station_id=cam) for body in bodies]
            for code, bodies in cases.items()
        }
        monkeypatch.setattr(settings, "IMPORT_MAX_MB", 1)
        bomb = await _upload(
            c, h, _zip({**base, "manifest.json": b" " * (4 * 1024 * 1024)}), camera_station_id=cam
        )
        big = await _upload(c, h, b"0" * (2 * 1024 * 1024), camera_station_id=cam)
        anon = await c.post(
            f"{API}/desktop",
            files={"package": ("p.zip", _pkg("sample_valid"))},
            data={"camera_station_id": cam},
        )
    for code, responses in results.items():
        for resp in responses:
            assert resp.json()["error"]["code"] == code, resp.text
    assert results["IMPORT_TOO_LARGE"][0].status_code == 413
    assert bomb.status_code == 413 and bomb.json()["error"]["code"] == "IMPORT_TOO_LARGE"
    assert big.status_code == 413
    assert anon.status_code == 401
    assert await _count(db_session_factory, DesktopImport) == 0
    assert await _count(db_session_factory, Classification) == 0
    assert _tmp_imports() == []


async def test_preview_reports_counts_issues_duplicates_and_matches_ca2(
    db_session_factory: async_sessionmaker[AsyncSession], storage: LocalStorage
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        h, uid = bearer(ana), ana["user"]["id"]  # type: ignore[index]
        cam = await _camera(c, h, "CAM01")  # instalada el 01/03 08:30
        # El archivo de la línea 1 ya está en la cámara → duplicado (CB-55).
        await _row(
            db_session_factory,
            cam,
            uid,
            **_taxon("Panthera onca"),
            file_sha256="a40fc1c3b4940b764abee6b97106bf51b030f43aee9591a039c444d62e9c5444",
        )
        async with db_session_factory() as s:  # retiro el 10/03: varias capturas quedan fuera
            from app.models.camera_station import CameraStation

            await s.execute(
                update(CameraStation)
                .where(CameraStation.id == uuid.UUID(cam))
                .values(retrieved_at=datetime(2026, 3, 10), still_installed=False)
            )
            await s.commit()
        resp = await _upload(c, h, _pkg("sample_valid"), camera_station_id=cam)
        corrupt = await _upload(c, h, _pkg("invalid_corrupt_jpg"), camera_station_id=cam)
        unknown = await _upload(c, h, _pkg("invalid_unknown_taxon"), camera_station_id=cam)
        new_cam = await _upload(c, h, _pkg("sample_valid"), create_camera="true")
        both = await _upload(
            c, h, _pkg("sample_valid"), camera_station_id=cam, create_camera="true"
        )
    assert resp.status_code == 201, resp.text
    d = resp.json()["data"]
    assert d["status"] == "preview" and d["camera_code_matches"] is True
    assert d["matching_camera_station_id"] == cam
    assert d["package"]["format_version"] == "1.0" and d["package"]["camera_code"] == "CAM01"
    assert d["camera_from_package"]["complete"] is True
    assert d["counts"]["lines"] == 12 and d["counts"]["duplicates"] == 1
    assert d["counts"]["new"] == 11 and d["counts"]["invalid"] == 0
    outside = [i for i in d["issues"] if i["code"] == "CAPTURE_OUTSIDE_DEPLOYMENT"]
    assert len(outside) == d["counts"]["outside_deployment_range"] == 5
    assert all(i["severity"] == "warning" for i in outside)
    issues = corrupt.json()["data"]["issues"]
    assert {"line": 1, "code": "EVIDENCE_INVALID", "severity": "error"}.items() <= issues[0].items()
    unknown_issue = next(i for i in unknown.json()["data"]["issues"] if i["severity"] == "error")
    assert unknown_issue["line"] == 4 and unknown_issue["code"] == "CATALOG_TAXON_NOT_FOUND"
    assert unknown.json()["data"]["counts"]["invalid"] == 1
    assert new_cam.json()["data"]["camera_station"] is None
    assert both.status_code == 422
    assert await _count(db_session_factory, Classification) == 1  # la vista previa no escribe


async def test_confirm_imports_rows_and_frames_then_blocks_reimport_ca3(
    db_session_factory: async_sessionmaker[AsyncSession], storage: LocalStorage
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        h = bearer(ana)
        cam = await _camera(c, h, "CAM01")
        preview = (await _upload(c, h, _pkg("sample_valid"), camera_station_id=cam)).json()
        import_id = preview["data"]["import_id"]
        accepted, done = await _confirm(c, h, import_id, db_session_factory, storage)
        again = await c.post(f"{API}/{import_id}/confirm", json={}, headers=h)
        reimport = await _upload(c, h, _pkg("sample_valid"), camera_station_id=cam)
        rows = (
            await c.get(
                "/api/v1/classifications",
                params={"camera_station_id": cam, "status": "all", "page_size": 50},
                headers=h,
            )
        ).json()["data"]
        animal = next(r for r in rows if r["category"] == "animal")
        frame = await c.get(animal["evidence"]["url"], headers=h)
        listed = (await c.get(API, headers=h)).json()["data"]
        stats = (await c.get(f"/api/v1/camera-stations/{cam}/stats", headers=h)).json()["data"]
        luis = bearer(await register_user(c, "luis@wwf.org"))
        foreign = await c.post(f"{API}/{import_id}/confirm", json={}, headers=luis)
    assert accepted.status_code == 202 and accepted.json()["data"]["status"] == "processing"
    r = done.json()["data"]
    assert done.status_code == 200 and r["status"] == "completed" and r["error"] is None
    result = r["result"]
    assert result["imported"] == 12 and result["skipped_duplicates"] == 0
    assert result["skipped_invalid"] == 0 and result["batch_id"]
    assert again.status_code == 409
    assert reimport.status_code == 409
    assert reimport.json()["error"]["code"] == "IMPORT_ALREADY_IMPORTED"
    assert reimport.json()["error"]["details"][0]["context"]["import_id"] == import_id
    assert len(rows) == 12 and {x["source"] for x in rows} == {"desktop"}
    assert sum(x["status"] == "error" for x in rows) == 1
    assert frame.status_code == 200
    assert len(Image.open(io.BytesIO(frame.content)).getexif()) == 0  # recodificado sin EXIF
    assert listed[0]["import_id"] == import_id and listed[0]["imported"] == 12
    assert listed[0]["camera_code"] == "CAM01"
    assert stats["totals"]["files_with_fauna"] == 7 and stats["totals"]["files_error"] == 1
    assert foreign.status_code == 404 and foreign.json()["error"]["code"] == "IMPORT_NOT_FOUND"
    assert _tmp_imports() == []


async def test_create_camera_on_confirm_and_incomplete_camera(
    db_session_factory: async_sessionmaker[AsyncSession], storage: LocalStorage
) -> None:
    async with make_client() as c:
        h = bearer(await register_user(c, "ana@wwf.org"))
        with_cam = (await _upload(c, h, _pkg("sample_valid"), create_camera="true")).json()
        _, created = await _confirm(
            c, h, with_cam["data"]["import_id"], db_session_factory, storage
        )
        no_cam = (await _upload(c, h, _pkg("sample_valid_no_camera"), create_camera="true")).json()
        missing = await c.post(f"{API}/{no_cam['data']['import_id']}/confirm", json={}, headers=h)
        taken = await c.post(
            f"{API}/{no_cam['data']['import_id']}/confirm",
            json={
                "camera": {
                    "code": "CAM01",
                    "latitude": -17.7,
                    "longitude": -63.1,
                    "deployed_at": "2026-03-01T00:00:00",
                    "still_installed": True,
                }
            },
            headers=h,
        )
        _, fixed = await _confirm(
            c,
            h,
            no_cam["data"]["import_id"],
            db_session_factory,
            storage,
            camera={
                "code": "CAM01-B",
                "latitude": -17.7,
                "longitude": -63.1,
                "deployed_at": "2026-03-01T00:00:00",
                "still_installed": True,
            },
        )
        cams = (await c.get("/api/v1/camera-stations", params={"scope": "mine"}, headers=h)).json()[
            "data"
        ]
    assert created.json()["data"]["result"]["imported"] == 12
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "VALIDATION_ERROR"
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "CAMERA_CODE_TAKEN"
    assert fixed.json()["data"]["status"] == "completed"
    assert sorted(cam["code"] for cam in cams) == ["CAM01", "CAM01-B"]


async def test_cancel_expire_and_cleanup(
    db_session_factory: async_sessionmaker[AsyncSession], storage: LocalStorage
) -> None:
    async with make_client() as c:
        h = bearer(await register_user(c, "ana@wwf.org"))
        cam = await _camera(c, h, "CAM01")
        first = (await _upload(c, h, _pkg("sample_valid"), camera_station_id=cam)).json()["data"]
        second = (await _upload(c, h, _pkg("sample_valid"), camera_station_id=cam)).json()["data"]
        third = (await _upload(c, h, _pkg("sample_valid"), camera_station_id=cam)).json()["data"]
        assert len(_tmp_imports()) == 3
        cancelled = await c.delete(f"{API}/{first['import_id']}", headers=h)
        cancel_again = await c.delete(f"{API}/{first['import_id']}", headers=h)
        async with db_session_factory() as s:
            await s.execute(
                update(DesktopImport)
                .where(
                    DesktopImport.id.in_(
                        [uuid.UUID(second["import_id"]), uuid.UUID(third["import_id"])]
                    )
                )
                .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
            )
            await s.commit()
        expired = await c.post(f"{API}/{second['import_id']}/confirm", json={}, headers=h)
    summary = await cron_jobs.cleanup(storage, uow_factory=_uow(db_session_factory))
    assert cancelled.status_code == 204 and cancel_again.status_code == 404
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "IMPORT_PREVIEW_EXPIRED"
    assert summary.imports_expired == 1  # el tercero lo vence la limpieza FL-31
    assert _tmp_imports() == []


async def test_confirm_needs_the_queue_and_failures_are_reported_d10(
    db_session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    queue: FakeQueue,
) -> None:
    async with make_client() as c:
        h = bearer(await register_user(c, "ana@wwf.org"))
        cam = await _camera(c, h, "CAM01")
        first = (await _upload(c, h, _pkg("sample_valid"), camera_station_id=cam)).json()["data"]
        queue.down = True
        no_redis = await c.post(f"{API}/{first['import_id']}/confirm", json={}, headers=h)
        still = (await c.get(f"{API}/{first['import_id']}", headers=h)).json()["data"]
        queue.down = False
        # El zip desaparece antes de que el worker lo tome: la importación queda failed.
        accepted = await c.post(f"{API}/{first['import_id']}/confirm", json={}, headers=h)
        for leftover in import_service.imports_dir().iterdir():
            leftover.unlink()
        status = await import_service.run_import(
            uuid.UUID(first["import_id"]), storage, uow_factory=_uow(db_session_factory)
        )
        failed = (await c.get(f"{API}/{first['import_id']}", headers=h)).json()["data"]
        # Una importación que el worker dejó colgada la cierra la limpieza FL-31.
        second = (await _upload(c, h, _pkg("sample_valid"), camera_station_id=cam)).json()["data"]
        await c.post(f"{API}/{second['import_id']}/confirm", json={}, headers=h)
        async with db_session_factory() as s:
            await s.execute(
                update(DesktopImport)
                .where(DesktopImport.id == uuid.UUID(second["import_id"]))
                .values(updated_at=datetime.now(UTC) - timedelta(hours=2))
            )
            await s.commit()
        await cron_jobs.cleanup(storage, uow_factory=_uow(db_session_factory))
        stuck = (await c.get(f"{API}/{second['import_id']}", headers=h)).json()["data"]
    assert no_redis.status_code == 503 and no_redis.json()["error"]["code"] == "QUEUE_UNAVAILABLE"
    assert still["status"] == "preview"
    assert accepted.status_code == 202 and queue.imports[0] == uuid.UUID(first["import_id"])
    assert str(status) == "failed" and failed["status"] == "failed"
    assert failed["error"]["code"] == "IMPORT_PREVIEW_EXPIRED" and failed["result"] is None
    assert stuck["status"] == "failed" and stuck["error"]["code"] == "PROCESSING_INTERRUPTED"
    assert await _count(db_session_factory, Classification) == 0
    assert _tmp_imports() == []
