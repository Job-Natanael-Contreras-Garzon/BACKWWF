"""HU-06: cámaras trampa con privacidad DD-17, If-Match, cascada, nearby y redeploy."""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import Category, ClassificationStatus, MediaType, Rank
from app.core.security import hash_token
from app.models import Classification, Project
from app.models.camera_station import CameraStation
from app.models.project import ProjectCameraStation
from app.services.policies import Owner
from tests.conftest import bearer, make_client, register_user, requires_db

pytestmark = requires_db

EXACT = {"latitude": -17.78345, "longitude": -63.18211}


def _body(code_: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": code_,
        "name": f"Cámara {code_}",
        **EXACT,
        "deployed_at": "2026-03-01T08:30:00",
        "still_installed": True,
    }
    body.update(overrides)
    return body


async def _create(
    client: httpx.AsyncClient, headers: dict[str, str], code: str, **overrides: Any
) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/camera-stations", json=_body(code, **overrides), headers=headers
    )
    assert resp.status_code == 201, resp.text
    return dict(resp.json()["data"])


async def _anon_headers(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.post("/api/v1/anon-sessions")
    return {"X-Anon-Token": resp.json()["data"]["anon_token"]}


async def _add_classifications(
    factory: async_sessionmaker[AsyncSession],
    camera_id: str,
    owner_user_id: str,
    statuses: list[ClassificationStatus],
) -> None:
    owner = Owner(user_id=uuid.UUID(owner_user_id))
    async with factory() as s:
        for i, status in enumerate(statuses):
            row = Classification(
                camera_station_id=uuid.UUID(camera_id),
                file_name=f"f{i}.jpg",
                file_sha256=hash_token(f"{camera_id}-{i}"),
                file_size_bytes=10,
                media_type=MediaType.IMAGE,
                status=status,
                category=Category.ANIMAL if status == ClassificationStatus.DONE else None,
                scientific_name="Tapirus terrestris"
                if status == ClassificationStatus.DONE
                else None,
                rank=Rank.SPECIES if status == ClassificationStatus.DONE else None,
                captured_at=datetime(2026, 3, 10, 3, i),
            )
            owner.assign_to(row, anon_retain=False)
            s.add(row)
        await s.commit()


async def test_dd17_owner_sees_exact_others_see_1km_and_private_is_404(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        public = await _create(c, bearer(ana), "PUB01", visibility="public")
        private = await _create(c, bearer(ana), "PRI01")

        own_view = (
            await c.get(f"/api/v1/camera-stations/{public['id']}", headers=bearer(ana))
        ).json()
        other_view = await c.get(f"/api/v1/camera-stations/{public['id']}", headers=bearer(luis))
        visitor_view = await c.get(f"/api/v1/camera-stations/{public['id']}")
        hidden = await c.get(f"/api/v1/camera-stations/{private['id']}", headers=bearer(luis))
        listing = await c.get("/api/v1/camera-stations", headers=bearer(luis))
        nearby = await c.get(
            "/api/v1/camera-stations/nearby",
            params={"lat": EXACT["latitude"], "lng": EXACT["longitude"]},
            headers=bearer(luis),
        )

    assert own_view["data"]["latitude"] == -17.78345
    assert own_view["data"]["location_precision"] == "exact"
    for resp in (other_view, visitor_view):
        data = resp.json()["data"]
        assert (data["latitude"], data["longitude"]) == (-17.78, -63.18)
        assert data["location_precision"] == "approx_1km"
        assert data["owner"] == {
            "type": "user",
            "is_mine": False,
            "display_name": "Investigador",
            "institution": None,
        }
    assert hidden.status_code == 404 and hidden.json()["error"]["code"] == "CAMERA_NOT_FOUND"
    assert [cam["code"] for cam in listing.json()["data"]] == ["PUB01"]
    others = nearby.json()["data"]["public_others"]
    assert [o["code"] for o in others] == ["PUB01"]  # la privada nunca aparece (CB-05)
    assert others[0]["distance_band"] == "<10m"
    assert "distance_m" not in others[0] and "latitude" not in others[0]


async def test_bbox_filters_foreign_cameras_by_rounded_coords_cb05b(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tiny = "-63.18215,-17.78350,-63.18205,-17.78340"  # rodea la coordenada exacta
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        await _create(c, bearer(ana), "PUB01", visibility="public")
        as_owner = await c.get(
            "/api/v1/camera-stations", params={"bbox": tiny}, headers=bearer(ana)
        )
        as_other = await c.get(
            "/api/v1/camera-stations", params={"bbox": tiny}, headers=bearer(luis)
        )
        rounded = await c.get(
            "/api/v1/camera-stations",
            params={"bbox": "-63.19,-17.79,-63.17,-17.77"},
            headers=bearer(luis),
        )
    assert len(as_owner.json()["data"]) == 1
    assert as_other.json()["data"] == []  # no se puede triangular con un bbox diminuto
    assert len(rounded.json()["data"]) == 1


async def test_anonymous_cameras_are_private_limited_and_retain_flag(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        anon = await _anon_headers(c)
        public = await c.post(
            "/api/v1/camera-stations", json=_body("A0", visibility="public"), headers=anon
        )
        for i in range(5):
            await _create(c, anon, f"A{i + 1}")
        sixth = await c.post("/api/v1/camera-stations", json=_body("A6"), headers=anon)
        mine = await c.get("/api/v1/camera-stations", params={"scope": "mine"}, headers=anon)
        no_auth = await c.get("/api/v1/camera-stations", params={"scope": "mine"})
    assert public.status_code == 422 and public.json()["error"]["code"] == "ANON_PUBLIC_NOT_ALLOWED"
    assert sixth.status_code == 422 and sixth.json()["error"]["code"] == "ANON_LIMIT_REACHED"
    assert mine.json()["meta"]["pagination"]["total"] == 5
    assert mine.json()["data"][0]["owner"]["type"] == "anonymous"
    assert no_auth.status_code == 401 and no_auth.json()["error"]["code"] == "AUTH_REQUIRED"
    async with db_session_factory() as s:
        flags = {cam.anon_retain for cam in await s.scalars(select(CameraStation))}
    assert flags == {True}


async def test_code_unique_per_owner_case_insensitive_and_reusable_after_delete_cb13_cb14(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        first = await _create(c, bearer(ana), "CAM01")
        dup = await c.post("/api/v1/camera-stations", json=_body("cam01"), headers=bearer(ana))
        other_owner = await c.post(
            "/api/v1/camera-stations", json=_body("CAM01"), headers=bearer(luis)
        )
        await c.delete(f"/api/v1/camera-stations/{first['id']}", headers=bearer(ana))
        reused = await c.post("/api/v1/camera-stations", json=_body("Cam01"), headers=bearer(ana))
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "CAMERA_CODE_TAKEN"
    assert other_owner.status_code == 201
    assert reused.status_code == 201

    async with make_client() as c1, make_client() as c2:
        r1, r2 = await asyncio.gather(
            c1.post("/api/v1/camera-stations", json=_body("RACE"), headers=bearer(ana)),
            c2.post("/api/v1/camera-stations", json=_body("race"), headers=bearer(ana)),
        )
    assert sorted([r1.status_code, r2.status_code]) == [201, 409]


async def test_patch_requires_if_match_and_rejects_stale_version_cb15(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        cam = await _create(c, bearer(ana), "CAM01")
        url = f"/api/v1/camera-stations/{cam['id']}"
        missing = await c.patch(url, json={"name": "x"}, headers=bearer(ana))
        ok = await c.patch(url, json={"name": "Nuevo"}, headers={**bearer(ana), "If-Match": '"1"'})
        stale = await c.patch(url, json={"name": "Otro"}, headers={**bearer(ana), "If-Match": "1"})
    assert missing.status_code == 422
    assert ok.status_code == 200 and ok.json()["data"]["version"] == 2
    assert ok.json()["data"]["name"] == "Nuevo"
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "CONFLICT_STALE"


async def test_patch_and_delete_on_foreign_cameras_are_403_or_404(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        public = await _create(c, bearer(ana), "PUB", visibility="public")
        private = await _create(c, bearer(ana), "PRI")
        headers = {**bearer(luis), "If-Match": "1"}
        r_pub = await c.patch(
            f"/api/v1/camera-stations/{public['id']}", json={"name": "x"}, headers=headers
        )
        r_pri = await c.patch(
            f"/api/v1/camera-stations/{private['id']}", json={"name": "x"}, headers=headers
        )
        d_pub = await c.delete(f"/api/v1/camera-stations/{public['id']}", headers=bearer(luis))
        d_pri = await c.delete(f"/api/v1/camera-stations/{private['id']}", headers=bearer(luis))
        anon = await _anon_headers(c)
        anon_patch = await c.patch(
            f"/api/v1/camera-stations/{public['id']}",
            json={"name": "x"},
            headers={**anon, "If-Match": "1"},
        )
    assert r_pub.status_code == 403 and r_pub.json()["error"]["code"] == "FORBIDDEN"
    assert d_pub.status_code == 403
    assert r_pri.status_code == 404 and d_pri.status_code == 404
    assert anon_patch.status_code == 403


async def test_date_and_coordinate_validation_cb08_cb11_cb12(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    future = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
    cases = [
        ({"deployed_at": future}, "CAMERA_INVALID_DATES"),
        ({"still_installed": False, "retrieved_at": "2026-02-01T00:00:00"}, "CAMERA_INVALID_DATES"),
        ({"still_installed": True, "retrieved_at": "2026-04-01T00:00:00"}, "CAMERA_INVALID_DATES"),
        ({"still_installed": False}, "CAMERA_INVALID_DATES"),
        ({"latitude": 95}, "VALIDATION_ERROR"),
        ({"longitude": -181}, "VALIDATION_ERROR"),
        ({"deployed_at": "2026-03-01T08:30:00Z"}, "VALIDATION_ERROR"),
        ({"code": "   "}, "VALIDATION_ERROR"),
    ]
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        for i, (overrides, code) in enumerate(cases):
            resp = await c.post(
                "/api/v1/camera-stations", json=_body(f"X{i}", **overrides), headers=bearer(ana)
            )
            assert resp.status_code == 422, (overrides, resp.text)
            assert resp.json()["error"]["code"] == code, overrides
        retired = await c.post(
            "/api/v1/camera-stations",
            json=_body("OK", still_installed=False, retrieved_at="2026-04-01T00:00:00"),
            headers=bearer(ana),
        )
    assert retired.status_code == 201


async def test_coordinate_and_move_warnings_cb07_cb09(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        zero = await c.post(
            "/api/v1/camera-stations", json=_body("Z", latitude=0, longitude=0), headers=bearer(ana)
        )
        swapped = await c.post(
            "/api/v1/camera-stations",
            json=_body("S", latitude=-63.18, longitude=-17.78),
            headers=bearer(ana),
        )
        abroad = await c.post(
            "/api/v1/camera-stations",
            json=_body("LIMA", latitude=-12.05, longitude=-77.04),
            headers=bearer(ana),
        )
        cam = await _create(c, bearer(ana), "CAM01")
        await _add_classifications(
            db_session_factory,
            cam["id"],
            ana["user"]["id"],
            [ClassificationStatus.DONE],  # type: ignore[index]
        )
        url = f"/api/v1/camera-stations/{cam['id']}"
        small = await c.patch(
            url, json={"latitude": -17.78350}, headers={**bearer(ana), "If-Match": "1"}
        )
        big = await c.patch(
            url, json={"latitude": -17.79}, headers={**bearer(ana), "If-Match": "2"}
        )
    for resp in (zero, swapped):
        assert [w["code"] for w in resp.json()["meta"]["warnings"]] == ["CAMERA_COORDS_SUSPECT"]
    assert abroad.json()["meta"]["warnings"] == []  # fuera de Bolivia es válido
    assert small.json()["meta"]["warnings"] == []
    warning = big.json()["meta"]["warnings"][0]
    assert warning["code"] == "CAMERA_MOVED_WITH_DATA"
    assert warning["context"]["classifications"] == 1


async def test_delete_cascades_cancels_queue_and_leaves_projects_cb21(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        user_id = ana["user"]["id"]  # type: ignore[index]
        cam = await _create(c, bearer(ana), "CAM01")
        await _add_classifications(
            db_session_factory,
            cam["id"],
            user_id,
            [ClassificationStatus.QUEUED, ClassificationStatus.DONE],
        )
        async with db_session_factory() as s:
            project = Project(name="P1")
            Owner(user_id=uuid.UUID(user_id)).assign_to(project, anon_retain=False)
            s.add(project)
            await s.flush()
            s.add(
                ProjectCameraStation(project_id=project.id, camera_station_id=uuid.UUID(cam["id"]))
            )
            await s.commit()

        url = f"/api/v1/camera-stations/{cam['id']}"
        deleted = await c.delete(url, headers=bearer(ana))
        again = await c.delete(url, headers=bearer(ana))
        gone = await c.get(url, headers=bearer(ana))
    assert deleted.status_code == 204 and deleted.content == b""
    assert again.status_code == 409 and again.json()["error"]["code"] == "ENTITY_ALREADY_DELETED"
    assert gone.status_code == 404
    async with db_session_factory() as s:
        rows = list(await s.scalars(select(Classification)))
        links = list(await s.scalars(select(ProjectCameraStation)))
    assert all(r.is_deleted for r in rows)
    assert {(r.status, r.error_code) for r in rows} == {
        (ClassificationStatus.CANCELLED, "CAMERA_DELETED"),
        (ClassificationStatus.DONE, None),
    }
    assert links == []


async def test_nearby_reports_mine_with_flags_and_caps_radius_cb01_cb06(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        same = await _create(c, bearer(ana), "SAME")
        await _create(c, bearer(ana), "NEAR", latitude=-17.78355)  # ~11 m al sur
        await _create(c, bearer(ana), "FAR", latitude=-17.80)  # ~1.8 km
        resp = await c.get(
            "/api/v1/camera-stations/nearby",
            params={
                "lat": EXACT["latitude"],
                "lng": EXACT["longitude"],
                "radius_m": 5000,
                "deployed_at": "2026-03-10T00:00:00",
            },
            headers=bearer(ana),
        )
        excluded = await c.get(
            "/api/v1/camera-stations/nearby",
            params={
                **EXACT,
                "lat": EXACT["latitude"],
                "lng": EXACT["longitude"],
                "exclude_id": same["id"],
            },
            headers=bearer(ana),
        )
        visitor = await c.get("/api/v1/camera-stations/nearby", params={"lat": 0, "lng": 0})
    mine = resp.json()["data"]["mine"]
    assert [m["code"] for m in mine] == ["SAME", "NEAR"]  # FAR queda fuera: radio máx. 200 m
    assert mine[0]["same_location"] is True and mine[0]["distance_m"] == 0
    assert mine[1]["same_location"] is False and 5 < mine[1]["distance_m"] < 20
    assert all(m["overlapping_period"] for m in mine)
    assert [m["code"] for m in excluded.json()["data"]["mine"]] == ["NEAR"]
    assert visitor.status_code == 401


async def test_redeploy_creates_linked_camera_copies_projects_and_closes_previous_cb03(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        user_id = ana["user"]["id"]  # type: ignore[index]
        cam = await _create(c, bearer(ana), "CAM01", visibility="public")
        async with db_session_factory() as s:
            project = Project(name="P1")
            Owner(user_id=uuid.UUID(user_id)).assign_to(project, anon_retain=False)
            s.add(project)
            await s.flush()
            s.add(
                ProjectCameraStation(project_id=project.id, camera_station_id=uuid.UUID(cam["id"]))
            )
            await s.commit()
            project_id = str(project.id)
        url = f"/api/v1/camera-stations/{cam['id']}/redeploy"
        early = await c.post(url, json={"deployed_at": "2026-01-01T00:00:00"}, headers=bearer(ana))
        resp = await c.post(
            url,
            json={"deployed_at": "2026-05-02T09:00:00", "observations": "Cambio de equipo"},
            headers=bearer(ana),
        )
        second = await c.post(
            f"/api/v1/camera-stations/{resp.json()['data']['camera_station']['id']}/redeploy",
            json={"deployed_at": "2026-06-02T09:00:00"},
            headers=bearer(ana),
        )
    assert early.status_code == 422 and early.json()["error"]["code"] == "CAMERA_INVALID_DATES"
    assert resp.status_code == 201
    new, previous = resp.json()["data"]["camera_station"], resp.json()["data"]["previous"]
    assert new["code"] == "CAM01-2"
    assert new["previous_camera_station_id"] == cam["id"]
    assert (new["latitude"], new["longitude"], new["visibility"]) == (
        -17.78345,
        -63.18211,
        "public",
    )
    assert new["project_ids"] == [project_id]
    assert new["observations"] == "Cambio de equipo" and new["still_installed"] is True
    assert previous["still_installed"] is False
    assert previous["retrieved_at"] == "2026-05-02T09:00:00"
    assert second.json()["data"]["camera_station"]["code"] == "CAM01-3"


async def test_create_inside_project_checks_ownership(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        luis = await register_user(c, "luis@wwf.org")
        async with db_session_factory() as s:
            mine = Project(name="Mío")
            Owner(user_id=uuid.UUID(ana["user"]["id"])).assign_to(mine, anon_retain=False)  # type: ignore[index]
            theirs = Project(name="Público de Luis", visibility="public")
            Owner(user_id=uuid.UUID(luis["user"]["id"])).assign_to(theirs, anon_retain=False)  # type: ignore[index]
            s.add_all([mine, theirs])
            await s.commit()
            mine_id, theirs_id = str(mine.id), str(theirs.id)
        ok = await c.post(
            "/api/v1/camera-stations", json=_body("C1", project_id=mine_id), headers=bearer(ana)
        )
        forbidden = await c.post(
            "/api/v1/camera-stations", json=_body("C2", project_id=theirs_id), headers=bearer(ana)
        )
        missing = await c.post(
            "/api/v1/camera-stations",
            json=_body("C3", project_id=str(uuid.uuid4())),
            headers=bearer(ana),
        )
        in_project = await c.get(
            "/api/v1/camera-stations", params={"project_id": mine_id}, headers=bearer(ana)
        )
    assert ok.status_code == 201 and ok.json()["data"]["project_ids"] == [mine_id]
    assert forbidden.status_code == 403 and forbidden.json()["error"]["code"] == "FORBIDDEN"
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    assert [cam["code"] for cam in in_project.json()["data"]] == ["C1"]


async def test_list_filters_sort_map_view_and_counts(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        b = await _create(c, bearer(ana), "B-quebrada", name="Quebrada sur")
        await _create(
            c,
            bearer(ana),
            "A-ribera",
            name="Ribera",
            still_installed=False,
            retrieved_at="2026-04-01T00:00:00",
        )
        await _add_classifications(
            db_session_factory,
            b["id"],
            ana["user"]["id"],  # type: ignore[index]
            [ClassificationStatus.DONE, ClassificationStatus.DONE, ClassificationStatus.QUEUED],
        )
        h = bearer(ana)
        by_code = await c.get("/api/v1/camera-stations", params={"sort": "code"}, headers=h)
        by_capture = await c.get(
            "/api/v1/camera-stations", params={"sort": "-last_capture_at"}, headers=h
        )
        search = await c.get("/api/v1/camera-stations", params={"q": "queb"}, headers=h)
        retired = await c.get(
            "/api/v1/camera-stations", params={"still_installed": "false"}, headers=h
        )
        wildcard = await c.get("/api/v1/camera-stations", params={"q": "%"}, headers=h)
        paged = await c.get(
            "/api/v1/camera-stations", params={"page_size": 1, "page": 2}, headers=h
        )
        as_map = await c.get("/api/v1/camera-stations", params={"view": "map"}, headers=h)
    assert [x["code"] for x in by_code.json()["data"]] == ["A-ribera", "B-quebrada"]
    assert by_capture.json()["data"][0]["code"] == "B-quebrada"
    assert [x["code"] for x in search.json()["data"]] == ["B-quebrada"]
    assert [x["code"] for x in retired.json()["data"]] == ["A-ribera"]
    assert wildcard.json()["data"] == []  # el % se escapa
    assert paged.json()["meta"]["pagination"] == {
        "page": 2,
        "page_size": 1,
        "total": 2,
        "total_pages": 2,
    }
    counts = next(x for x in by_code.json()["data"] if x["code"] == "B-quebrada")["counts"]
    assert counts == {"classifications": 3, "sightings": 2, "species": 1, "pending_validation": 2}
    item = next(x for x in as_map.json()["data"] if x["code"] == "B-quebrada")
    assert set(item) == {
        "id",
        "code",
        "name",
        "latitude",
        "longitude",
        "location_precision",
        "visibility",
        "is_mine",
        "still_installed",
        "sightings",
        "species",
    }
    assert item["is_mine"] is True and item["sightings"] == 2
