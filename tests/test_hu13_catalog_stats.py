"""HU-13: catálogo SpeciesNet en RAM (#30) y estadísticas ecológicas (#15, #20, §10.3)."""

import itertools
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.enums import (
    CaptureSource,
    Category,
    ClassificationSource,
    ClassificationStatus,
    MediaType,
    Rank,
    ValidationStatus,
)
from app.core.security import hash_token
from app.models import Classification
from app.models.camera_station import CameraStation
from app.services import catalog_service
from app.services.catalog_service import get_catalog
from app.services.policies import Owner
from tests.conftest import bearer, make_client, register_user, requires_db
from tests.test_hu07_projects import _camera, _project

_seq = itertools.count()


def _taxon(name: str) -> dict[str, Any]:
    taxon = get_catalog().search(name, limit=1)[0]
    return {
        "label_id": taxon.label_id,
        "rank": taxon.rank,
        "class_": taxon.class_,
        "order_": taxon.order,
        "family": taxon.family,
        "genus": taxon.genus,
        "species": taxon.species,
        "scientific_name": taxon.scientific_name,
        "common_name": taxon.common_name,
    }


async def _row(
    factory: async_sessionmaker[AsyncSession], camera_id: str, user_id: str, **values: Any
) -> uuid.UUID:
    n = next(_seq)
    defaults: dict[str, Any] = {
        "camera_station_id": uuid.UUID(camera_id),
        "file_name": f"f{n}.jpg",
        "file_sha256": hash_token(f"hu13-{n}"),
        "file_size_bytes": 1,
        "media_type": MediaType.IMAGE,
        "status": ClassificationStatus.DONE,
        "category": Category.ANIMAL,
        "confidence": 0.9,
        "captured_at": datetime(2026, 3, 10, 22, 15),
        "captured_at_source": CaptureSource.EXIF,
    }
    row = Classification(**{**defaults, **values})
    Owner(user_id=uuid.UUID(user_id)).assign_to(row, anon_retain=True)
    async with factory() as s:
        s.add(row)
        await s.commit()
        return row.id


# --- Catálogo (#30, CA-2) ---------------------------------------------------------------------


async def test_catalog_search_is_accent_insensitive_species_first_and_bounded() -> None:
    async with make_client() as c:
        plain = await c.get("/api/v1/catalog/species", params={"q": "jaguar"})
        accented = await c.get("/api/v1/catalog/species", params={"q": "JAGUÁR"})
        genus = await c.get("/api/v1/catalog/species", params={"q": "panthera", "rank": "genus"})
        short = await c.get("/api/v1/catalog/species", params={"q": "j"})
        too_many = await c.get("/api/v1/catalog/species", params={"q": "ja", "limit": 51})
        many = await c.get("/api/v1/catalog/species", params={"q": "felidae", "limit": 50})
    first = plain.json()["data"][0]
    assert first["scientific_name"] == "Panthera onca" and first["rank"] == "species"
    assert set(first) == {
        "label_id",
        "rank",
        "class",
        "order",
        "family",
        "genus",
        "species",
        "scientific_name",
        "common_name",
    }
    assert accented.json()["data"] == plain.json()["data"]
    assert [t["rank"] for t in genus.json()["data"]] == ["genus"]
    for resp in (short, too_many):
        assert resp.status_code == 422 and resp.json()["error"]["code"] == "VALIDATION_ERROR"
    ranks = [t["rank"] for t in many.json()["data"]]
    assert 0 < len(ranks) <= 50 and ranks == sorted(ranks, key=lambda r: r != "species")


async def test_catalog_get_by_label_id_and_404() -> None:
    label = _taxon("Panthera onca")["label_id"]
    async with make_client() as c:
        found = await c.get(f"/api/v1/catalog/species/{label}")
        missing = await c.get("/api/v1/catalog/species/no-existe")
    assert found.json()["data"]["common_name"] == "jaguar"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CATALOG_TAXON_NOT_FOUND"
    assert len(get_catalog().taxa) == 3538


