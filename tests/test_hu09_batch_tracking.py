"""HU-09: seguimiento con ?since, cancelación, reintento, reaper (FL-33) y limpieza (FL-31)."""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.enums import BatchStatus, ClassificationStatus
from app.db.uow import UnitOfWork
from app.integrations.storage.local import LocalStorage
from app.models import Classification, ClassificationBatch
from app.worker import cron_jobs
from tests.conftest import FakeQueue, bearer, make_client, register_user, requires_db
from tests.test_hu08_batches import _batch, _camera, _jpeg, _tmp_files, _upload

pytestmark = requires_db


async def _setup(c: Any, n: int = 3) -> tuple[dict[str, str], str, list[str]]:
    ana = await register_user(c, "ana@wwf.org")
    h = bearer(ana)
    batch = await _batch(c, h, await _camera(c, h, "CAM01"), n=n)
    ids = []
    for i in range(n):
        resp = await _upload(c, h, batch, f"f{i}.jpg", _jpeg(i * 60), i)
        assert resp.status_code == 202, resp.text
        ids.append(resp.json()["data"]["classification_id"])
    return h, batch, ids


async def _set(factory: async_sessionmaker[AsyncSession], cid: str, **values: Any) -> None:
    async with factory() as s:
        await s.execute(
            update(Classification).where(Classification.id == uuid.UUID(cid)).values(**values)
        )
        await s.commit()


async def _row(factory: async_sessionmaker[AsyncSession], cid: str) -> Classification:
    async with factory() as s:
        return (
            await s.scalars(select(Classification).where(Classification.id == uuid.UUID(cid)))
        ).one()


def _uow(factory: async_sessionmaker[AsyncSession]) -> Any:
    return lambda: UnitOfWork(factory)


