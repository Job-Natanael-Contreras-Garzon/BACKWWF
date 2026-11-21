"""HU-07: proyectos con privacidad independiente, If-Match y N:M solo con cámaras propias."""

import asyncio
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import Category, ClassificationStatus, MediaType, Rank
from app.core.security import hash_token
from app.models import Classification
from app.models.camera_station import CameraStation
from app.services.policies import Owner
from tests.conftest import bearer, make_client, register_user, requires_db

pytestmark = requires_db


async def _camera(
    c: httpx.AsyncClient, headers: dict[str, str], code: str, visibility: str = "private"
) -> str:
    resp = await c.post(
        "/api/v1/camera-stations",
        json={
            "code": code,
            "latitude": -17.78345,
            "longitude": -63.18211,
            "deployed_at": "2026-03-01T08:30:00",
            "still_installed": True,
            "visibility": visibility,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def _project(
    c: httpx.AsyncClient, headers: dict[str, str], name: str, **extra: Any
) -> httpx.Response:
    return await c.post("/api/v1/projects", json={"name": name, **extra}, headers=headers)


async def _sightings(
    factory: async_sessionmaker[AsyncSession], camera_id: str, user_id: str, n: int, species: str
) -> None:
    owner = Owner(user_id=uuid.UUID(user_id))
    async with factory() as s:
        for i in range(n):
            row = Classification(
                camera_station_id=uuid.UUID(camera_id),
                file_name=f"{species}{i}.jpg",
                file_sha256=hash_token(f"{camera_id}-{species}-{i}"),
                file_size_bytes=1,
                media_type=MediaType.IMAGE,
                status=ClassificationStatus.DONE,
                category=Category.ANIMAL,
                scientific_name=species,
                rank=Rank.SPECIES,
                captured_at=datetime(2026, 3, 1, 1, i),
            )
            owner.assign_to(row, anon_retain=False)
            s.add(row)
        await s.commit()


async def test_public_project_hides_private_cameras_from_others_cb20_cb22(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        pub = await _camera(c, bearer(ana), "PUB", "public")
        pri = await _camera(c, bearer(ana), "PRI")
        await _sightings(db_session_factory, pub, ana["user"]["id"], 2, "Tapirus terrestris")  # type: ignore[index]
        await _sightings(db_session_factory, pri, ana["user"]["id"], 3, "Panthera onca")  # type: ignore[index]
        created = await _project(
            c, bearer(ana), "Amboró", visibility="public", camera_station_ids=[pub, pri]
        )
        pid = created.json()["data"]["id"]
        mine = await c.get(f"/api/v1/projects/{pid}", headers=bearer(ana))
        theirs = await c.get(f"/api/v1/projects/{pid}", headers=bearer(luis))
        empty = await _project(
            c, bearer(ana), "Vacío", visibility="public", camera_station_ids=[pri]
        )
        empty_view = await c.get(f"/api/v1/projects/{empty.json()['data']['id']}")

    assert created.status_code == 201
    assert mine.json()["data"]["counts"] == {
        "camera_stations": 2,
        "classifications": 5,
        "sightings": 5,
        "species": 2,
    }
    other = theirs.json()["data"]
    assert other["camera_station_ids"] == [pub]
    assert [cam["code"] for cam in other["camera_stations"]] == ["PUB"]
    assert other["camera_stations"][0]["location_precision"] == "approx_1km"
    assert other["counts"] == {
        "camera_stations": 1,
        "classifications": 2,
        "sightings": 2,
        "species": 1,
    }
    assert empty_view.json()["data"]["camera_stations"] == []  # CB-22: sin cámaras públicas
    assert empty_view.json()["data"]["counts"]["camera_stations"] == 0


async def test_private_project_of_others_is_404_and_writes_are_403_or_404(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        private = (await _project(c, bearer(ana), "Privado")).json()["data"]["id"]
        public = (await _project(c, bearer(ana), "Público", visibility="public")).json()["data"][
            "id"
        ]
        get_private = await c.get(f"/api/v1/projects/{private}", headers=bearer(luis))
        visitor_private = await c.get(f"/api/v1/projects/{private}")
        h = {**bearer(luis), "If-Match": "1"}
        patch_public = await c.patch(f"/api/v1/projects/{public}", json={"name": "x"}, headers=h)
        patch_private = await c.patch(f"/api/v1/projects/{private}", json={"name": "x"}, headers=h)
        delete_public = await c.delete(f"/api/v1/projects/{public}", headers=bearer(luis))
        listing = await c.get("/api/v1/projects", headers=bearer(luis))
    assert (
        get_private.status_code == 404
        and get_private.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    )
    assert visitor_private.status_code == 404
    assert patch_public.status_code == 403 and delete_public.status_code == 403
    assert patch_private.status_code == 404
    assert [p["name"] for p in listing.json()["data"]] == ["Público"]


async def test_only_own_cameras_can_be_associated_cb23(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        luis_public = await _camera(c, bearer(luis), "LUIS-PUB", "public")
        luis_private = await _camera(c, bearer(luis), "LUIS-PRI")
        on_create = await _project(c, bearer(ana), "P", camera_station_ids=[luis_public])
        pid = (await _project(c, bearer(ana), "P2")).json()["data"]["id"]
        add_public = await c.post(
            f"/api/v1/projects/{pid}/camera-stations",
            json={"camera_station_id": luis_public},
            headers=bearer(ana),
        )
        add_private = await c.post(
            f"/api/v1/projects/{pid}/camera-stations",
            json={"camera_station_id": luis_private},
            headers=bearer(ana),
        )
    assert on_create.status_code == 403 and on_create.json()["error"]["code"] == "CAMERA_NOT_OWNED"
    assert (
        add_public.status_code == 403 and add_public.json()["error"]["code"] == "CAMERA_NOT_OWNED"
    )
    assert (
        add_private.status_code == 404 and add_private.json()["error"]["code"] == "CAMERA_NOT_FOUND"
    )


async def test_association_rules_n_to_m_duplicates_and_removal_cb24_cb25_cb26(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        cam = await _camera(c, bearer(ana), "CAM01")
        p1 = (await _project(c, bearer(ana), "Repetido")).json()["data"]["id"]
        p2_resp = await _project(c, bearer(ana), "Repetido")  # CB-25: nombres no únicos
        p2 = p2_resp.json()["data"]["id"]
        body = {"camera_station_id": cam}
        first = await c.post(
            f"/api/v1/projects/{p1}/camera-stations", json=body, headers=bearer(ana)
        )
        dup = await c.post(f"/api/v1/projects/{p1}/camera-stations", json=body, headers=bearer(ana))
        other = await c.post(
            f"/api/v1/projects/{p2}/camera-stations", json=body, headers=bearer(ana)
        )
        cam_view = await c.get(f"/api/v1/camera-stations/{cam}", headers=bearer(ana))
        removed = await c.delete(
            f"/api/v1/projects/{p1}/camera-stations/{cam}", headers=bearer(ana)
        )
        removed_again = await c.delete(
            f"/api/v1/projects/{p1}/camera-stations/{cam}", headers=bearer(ana)
        )
        still_there = await c.get(f"/api/v1/camera-stations/{cam}", headers=bearer(ana))
    assert p2_resp.status_code == 201
    assert first.status_code == 200 and first.json()["data"]["camera_station_ids"] == [cam]
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "ALREADY_ASSOCIATED"
    assert other.status_code == 200
    assert sorted(cam_view.json()["data"]["project_ids"]) == sorted([p1, p2])  # CB-26
    assert removed.status_code == 204
    assert removed_again.status_code == 404
    assert still_there.json()["data"]["project_ids"] == [p2]


async def test_concurrent_duplicate_association_is_409_not_500(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        cam = await _camera(c, bearer(ana), "CAM01")
        pid = (await _project(c, bearer(ana), "P")).json()["data"]["id"]
    async with make_client() as c1, make_client() as c2:
        url = f"/api/v1/projects/{pid}/camera-stations"
        body = {"camera_station_id": cam}
        r1, r2 = await asyncio.gather(
            c1.post(url, json=body, headers=bearer(ana)),
            c2.post(url, json=body, headers=bearer(ana)),
        )
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]


async def test_patch_if_match_and_delete_keeps_cameras_cb15_cb27(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        cam = await _camera(c, bearer(ana), "CAM01")
        pid = (await _project(c, bearer(ana), "P", camera_station_ids=[cam])).json()["data"]["id"]
        url = f"/api/v1/projects/{pid}"
        missing = await c.patch(url, json={"name": "x"}, headers=bearer(ana))
        ok = await c.patch(
            url,
            json={"name": "Nuevo", "description": "d", "visibility": "public"},
            headers={**bearer(ana), "If-Match": "1"},
        )
        stale = await c.patch(url, json={"name": "y"}, headers={**bearer(ana), "If-Match": "1"})
        empty = await c.patch(url, json={"name": "  "}, headers={**bearer(ana), "If-Match": "2"})
        deleted = await c.delete(url, headers=bearer(ana))
        again = await c.delete(url, headers=bearer(ana))
        gone = await c.get(url, headers=bearer(ana))
        camera = await c.get(f"/api/v1/camera-stations/{cam}", headers=bearer(ana))
    assert missing.status_code == 422
    assert ok.status_code == 200
    assert (ok.json()["data"]["name"], ok.json()["data"]["version"]) == ("Nuevo", 2)
    assert ok.json()["data"]["visibility"] == "public"
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "CONFLICT_STALE"
    assert empty.status_code == 422
    assert deleted.status_code == 204
    assert again.status_code == 409 and again.json()["error"]["code"] == "ENTITY_ALREADY_DELETED"
    assert gone.status_code == 404
    assert camera.status_code == 200 and camera.json()["data"]["project_ids"] == []
    async with db_session_factory() as s:
        assert (await s.scalars(select(CameraStation))).one().is_deleted is False


async def test_anonymous_projects_are_private_and_list_scopes(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        anon = {
            "X-Anon-Token": (await c.post("/api/v1/anon-sessions")).json()["data"]["anon_token"]
        }
        public = await _project(c, anon, "Público", visibility="public")
        private = await _project(c, anon, "Privado")
        patch_public = await c.patch(
            f"/api/v1/projects/{private.json()['data']['id']}",
            json={"visibility": "public"},
            headers={**anon, "If-Match": "1"},
        )
        ana = await register_user(c, "ana@wwf.org")
        await _project(c, bearer(ana), "Zeta pública", visibility="public")
        await _project(c, bearer(ana), "Alfa privada")
        mine = await c.get(
            "/api/v1/projects", params={"scope": "mine", "sort": "name"}, headers=bearer(ana)
        )
        public_only = await c.get("/api/v1/projects", params={"scope": "public"})
        search = await c.get("/api/v1/projects", params={"q": "alfa"}, headers=bearer(ana))
        no_auth = await c.get("/api/v1/projects", params={"scope": "mine"})
    assert public.status_code == 422 and public.json()["error"]["code"] == "ANON_PUBLIC_NOT_ALLOWED"
    assert private.status_code == 201
    assert private.json()["data"]["owner"]["type"] == "anonymous"
    assert patch_public.status_code == 422
    assert [p["name"] for p in mine.json()["data"]] == ["Alfa privada", "Zeta pública"]
    assert [p["name"] for p in public_only.json()["data"]] == ["Zeta pública"]
    assert [p["name"] for p in search.json()["data"]] == ["Alfa privada"]
    assert no_auth.status_code == 401