def _copy_catalog(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.json"
    path.write_bytes(Path(settings.CATALOG_PATH).read_bytes())
    return path


async def test_sync_catalog_uses_etag_and_replaces_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _copy_catalog(tmp_path)
    monkeypatch.setattr(settings, "CATALOG_PATH", str(path))
    monkeypatch.setattr(settings, "AI_SERVICE_URL", "http://ia.test:8001")
    monkeypatch.setattr(settings, "AI_API_KEY", "test-key-not-a-secret")
    current = json.loads(path.read_bytes())  # noqa: ASYNC240 - archivo local de la prueba
    new = {**current, "sha256": "0" * 64, "count": 1, "taxa": current["taxa"][:1]}
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.headers.get("if-none-match") == f'"{current["sha256"]}"' and len(seen) == 1:
            return httpx.Response(304)
        return httpx.Response(200, json={"status": "success", "data": new})

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await catalog_service.sync_from_ai(client) == "not_modified"
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await catalog_service.sync_from_ai(client) == "updated"
        assert seen[0].headers["X-API-Key"] == "test-key-not-a-secret"
        assert len(get_catalog().taxa) == 1
    finally:
        catalog_service.set_catalog(None)


# --- Estadísticas (#15, #20, CA-1, CA-3) ------------------------------------------------------


@requires_db
async def test_camera_stats_follow_the_official_rules_ca3(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    jaguar, ocelot, tapir = _taxon("Panthera onca"), _taxon("ocelot"), _taxon("Tapirus terrestris")
    genus = {
        **_taxon("Leopardus pardalis"),
        "rank": Rank.GENUS,
        "species": None,
        "scientific_name": "Leopardus",
        "label_id": None,
    }
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        h, uid = bearer(ana), ana["user"]["id"]  # type: ignore[index]
        cam = await _camera(c, h, "CAM01")
        f = db_session_factory
        await _row(f, cam, uid, **jaguar, validation_status=ValidationStatus.CONFIRMED)
        await _row(f, cam, uid, **jaguar, captured_at=datetime(2026, 4, 2, 3, 0))
        await _row(f, cam, uid, **jaguar, validation_status=ValidationStatus.REJECTED)
        await _row(f, cam, uid, **jaguar, validation_status=ValidationStatus.DISCARDED_REPEAT)
        # La IA dijo ocelote; la persona lo corrigió a tapir: cuenta como tapir (effective).
        await _row(
            f,
            cam,
            uid,
            **ocelot,
            validation_status=ValidationStatus.CORRECTED,
            corrected_label_id=tapir["label_id"],
            corrected_rank=Rank.SPECIES,
            corrected_class=tapir["class_"],
            corrected_order=tapir["order_"],
            corrected_family=tapir["family"],
            corrected_genus=tapir["genus"],
            corrected_species=tapir["species"],
            corrected_scientific_name=tapir["scientific_name"],
            corrected_common_name=tapir["common_name"],
        )
        await _row(f, cam, uid, **genus)
        await _row(
            f,
            cam,
            uid,
            validation_status=ValidationStatus.CORRECTED_UNLISTED,
            suggested_name="Mono raro",
        )
        await _row(f, cam, uid, **jaguar, captured_at_source=CaptureSource.UPLOAD_TIME)
        await _row(f, cam, uid, category=Category.PERSON)
        await _row(f, cam, uid, category=Category.BLANK)
        await _row(f, cam, uid, status=ClassificationStatus.ERROR, category=None)
        await _row(f, cam, uid, **jaguar, status=ClassificationStatus.QUEUED)  # no cuenta
        await _row(f, cam, uid, **jaguar, is_deleted=True)  # no cuenta
        resp = await c.get(f"/api/v1/camera-stations/{cam}/stats", headers=h)
    assert resp.status_code == 200, resp.text
    s = resp.json()["data"]
    assert s["scope"] == "camera_station" and s["scope_name"] == "CAM01"
    assert s["totals"] == {
        "files_processed": 11,
        "files_with_fauna": 8,
        "files_without_fauna": 2,
        "files_error": 1,
        "sightings": 6,
        "validated": 3,
        "corrected": 2,
        "rejected": 1,
        "discarded_repeat": 1,
        "pending_validation": 3,
    }
    assert s["non_animal"] == {"person": 1, "vehicle": 0, "blank": 1}
    species = {r["scientific_name"]: r for r in s["by_species"]}
    assert species["Panthera onca"]["count"] == 3 and species["Panthera onca"]["pct"] == 50.0
    assert species["Panthera onca"]["validated"] == 1
    assert species["Panthera onca"]["first_seen"] == "2026-03-10T22:15:00"
    assert species["Panthera onca"]["last_seen"] == "2026-04-02T03:00:00"
    assert "Leopardus pardalis" not in species and species["Tapirus terrestris"]["count"] == 1
    assert s["by_species"][0]["scientific_name"] == "Panthera onca"  # ordenado por count
    assert s["unidentified_to_species"] == {
        "genus": 1,
        "family": 0,
        "order": 0,
        "class": 0,
        "unlisted": 1,
    }
    assert {g["name"]: g["count"] for g in s["by_genus"]} == {
        "panthera": 3,
        "tapirus": 1,
        "leopardus": 1,
    }
    assert s["by_genus"][0]["label_id"] is not None  # el grupo lleva el label_id del catálogo
    assert s["richness"] == {"species": 2, "genera": 3, "families": 2}
    # by_month/by_hour excluyen upload_time (6 avistamientos, 1 con fecha de subida).
    assert s["by_month"] == [
        {"month": "2026-03", "sightings": 4},
        {"month": "2026-04", "sightings": 1},
    ]
    assert len(s["by_hour"]) == 24 and s["by_hour"][22]["sightings"] == 4
    assert s["effort"]["camera_stations_without_retrieval"] == 1
    assert s["effort"]["trap_days"] > 200
    assert "by_camera" not in s or s["by_camera"] is None


@requires_db
async def test_project_stats_hide_private_cameras_from_third_parties_ca1(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    jaguar = _taxon("Panthera onca")
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        h, uid = bearer(ana), ana["user"]["id"]  # type: ignore[index]
        pub = await _camera(c, h, "PUB", visibility="public")
        pri = await _camera(c, h, "PRI")
        project = (
            await _project(c, h, "Amboró", visibility="public", camera_station_ids=[pub, pri])
        ).json()["data"]["id"]
        for cam, n in ((pub, 2), (pri, 5)):
            for _ in range(n):
                await _row(db_session_factory, cam, uid, **jaguar)
        async with db_session_factory() as s:
            await s.execute(
                update(CameraStation)
                .where(CameraStation.id == uuid.UUID(pub))
                .values(retrieved_at=datetime(2026, 3, 11, 8, 30), still_installed=False)
            )
            await s.commit()
        luis = bearer(await register_user(c, "luis@wwf.org"))
        mine = (await c.get(f"/api/v1/projects/{project}/stats", headers=h)).json()["data"]
        theirs = (await c.get(f"/api/v1/projects/{project}/stats", headers=luis)).json()["data"]
        anon = (await c.get(f"/api/v1/projects/{project}/stats")).json()["data"]
        direct = await c.get(f"/api/v1/camera-stations/{pri}/stats", headers=luis)
        missing = await c.get(f"/api/v1/projects/{uuid.uuid4()}/stats")
    assert mine["totals"]["sightings"] == 7 and len(mine["by_camera"]) == 2
    assert mine["by_camera"][0]["code"] == "PRI"
    for other in (theirs, anon):
        assert other["totals"]["sightings"] == 2
        assert [r["code"] for r in other["by_camera"]] == ["PUB"]
        assert other["effort"]["trap_days"] == 10.0  # 1/3 → 11/3 de la cámara pública
    assert direct.status_code == 404 and direct.json()["error"]["code"] == "CAMERA_NOT_FOUND"
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"


@requires_db
async def test_stats_filters_sections_and_validation(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    jaguar = _taxon("Panthera onca")
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        h, uid = bearer(ana), ana["user"]["id"]  # type: ignore[index]
        cam = await _camera(c, h, "CAM01")
        f = db_session_factory
        await _row(f, cam, uid, **jaguar, validation_status=ValidationStatus.CONFIRMED)
        await _row(f, cam, uid, **jaguar, captured_at=datetime(2026, 5, 1, 1, 0))
        await _row(f, cam, uid, **jaguar, source=ClassificationSource.DESKTOP)
        url = f"/api/v1/camera-stations/{cam}/stats"
        validated = (await c.get(url, params={"only_validated": "true"}, headers=h)).json()
        march = await c.get(url, params={"from": "2026-03-01", "to": "2026-03-31"}, headers=h)
        desktop = (await c.get(url, params={"source": "desktop"}, headers=h)).json()
        only = (await c.get(url, params={"sections": "totals,effort"}, headers=h)).json()
        bad = await c.get(url, params={"sections": "totals,nope"}, headers=h)
        reversed_ = await c.get(url, params={"from": "2026-04-01", "to": "2026-03-01"}, headers=h)
    assert validated["data"]["totals"]["sightings"] == 1
    assert validated["data"]["filters"]["only_validated"] is True
    assert march.json()["data"]["totals"]["sightings"] == 2
    assert march.json()["data"]["filters"]["from"] == "2026-03-01"
    assert march.json()["data"]["effort"]["trap_days"] == 30.6  # 01/03 08:30 → 01/04 00:00
    assert desktop["data"]["totals"]["sightings"] == 1
    assert only["data"]["totals"] and only["data"]["effort"]
    assert only["data"]["by_species"] is None and only["data"]["richness"] is None
    for resp in (bad, reversed_):
        assert resp.status_code == 422 and resp.json()["error"]["code"] == "VALIDATION_ERROR"