async def test_get_batch_since_returns_only_changed_items(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        h, batch, ids = await _setup(c, 2)
        await asyncio.sleep(0.05)
        mark = datetime.now(UTC)
        await asyncio.sleep(0.05)
        await c.delete(f"/api/v1/classification-batches/{batch}/items/1", headers=h)
        full = await c.get(f"/api/v1/classification-batches/{batch}", headers=h)
        delta = await c.get(
            f"/api/v1/classification-batches/{batch}", params={"since": mark.isoformat()}, headers=h
        )
        luis = await register_user(c, "luis@wwf.org")
        foreign = await c.get(f"/api/v1/classification-batches/{batch}", headers=bearer(luis))
    assert [i["client_index"] for i in full.json()["data"]["items"]] == [0, 1]
    changed = delta.json()["data"]["items"]
    assert [(i["client_index"], i["status"]) for i in changed] == [(1, "cancelled")]
    assert changed[0]["error"]["code"] == "CANCELLED_BY_USER"
    assert foreign.status_code == 404 and foreign.json()["error"]["code"] == "BATCH_NOT_FOUND"


async def test_cancel_batch_cancels_queued_only_and_deletes_temps_cb40(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        h, batch, ids = await _setup(c, 3)
        await _set(db_session_factory, ids[0], status=ClassificationStatus.PROCESSING)
        kept_tmp = (await _row(db_session_factory, ids[0])).tmp_key
        resp = await c.post(f"/api/v1/classification-batches/{batch}/cancel", headers=h)
    data = resp.json()["data"]
    assert data["status"] == "cancelled" and data["completed_at"] is not None
    assert [i["status"] for i in data["items"]] == ["processing", "cancelled", "cancelled"]
    assert data["counts"]["cancelled"] == 2
    assert _tmp_files() == [kept_tmp]  # el que procesa conserva su temporal


async def test_cancel_item_rules(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        h, batch, ids = await _setup(c, 2)
        await _set(db_session_factory, ids[1], status=ClassificationStatus.PROCESSING)
        ok = await c.delete(f"/api/v1/classification-batches/{batch}/items/0", headers=h)
        busy = await c.delete(f"/api/v1/classification-batches/{batch}/items/1", headers=h)
        missing = await c.delete(f"/api/v1/classification-batches/{batch}/items/7", headers=h)
    assert ok.status_code == 204
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "ITEM_NOT_CANCELLABLE"
    assert missing.status_code == 404
    row = await _row(db_session_factory, ids[0])
    assert (row.status, row.error_code, row.tmp_key) == (
        ClassificationStatus.CANCELLED,
        "CANCELLED_BY_USER",
        None,
    )


async def test_retry_requeues_error_with_temp_and_410_without_it_cb37_cb39(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        h, batch, ids = await _setup(c, 2)
        await c.post(f"/api/v1/classification-batches/{batch}/complete", headers=h)
        for cid in ids:
            await _set(
                db_session_factory, cid, status=ClassificationStatus.ERROR, error_code="AI_TIMEOUT"
            )
        async with db_session_factory() as s:
            await s.execute(
                update(ClassificationBatch).values(
                    status=BatchStatus.COMPLETED_WITH_ERRORS, closed_at=datetime.now(UTC)
                )
            )
            await s.commit()
        gone_tmp = (await _row(db_session_factory, ids[1])).tmp_key
        assert gone_tmp is not None
        Path(settings.TMP_UPLOAD_PATH, gone_tmp).unlink()  # noqa: ASYNC240 - preparación del test
        queue.woken.clear()

        retried = await c.post(f"/api/v1/classification-batches/{batch}/items/0/retry", headers=h)
        again = await c.post(f"/api/v1/classification-batches/{batch}/items/0/retry", headers=h)
        gone = await c.post(f"/api/v1/classification-batches/{batch}/items/1/retry", headers=h)
        view = await c.get(f"/api/v1/classification-batches/{batch}", headers=h)
    assert retried.status_code == 202 and retried.json()["data"]["status"] == "queued"
    assert retried.json()["data"]["queue"]["position"] == 1
    assert again.status_code == 202  # idempotente: ya estaba en cola
    assert queue.woken == [uuid.UUID(ids[0])]
    assert gone.status_code == 410 and gone.json()["error"]["code"] == "RETRY_FILE_UNAVAILABLE"
    assert view.json()["data"]["status"] == "processing"  # el lote volvió a procesar
    assert (await _row(db_session_factory, ids[0])).error_code is None


async def test_reaper_recovers_expires_closes_and_rewakes_cb32_cb36_cb38_cb39(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        h, batch, ids = await _setup(c, 4)
        await c.post(f"/api/v1/classification-batches/{batch}/complete", headers=h)
        idle_batch = await _batch(c, h, await _camera(c, h, "CAM02"), n=1)
    now = datetime.now(UTC)
    old_beat = now - timedelta(minutes=30)
    await _set(
        db_session_factory,
        ids[0],
        status=ClassificationStatus.PROCESSING,
        heartbeat_at=old_beat,
        attempts=1,
    )
    await _set(
        db_session_factory,
        ids[1],
        status=ClassificationStatus.PROCESSING,
        heartbeat_at=old_beat,
        attempts=3,
    )
    await _set(db_session_factory, ids[2], queued_at=now - timedelta(hours=30))
    expired_tmp = (await _row(db_session_factory, ids[2])).tmp_key
    async with db_session_factory() as s:
        await s.execute(
            update(ClassificationBatch)
            .where(ClassificationBatch.id == uuid.UUID(idle_batch))
            .values(updated_at=now - timedelta(hours=2))
        )
        await s.commit()
    queue.woken.clear()

    summary = await cron_jobs.reaper(queue, _uow(db_session_factory), now)

    assert (summary.requeued, summary.interrupted, summary.expired, summary.batches_closed) == (
        1,
        1,
        1,
        1,
    )
    first, second, third = [await _row(db_session_factory, i) for i in ids[:3]]
    assert (first.status, first.heartbeat_at) == (ClassificationStatus.QUEUED, None)
    assert (second.status, second.error_code) == (
        ClassificationStatus.ERROR,
        "PROCESSING_INTERRUPTED",
    )
    assert (third.status, third.error_code, third.tmp_key) == (
        ClassificationStatus.ERROR,
        "PROCESSING_EXPIRED",
        None,
    )
    assert expired_tmp not in _tmp_files()
    assert sorted(queue.woken) == sorted(
        [uuid.UUID(ids[0]), uuid.UUID(ids[3])]
    )  # los que están en cola
    async with db_session_factory() as s:
        idle = (
            await s.scalars(
                select(ClassificationBatch).where(ClassificationBatch.id == uuid.UUID(idle_batch))
            )
        ).one()
    assert idle.status == BatchStatus.INCOMPLETE

    queue.down = True  # CB-36: con Redis caído el reaper no falla; vuelve a intentar a los 5 min
    again = await cron_jobs.reaper(queue, _uow(db_session_factory), now)
    assert again.rewoken == 0


async def test_reaper_finishes_processing_batches_without_pending(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        h, batch, ids = await _setup(c, 1)
        await c.post(f"/api/v1/classification-batches/{batch}/complete", headers=h)
    await _set(db_session_factory, ids[0], status=ClassificationStatus.DONE)
    summary = await cron_jobs.reaper(queue, _uow(db_session_factory))
    assert summary.batches_finished == 1
    async with db_session_factory() as s:
        assert (await s.scalars(select(ClassificationBatch))).one().status == BatchStatus.COMPLETED


async def test_cleanup_removes_orphans_but_keeps_live_and_soft_deleted_cb_fl31(
    db_session_factory: async_sessionmaker[AsyncSession],
    queue: FakeQueue,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with make_client() as c:
        h, batch, ids = await _setup(c, 2)
    tmp_root = Path(settings.TMP_UPLOAD_PATH)
    old = (datetime.now(UTC) - timedelta(hours=3)).timestamp()
    stray = tmp_root / "huerfano.jpg"
    stray.write_bytes(b"x")
    recent = tmp_root / "reciente.jpg"
    recent.write_bytes(b"x")
    live_tmp = (await _row(db_session_factory, ids[0])).tmp_key
    error_tmp = (await _row(db_session_factory, ids[1])).tmp_key
    for path in (stray, tmp_root / live_tmp, tmp_root / error_tmp):
        os.utime(path, (old, old))
    await _set(
        db_session_factory,
        ids[1],
        status=ClassificationStatus.ERROR,
        updated_at=datetime.now(UTC) - timedelta(hours=30),
    )

    storage = LocalStorage(tmp_path / "evidence-store")
    for key in (
        "evidence/2026/03/orphan.jpg",
        "evidence/2026/03/kept.jpg",
        "evidence/2026/03/fresh.jpg",
    ):
        await storage.put(key, b"jpg", "image/jpeg")
    for key in ("evidence/2026/03/orphan.jpg", "evidence/2026/03/kept.jpg"):
        os.utime(tmp_path / "evidence-store" / key, (old, old))
    await _set(
        db_session_factory, ids[0], evidence_key="evidence/2026/03/kept.jpg", is_deleted=True
    )

    summary = await cron_jobs.cleanup(storage, _uow(db_session_factory))

    remaining = set(_tmp_files())
    assert "huerfano.jpg" not in remaining and "reciente.jpg" in remaining  # < 60 min: se respeta
    assert error_tmp not in remaining and summary.retry_expired == 1
    assert (await _row(db_session_factory, ids[1])).tmp_key is None
    assert not await storage.exists("evidence/2026/03/orphan.jpg")
    assert await storage.exists("evidence/2026/03/kept.jpg")  # su fila está borrada lógicamente
    assert await storage.exists("evidence/2026/03/fresh.jpg")
    assert summary.frames_deleted == 1
