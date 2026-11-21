"""HU-14: reportes Excel (5 hojas) y PDF (§11), con DD-17 y fórmulas neutralizadas (S4)."""

import io
import re
from datetime import datetime

from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import MediaType, ValidationStatus
from tests.conftest import bearer, make_client, register_user, requires_db
from tests.test_hu07_projects import _camera, _project
from tests.test_hu13_catalog_stats import _row, _taxon

pytestmark = requires_db
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def test_excel_has_five_sheets_dd17_and_neutralized_formulas_ca1(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    f = db_session_factory
    jaguar = _taxon("Panthera onca")
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        h, uid = bearer(ana), ana["user"]["id"]  # type: ignore[index]
        cam = await _camera(c, h, "CAM-01", visibility="public")
        project = (
            await _project(c, h, "Amboró 2026", visibility="public", camera_station_ids=[cam])
        ).json()["data"]["id"]
        keep = await _row(
            f,
            cam,
            uid,
            **jaguar,
            file_name="IMG_001.JPG",
            media_type=MediaType.VIDEO,
            evidence_timestamp_seconds=7.2,
            validation_status=ValidationStatus.CONFIRMED,
            validation_notes="=SUM(A1)",
        )
        await _row(
            f,
            cam,
            uid,
            **jaguar,
            file_name="@IMG_002.JPG",
            repeat_of=keep,
            validation_status=ValidationStatus.DISCARDED_REPEAT,
        )
        luis = bearer(await register_user(c, "luis@wwf.org"))
        theirs = await c.get("/api/v1/reports/excel", params={"project_id": project}, headers=luis)
        mine = await c.get("/api/v1/reports/excel", params={"project_id": project}, headers=h)

    assert theirs.status_code == 200 and theirs.headers["content-type"] == XLSX
    disposition = theirs.headers["content-disposition"]
    assert re.fullmatch(r'attachment; filename="WWM_Ambor-2026_\d{8}\.xlsx"', disposition)
    wb = load_workbook(io.BytesIO(theirs.content))
    assert wb.sheetnames == [
        "Resumen",
        "Por especie",
        "Por género",
        "Por familia",
        "Clasificaciones",
    ]
    summary = {row[0]: row[1] for row in wb["Resumen"].iter_rows(min_row=2, values_only=True)}
    assert summary["Alcance"] == "Proyecto" and summary["Avistamientos"] == 1
    assert summary["Repetidos descartados"] == 1 and summary["request_id"] not in (None, "-")
    species = list(wb["Por especie"].iter_rows(min_row=2, values_only=True))
    assert species[0][0] == "Panthera onca" and species[0][4] == 1
    rows = list(wb["Clasificaciones"].iter_rows(min_row=1, values_only=True))
    header, data = rows[0], {r[0]: r for r in rows[1:]}
    col = {name: i for i, name in enumerate(header)}
    first = data["IMG_001.JPG"]
    assert first[col["Latitud"]] == -17.78 and first[col["Longitud"]] == -63.18  # DD-17
    assert first[col["Notas"]] == "'=SUM(A1)"  # S4: texto, no fórmula
    assert first[col["Fotograma (mm:ss)"]] == "00:07"
    assert first[col["Cuenta como avistamiento"]] == "sí"
    repeated = data["'@IMG_002.JPG"]
    assert repeated[col["Cuenta como avistamiento"]] == "no"
    assert repeated[col["Repetido de (archivo)"]] == "IMG_001.JPG"
    own = load_workbook(io.BytesIO(mine.content))["Clasificaciones"]
    own_rows = {r[0]: r for r in own.iter_rows(min_row=2, values_only=True)}
    assert own_rows["IMG_001.JPG"][col["Latitud"]] == -17.78345  # el dueño ve la exacta


async def test_pdf_has_cover_charts_and_request_id_footer_ca2(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    f = db_session_factory
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        h, uid = bearer(ana), ana["user"]["id"]  # type: ignore[index]
        cam = await _camera(c, h, "CAM01")
        for name in ("Panthera onca", "Tapirus terrestris", "ocelot"):
            await _row(f, cam, uid, **_taxon(name), captured_at=datetime(2026, 3, 2, 4, 0))
        resp = await c.get(
            "/api/v1/reports/pdf",
            params={"camera_station_id": cam, "from": "2026-03-01"},
            headers=h,
        )
    assert resp.status_code == 200 and resp.headers["content-type"] == "application/pdf"
    body = resp.content
    assert body.startswith(b"%PDF-1.4") and body.rstrip().endswith(b"%%EOF")
    request_id = resp.headers["x-request-id"].encode()
    assert b"request_id " + request_id in body
    pages = int(re.search(rb"/Count (\d+)", body).group(1))  # type: ignore[union-attr]
    assert pages >= 2 and f"P\xe1gina 1 de {pages}".encode("latin-1") in body
    assert b"Reporte de monitoreo de fauna" in body and b"(Panthera onca) Tj" in body
    assert b"re f" in body  # barras
    xref = int(body.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
    assert body[xref : xref + 4] == b"xref"


async def test_report_errors_ca3(db_session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        h = bearer(ana)
        cam = await _camera(c, h, "CAM01")
        project = (await _project(c, h, "P")).json()["data"]["id"]
        none = await c.get("/api/v1/reports/excel", headers=h)
        both = await c.get(
            "/api/v1/reports/pdf",
            params={"camera_station_id": cam, "project_id": project},
            headers=h,
        )
        empty = await c.get("/api/v1/reports/excel", params={"camera_station_id": cam}, headers=h)
        luis = bearer(await register_user(c, "luis@wwf.org"))
        private = await c.get(
            "/api/v1/reports/pdf", params={"camera_station_id": cam}, headers=luis
        )
    for resp in (none, both):
        assert resp.status_code == 422 and resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert empty.status_code == 404 and empty.json()["error"]["code"] == "REPORT_EMPTY"
    assert private.status_code == 404 and private.json()["error"]["code"] == "CAMERA_NOT_FOUND"
