"""HU-12: consulta (#25, #26), validación humana (#28, #29) y ráfagas (#29b)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import (
    CaptureSource,
    Category,
    ClassificationStatus,
    MediaType,
    Rank,
    ValidationStatus,
)
from app.services.catalog_service import get_catalog
from tests.conftest import bearer, make_client, register_user, requires_db
from tests.test_hu07_projects import _camera
from tests.test_hu13_catalog_stats import _row, _taxon

pytestmark = requires_db
API = "/api/v1/classifications"


def _group(name: str, rank: Rank) -> str:
    return get_catalog().search(name, rank=rank, limit=1)[0].label_id


async def _user(c: Any, email: str) -> tuple[dict[str, str], str]:
    session = await register_user(c, email)
    return bearer(session), session["user"]["id"]  # type: ignore[index]


async def test_list_and_get_follow_visibility_filters_and_shape(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    f = db_session_factory
    jaguar, ocelot = _taxon("Panthera onca"), _taxon("ocelot")
    async with make_client() as c:
        h, uid = await _user(c, "ana@wwf.org")
        cam = await _camera(c, h, "CAM01", visibility="public")
        video = await _row(
            f,
            cam,
            uid,
            **jaguar,
            confidence=0.95,
            media_type=MediaType.VIDEO,
            evidence_key="evidence/2026/11/x.jpg",
            evidence_timestamp_seconds=72.4,
            evidence_frame_index=12,
            low_evidence=True,
            warnings=[{"code": "VIDEO_TRUNCATED", "message": "15 s", "context": {}}],
        )
        await _row(f, cam, uid, **ocelot, confidence=0.4)
        await _row(f, cam, uid, category=Category.BLANK, confidence=0.99)
        await _row(
            f, cam, uid, status=ClassificationStatus.ERROR, category=None, error_code="AI_TIMEOUT"
        )
        luis_h, luis_id = await _user(c, "luis@wwf.org")
        hidden = await _camera(c, luis_h, "PRIV")
        await _row(f, hidden, luis_id, **jaguar)

        mine = (await c.get(API, headers=h)).json()
        errors = (await c.get(API, params={"status": "error"}, headers=h)).json()["data"]
        felids = await c.get(API, params={"taxon": _group("felidae", Rank.FAMILY)}, headers=h)
        sure = await c.get(API, params={"min_confidence": 0.9, "category": "animal"}, headers=h)
        public = (await c.get(API, params={"camera_station_id": cam}, headers=luis_h)).json()
        foreign = await c.get(API, params={"camera_station_id": hidden}, headers=h)
        anonymous = (await c.get(API)).json()
        one = (await c.get(f"{API}/{video}", headers=h)).json()["data"]
        bad_filter = await c.get(API, params={"category": "dragon"}, headers=h)

    assert mine["meta"]["pagination"]["total"] == 3  # done por defecto, solo lo propio
    assert errors[0]["error"]["code"] == "AI_TIMEOUT" and errors[0]["taxonomy"] is None
    assert {r["taxonomy"]["scientific_name"] for r in felids.json()["data"]} == {
        "Panthera onca",
        "Leopardus pardalis",
    }
    assert [r["id"] for r in sure.json()["data"]] == [str(video)]
    assert public["meta"]["pagination"]["total"] == 3  # cámara pública ajena: visible
    assert foreign.status_code == 404 and foreign.json()["error"]["code"] == "CAMERA_NOT_FOUND"
    assert anonymous["data"] == []
    assert one["evidence"]["timestamp_label"] == "01:12"
    assert one["evidence"]["url"] == f"/api/v1/classifications/{video}/evidence"
    assert one["low_evidence"] is True and one["warnings"][0]["code"] == "VIDEO_TRUNCATED"
    assert one["effective_taxonomy"]["class"] == "mammalia"
    assert one["validation"]["status"] == "unvalidated"
    assert bad_filter.status_code == 422


async def test_batch_validation_and_move_isolate_other_owners_ca1(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    f = db_session_factory
    jaguar = _taxon("Panthera onca")
    async with make_client() as c:
        h, uid = await _user(c, "ana@wwf.org")
        cam = await _camera(c, h, "CAM01")
        cam2 = await _camera(c, h, "CAM02")
        mine = [await _row(f, cam, uid, **jaguar) for _ in range(3)]
        queued = await _row(f, cam, uid, **jaguar, status=ClassificationStatus.QUEUED)
        luis_h, luis_id = await _user(c, "luis@wwf.org")
        theirs = await _row(f, await _camera(c, luis_h, "L1"), luis_id, **jaguar)
        luis_public = await _camera(c, luis_h, "L2", visibility="public")
        luis_private = await _camera(c, luis_h, "L3")

        batch = await c.post(
            f"{API}/validation-batch",
            json={"ids": [*map(str, mine), str(theirs), str(queued)], "action": "confirm"},
            headers=h,
        )
        to_public = await c.patch(
            f"{API}/{mine[0]}", json={"camera_station_id": luis_public}, headers=h
        )
        to_private = await c.patch(
            f"{API}/{mine[0]}", json={"camera_station_id": luis_private}, headers=h
        )
        steal = await c.patch(f"{API}/{theirs}", json={"camera_station_id": cam}, headers=h)
        moved = await c.patch(f"{API}/{mine[0]}", json={"camera_station_id": cam2}, headers=h)
        # El mismo archivo ya está en CAM02 → 409.
        copy = await _row(f, cam, uid, **jaguar, file_sha256=moved.json()["data"]["file_sha256"])
        dup = await c.patch(f"{API}/{copy}", json={"camera_station_id": cam2}, headers=h)
        too_many = await c.post(
            f"{API}/validation-batch",
            json={"ids": [str(uuid.uuid4()) for _ in range(501)], "action": "confirm"},
            headers=h,
        )
    data = batch.json()["data"]
    assert data["updated"] == 3
    assert {(s["id"], s["code"]) for s in data["skipped"]} == {
        (str(theirs), "CLASSIFICATION_NOT_FOUND"),
        (str(queued), "CLASSIFICATION_NOT_DONE"),
    }
    assert to_public.status_code == 403 and to_public.json()["error"]["code"] == "CAMERA_NOT_OWNED"
    assert to_private.status_code == 404
    assert steal.status_code == 404 and steal.json()["error"]["code"] == "CLASSIFICATION_NOT_FOUND"
    assert moved.status_code == 200 and moved.json()["data"]["camera_station_id"] == cam2
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "DUPLICATE_FILE"
    assert too_many.status_code == 422


async def test_validation_actions_history_and_errors_ca2(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    f = db_session_factory
    jaguar, puma, leopardus = _taxon("Panthera onca"), _taxon("Puma concolor"), _taxon("ocelot")
    genus_id = _group("leopardus", Rank.GENUS)
    alternatives = [
        {
            "label_id": puma["label_id"],
            "scientific_name": "Puma concolor",
            "common_name": "puma",
            "rank": "species",
            "score": 0.03,
        }
    ]
    async with make_client() as c:
        h, uid = await _user(c, "ana@wwf.org")
        cam = await _camera(c, h, "CAM01")
        cid = await _row(f, cam, uid, **jaguar, alternatives=alternatives)
        other = await _row(f, cam, uid, **jaguar)
        blank = await _row(f, cam, uid, category=Category.BLANK)
        queued = await _row(f, cam, uid, **jaguar, status=ClassificationStatus.QUEUED)
        url = f"{API}/{cid}/validation"

        async def put(target: uuid.UUID, **body: Any) -> Any:
            return await c.put(f"{API}/{target}/validation", json=body, headers=h)

        confirm = await put(cid, action="confirm", notes="Se ve la mancha")
        alt = await put(
            cid, action="correct", label_id=puma["label_id"], correction_source="alternative"
        )
        not_alt = await put(
            cid, action="correct", label_id=leopardus["label_id"], correction_source="alternative"
        )
        unknown = await put(cid, action="correct", label_id="nope", correction_source="catalog")
        to_animal = await put(
            blank, action="correct", label_id=leopardus["label_id"], correction_source="catalog"
        )
        unlisted = await put(
            other,
            action="correct_unlisted",
            suggested_name="Gato de las pampas",
            label_id=genus_id,
        )
        unlisted_species = await put(
            other, action="correct_unlisted", suggested_name="Algo", label_id=jaguar["label_id"]
        )
        discard = await put(cid, action="discard_repeat", repeat_of=str(other))
        self_repeat = await put(cid, action="discard_repeat", repeat_of=str(cid))
        not_done = await put(queued, action="confirm")
        reset = await c.put(url, json={"action": "reset"}, headers=h)
        history = (
            await c.get(f"{API}/{cid}", params={"include": "validation_history"}, headers=h)
        ).json()["data"]
        luis_h, _ = await _user(c, "luis@wwf.org")
        foreign = await c.put(url, json={"action": "reject"}, headers=luis_h)

    assert confirm.json()["data"]["validation"]["status"] == "confirmed"
    assert confirm.json()["data"]["validation"]["notes"] == "Se ve la mancha"
    corrected = alt.json()["data"]
    assert corrected["validation"]["status"] == "corrected"
    assert corrected["validation"]["correction_source"] == "alternative"
    assert corrected["effective_taxonomy"]["scientific_name"] == "Puma concolor"
    assert corrected["taxonomy"]["scientific_name"] == "Panthera onca"  # la IA no se pisa
    assert not_alt.status_code == 422 and not_alt.json()["error"]["code"] == "VALIDATION_ERROR"
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "CATALOG_TAXON_NOT_FOUND"
    assert to_animal.json()["data"]["category"] == "animal"
    u = unlisted.json()["data"]
    assert u["validation"]["status"] == "corrected_unlisted"
    assert u["validation"]["suggested_name"] == "Gato de las pampas"
    assert u["effective_taxonomy"]["rank"] == "genus"
    assert unlisted_species.status_code == 422
    assert discard.json()["data"]["validation"]["repeat_of"] == str(other)
    assert self_repeat.status_code == 422
    assert not_done.status_code == 409 and not_done.json()["error"]["code"] == (
        "CLASSIFICATION_NOT_DONE"
    )
    r = reset.json()["data"]
    assert r["validation"]["status"] == "unvalidated" and r["validation"]["repeat_of"] is None
    assert r["effective_taxonomy"]["scientific_name"] == "Panthera onca"
    assert [e["action"] for e in history["validation_history"]] == [
        "confirm",
        "correct",
        "discard_repeat",
        "reset",
    ]
    assert history["validation_history"][1]["by"] == uid
    assert foreign.status_code == 404


async def test_delete_is_logical_and_cancels_queued(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    f = db_session_factory
    async with make_client() as c:
        h, uid = await _user(c, "ana@wwf.org")
        cam = await _camera(c, h, "CAM01")
        done = await _row(f, cam, uid, **_taxon("Panthera onca"))
        queued = await _row(f, cam, uid, status=ClassificationStatus.QUEUED)
        first = await c.delete(f"{API}/{done}", headers=h)
        again = await c.delete(f"{API}/{done}", headers=h)
        gone = await c.get(f"{API}/{done}", headers=h)
        await c.delete(f"{API}/{queued}", headers=h)
        stats = (await c.get(f"/api/v1/camera-stations/{cam}/stats", headers=h)).json()["data"]
    assert first.status_code == 204 and again.status_code == 404 and gone.status_code == 404
    assert stats["totals"]["sightings"] == 0
    from tests.test_hu09_batch_tracking import _row as raw_row

    row = await raw_row(f, str(queued))
    assert row.is_deleted and row.status == ClassificationStatus.CANCELLED


async def test_burst_candidates_repeat_batch_and_dismiss_ca3(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    f = db_session_factory
    jaguar, tapir = _taxon("Panthera onca"), _taxon("Tapirus terrestris")

    def at(minute: int, second: int = 0) -> datetime:
        return datetime(2026, 3, 15, 4, minute, second)

    async with make_client() as c:
        h, uid = await _user(c, "ana@wwf.org")
        cam, cam2 = await _camera(c, h, "CAM01"), await _camera(c, h, "CAM02")
        a = await _row(f, cam, uid, **jaguar, captured_at=at(22, 10), confidence=0.8)
        b = await _row(f, cam, uid, **jaguar, captured_at=at(24, 0), confidence=0.95)
        d = await _row(f, cam, uid, **jaguar, captured_at=at(28, 30), confidence=0.7)  # encadena
        await _row(f, cam, uid, **jaguar, captured_at=at(50))  # fuera de la ventana: solo
        await _row(
            f,
            cam,
            uid,
            **jaguar,
            captured_at=at(28, 40),
            captured_at_source=CaptureSource.UPLOAD_TIME,
        )  # CB-60c
        await _row(f, cam, uid, **tapir, captured_at=at(23))  # otro taxón (CB-60b)
        await _row(
            f, cam, uid, **jaguar, captured_at=at(25), validation_status=ValidationStatus.REJECTED
        )
        t1 = await _row(f, cam2, uid, **tapir, captured_at=at(1))
        await _row(f, cam2, uid, **tapir, captured_at=at(2))
        url = f"{API}/burst-candidates"
        groups = (await c.get(url, params={"camera_station_id": cam}, headers=h)).json()["data"]
        no_scope = await c.get(url, headers=h)
        keep_none = await c.post(
            f"{API}/repeat-batch", json={"keep_ids": [], "discard_ids": [str(a)]}, headers=h
        )
        mixed = await c.post(
            f"{API}/repeat-batch", json={"keep_ids": [str(b)], "discard_ids": [str(t1)]}, headers=h
        )
        done = await c.post(
            f"{API}/repeat-batch",
            json={"keep_ids": [str(b)], "discard_ids": [str(a), str(d)]},
            headers=h,
        )
        after = (await c.get(url, params={"camera_station_id": cam}, headers=h)).json()["data"]
        reviewed = (
            await c.get(url, params={"camera_station_id": cam, "include_reviewed": True}, headers=h)
        ).json()["data"]
        cam2_groups = (await c.get(url, params={"camera_station_id": cam2}, headers=h)).json()
        dismissed = await c.post(
            f"{API}/repeat-batch/dismiss",
            json={"group_key": cam2_groups["data"][0]["group_key"]},
            headers=h,
        )
        cam2_after = (await c.get(url, params={"camera_station_id": cam2}, headers=h)).json()
        b_read = (await c.get(f"{API}/{b}", headers=h)).json()["data"]
        stats = (await c.get(f"/api/v1/camera-stations/{cam}/stats", headers=h)).json()["data"]
        luis_h, _ = await _user(c, "luis@wwf.org")
        foreign = await c.get(url, params={"camera_station_id": cam}, headers=luis_h)

    assert len(groups) == 1
    g = groups[0]
    assert [i["id"] for i in g["items"]] == [str(a), str(b), str(d)]
    assert g["suggested_keep_id"] == str(b) and g["span_seconds"] == 380
    assert g["camera_station_code"] == "CAM01" and g["taxonomy"]["scientific_name"] == (
        "Panthera onca"
    )
    assert no_scope.status_code == 422
    assert keep_none.status_code == 422
    assert keep_none.json()["error"]["code"] == "REPEAT_KEEP_REQUIRED"
    assert mixed.status_code == 422 and mixed.json()["error"]["code"] == "REPEAT_MIXED_CAMERAS"
    assert done.json()["data"] == {"kept": 1, "discarded": 2}
    assert after == [] and len(reviewed) == 1
    assert b_read["validation"]["status"] == "confirmed"
    assert stats["totals"]["discarded_repeat"] == 2
    assert dismissed.json()["data"] == {"dismissed": 2}
    assert cam2_after["data"] == []
    assert foreign.status_code == 404
