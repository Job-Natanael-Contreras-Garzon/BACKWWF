"""HU-15b: /admin/queue (#43), /admin/unlisted-suggestions (#44) y Excel global (#42)."""

import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from openpyxl import load_workbook
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import ClassificationStatus, ValidationStatus
from app.models import Classification
from app.models.admin import AdminAuditLog
from app.services.admin_service import normalize_name
from tests.conftest import FakeQueue, bearer, make_client, register_user, requires_db
from tests.test_hu07_projects import _camera
from tests.test_hu13_catalog_stats import _row, _taxon
from tests.test_hu15a_admin_panel import _admin

pytestmark = requires_db
A = "/api/v1/admin"


async def _setup(c: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    admin = await _admin(c, factory)
    ana = await register_user(c, "ana@example.com")
    h, uid = bearer(ana), ana["user"]["id"]
    public, private = await _camera(c, h, "PUB", "public"), await _camera(c, h, "PRIV")
    return {"admin": bearer(admin), "uid": uid, "public": public, "private": private}


async def _unlisted(
    factory: async_sessionmaker[AsyncSession], camera: str, uid: str, name: str
) -> uuid.UUID:
    row = await _row(factory, camera, uid, **_taxon("Leopardus"))
    async with factory() as s:
        await s.execute(
            update(Classification)
            .where(Classification.id == row)
            .values(
                validation_status=ValidationStatus.CORRECTED_UNLISTED,
                suggested_name=name,
                corrected_scientific_name="Leopardus",
                validated_at=datetime.now(UTC),
            )
        )
        await s.commit()
    return row


async def test_queue_status_counts_and_labels(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        w = await _setup(c, db_session_factory)
        now = datetime.now(UTC)
        for i in range(3):
            await _row(
                db_session_factory,
                w["private"],
                w["uid"],
                status=ClassificationStatus.QUEUED,
                category=None,
                created_at=now - timedelta(minutes=10 - i),
            )
        await _row(
            db_session_factory,
            w["public"],
            w["uid"],
            status=ClassificationStatus.PROCESSING,
            category=None,
            heartbeat_at=now,
            started_at=now,
        )
        await _row(
            db_session_factory,
            w["public"],
            w["uid"],
            started_at=now - timedelta(seconds=50),
            finished_at=now,
        )
        resp = await c.get(f"{A}/queue", headers=w["admin"])
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert (data["queued"], data["processing"]) == (3, 1)
        assert data["workers"] == {
            "alive": True,
            "concurrency": data["workers"]["concurrency"],
            "busy": 1,
        }
        assert data["by_owner"] == [{"label": "Investigador", "queued": 3}]
        assert data["oldest_queued_age_seconds"] >= 590
        assert data["avg_processing_seconds"] == 50.0
        assert data["last_hour"]["done"] == 1
        assert data["email"]["daily_cap"] > 0
        queue.down = True
        assert (await c.get(f"{A}/queue", headers=w["admin"])).json()["data"]["workers"][
            "alive"
        ] is None


async def test_unlisted_suggestions_group_normalized_and_skip_private(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert normalize_name("  Leopardus  Colócolo ") == "leopardus colocolo"
    async with make_client() as c:
        w = await _setup(c, db_session_factory)
        ids = [
            await _unlisted(db_session_factory, w["public"], w["uid"], name)
            for name in ("Leopardus colocolo", "leopardus colócolo", "LEOPARDUS  COLOCOLO")
        ]
        await _unlisted(db_session_factory, w["public"], w["uid"], "Oncifelis geoffroyi")
        await _unlisted(db_session_factory, w["private"], w["uid"], "Secreto privado")
        data = (await c.get(f"{A}/unlisted-suggestions", headers=w["admin"])).json()["data"]
        assert [(s["suggested_name"], s["count"]) for s in data] == [
            ("leopardus colocolo", 3),
            ("oncifelis geoffroyi", 1),
        ]
        assert data[0]["parent_taxon"] == "Leopardus"
        assert set(data[0]["classification_ids"]) == {str(i) for i in ids}


async def test_admin_excel_has_six_sheets_no_private_and_is_audited(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        w = await _setup(c, db_session_factory)
        await _row(
            db_session_factory,
            w["public"],
            w["uid"],
            file_name="=HYPERLINK(1).jpg",
            **_taxon("Puma concolor"),
        )
        for _ in range(3):
            await _row(
                db_session_factory,
                w["private"],
                w["uid"],
                file_name="privado.jpg",
                **_taxon("Panthera onca"),
            )
        await _unlisted(db_session_factory, w["public"], w["uid"], "Leopardus colocolo")
        resp = await c.get(f"{A}/reports/excel", headers=w["admin"])
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-disposition"].startswith(
            'attachment; filename="WWM_admin_all_'
        )
        wb = load_workbook(io.BytesIO(resp.content))
        assert wb.sheetnames == [
            "Plataforma",
            "Fauna por especie",
            "Por género",
            "Por familia",
            "Clasificaciones",
            "Sugerencias",
        ]
        rows = list(wb["Clasificaciones"].iter_rows(min_row=2, values_only=True))
        assert len(rows) == 2  # el puma y el no catalogado; nada de la cámara privada
        assert all(r[1] != "privado.jpg" for r in rows)
        files = {r[1] for r in rows}
        assert "'=HYPERLINK(1).jpg" in files  # escape de fórmulas (S4)
        assert {r[3] for r in rows} == {-17.78}  # público de usuario: redondeado
        species = [r[0] for r in wb["Fauna por especie"].iter_rows(min_row=2, values_only=True)]
        assert "Panthera onca" not in species
        platform = dict(wb["Plataforma"].iter_rows(min_row=2, values_only=True))
        assert platform["content.camera_stations.private"] == 1  # privado solo como conteo
        assert [r[0] for r in wb["Sugerencias"].iter_rows(min_row=2, values_only=True)] == [
            "leopardus colocolo"
        ]
        async with db_session_factory() as s:
            audit = await s.scalar(select(AdminAuditLog).where(AdminAuditLog.action == "export"))
        assert audit is not None and audit.new_value["rows"] == 2


async def test_hu15b_routes_require_admin(
    db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        h = bearer(await register_user(c, "ana@example.com"))
        for path in ("/queue", "/unlisted-suggestions", "/reports/excel"):
            resp = await c.get(A + path, headers=h)
            assert resp.json()["error"]["code"] == "ADMIN_REQUIRED", path
