"""HU-15a: panel admin MVP (FL-40..44, CB-43, CB-52, CB-96..99)."""

import logging
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import cli
from app.core.enums import ClassificationStatus, UserRole
from app.core.security import hash_token, verify_password
from app.models import Classification
from app.models.admin import AdminAuditLog
from app.models.anon_session import AnonSession
from app.models.camera_station import CameraStation
from app.models.user import PasswordResetToken, RefreshToken, User
from tests.conftest import bearer, make_client, register_user, requires_db
from tests.test_hu07_projects import _camera
from tests.test_hu13_catalog_stats import _row, _taxon

pytestmark = requires_db
A = "/api/v1/admin"


async def _admin(c: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]) -> Any:
    session = await register_user(c, "admin@example.com")
    async with factory() as s:
        await s.execute(update(User).where(User.email == "admin@example.com").values(role="admin"))
        await s.commit()
    return session


async def _world(c: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """CA-1: una cámara privada con 10 jaguares y una pública con 2 pumas, más una anónima."""
    admin = await _admin(c, factory)
    ana = await register_user(c, "ana@example.com")
    h, uid = bearer(ana), ana["user"]["id"]
    private = await _camera(c, h, "PRIV-1")
    public = await _camera(c, h, "PUB-1", "public")
    jaguar, puma = _taxon("Panthera onca"), _taxon("Puma concolor")
    private_rows = [await _row(factory, private, uid, **jaguar) for _ in range(10)]
    public_rows = [
        await _row(factory, public, uid, evidence_key=f"evidence/2026/11/p{i}.jpg", **puma)
        for i in range(2)
    ]
    anon = await c.post("/api/v1/anon-sessions")
    token = anon.json()["data"]["anon_token"]
    anon_camera = await _camera(c, {"X-Anon-Token": token}, "ANON-1")
    async with factory() as s:
        anon_id = await s.scalar(
            select(AnonSession.id).where(AnonSession.token_hash == hash_token(token))
        )
    return {
        "admin": bearer(admin),
        "admin_id": admin["user"]["id"],
        "ana": h,
        "ana_id": uid,
        "private": private,
        "public": public,
        "private_rows": private_rows,
        "public_rows": public_rows,
        "anon_token": token,
        "anon_id": anon_id,
        "anon_camera": anon_camera,
    }


async def test_admin_routes_require_admin_role(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        ana = await register_user(c, "ana@example.com")
        resp = await c.get(f"{A}/stats", headers=bearer(ana))
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "ADMIN_REQUIRED"
        assert (await c.get(f"{A}/stats")).status_code == 401


async def test_ca1_private_content_only_as_counts_and_404_by_id(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        w = await _world(c, db_session_factory)
        stats = (await c.get(f"{A}/stats", headers=w["admin"])).json()["data"]
        assert stats["content"]["camera_stations"]["private"] == 1
        assert stats["content"]["classifications"]["total"] == 12  # conteo incluye lo privado
        names = {s["scientific_name"] for s in stats["fauna"]["by_species"]}
        assert names == {"Puma concolor"}  # fauna nunca ve lo privado
        assert stats["fauna"]["totals"]["sightings"] == 2
        assert [p["sightings"] for p in stats["fauna_map"]] == [2]
        assert stats["fauna_map"][0]["latitude"] == -17.78  # redondeo ~1 km

        private_id = w["private_rows"][0]
        evidence = await c.get(f"{A}/classifications/{private_id}/evidence", headers=w["admin"])
        assert evidence.status_code == 404
        for entity, eid in (("classifications", private_id), ("camera-stations", w["private"])):
            resp = await c.post(
                f"{A}/{entity}/{eid}/delete", json={"reason": "probar"}, headers=w["admin"]
            )
            assert resp.status_code == 404, resp.text

        cams = (await c.get(f"{A}/camera-stations", headers=w["admin"])).json()["data"]
        by_code = {cam["code"]: cam for cam in cams}
        assert set(by_code) == {"PUB-1", "ANON-1"}
        assert by_code["PUB-1"]["latitude"] == -17.78  # público de usuario: redondeado
        assert by_code["ANON-1"]["latitude"] == pytest.approx(-17.78345)  # anónimo: exacto
        assert by_code["ANON-1"]["owner"]["display_name"].startswith("Anónimo #")
        rows = (await c.get(f"{A}/classifications", headers=w["admin"])).json()
        assert rows["meta"]["pagination"]["total"] == 2


async def test_cb52_fauna_counts_each_sha256_once(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        admin = await _admin(c, db_session_factory)
        ana, beto = (
            await register_user(c, "ana@example.com"),
            await register_user(c, "b@example.com"),
        )
        cam_a = await _camera(c, bearer(ana), "A-1", "public")
        cam_b = await _camera(c, bearer(beto), "B-1", "public")
        same = hash_token("mismo-archivo")
        puma = _taxon("Puma concolor")
        await _row(db_session_factory, cam_a, ana["user"]["id"], file_sha256=same, **puma)
        await _row(db_session_factory, cam_b, beto["user"]["id"], file_sha256=same, **puma)
        stats = (await c.get(f"{A}/stats", headers=bearer(admin))).json()["data"]
        assert stats["fauna"]["totals"]["sightings"] == 1


async def test_ca3_cascade_delete_and_restore_only_same_operation(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        w = await _world(c, db_session_factory)
        first = w["public_rows"][0]
        missing = await c.post(f"{A}/classifications/{first}/delete", json={}, headers=w["admin"])
        assert missing.status_code == 422
        assert missing.json()["error"]["code"] == "DELETE_REASON_REQUIRED"

        one = await c.post(
            f"{A}/classifications/{first}/delete",
            json={"reason": "duplicada"},
            headers=w["admin"],
        )
        assert one.json()["data"]["deleted"]["classifications"] == 1
        again = await c.post(
            f"{A}/classifications/{first}/delete", json={"reason": "otra"}, headers=w["admin"]
        )
        assert again.json()["error"]["code"] == "ENTITY_ALREADY_DELETED"

        cam = await c.post(
            f"{A}/camera-stations/{w['public']}/delete",
            json={"reason": "cámara de prueba"},
            headers=w["admin"],
        )
        assert cam.json()["data"]["deleted"] == {
            "classifications": 1,
            "camera_stations": 1,
            "projects": 0,
        }
        restored = await c.post(
            f"{A}/camera-stations/{w['public']}/restore", json={}, headers=w["admin"]
        )
        # La clasificación borrada antes, en otra operación, sigue borrada.
        assert restored.json()["data"]["restored"]["classifications"] == 1
        async with db_session_factory() as s:
            first_row = await s.get(Classification, first)
            assert first_row is not None and first_row.is_deleted
            audit = (await s.scalars(select(AdminAuditLog))).all()
        assert {str(a.action) for a in audit} >= {"soft_delete", "restore"}
        assert all(a.reason for a in audit if str(a.action) == "soft_delete")
        not_deleted = await c.post(
            f"{A}/camera-stations/{w['public']}/restore", json={}, headers=w["admin"]
        )
        assert not_deleted.json()["error"]["code"] == "ENTITY_NOT_DELETED"

        batch = await c.post(
            f"{A}/delete-batch",
            json={
                "entity": "classifications",
                "ids": [str(first), str(w["public_rows"][1]), str(w["private_rows"][0])],
                "reason": "limpieza",
            },
            headers=w["admin"],
        )
        data = batch.json()["data"]
        assert data["deleted"]["classifications"] == 1
        assert {s["code"] for s in data["skipped"]} == {
            "ENTITY_ALREADY_DELETED",
            "CLASSIFICATION_NOT_FOUND",
        }


async def test_ca2_cb97_deleting_anon_session_cancels_queued_and_kills_token(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        w = await _world(c, db_session_factory)
        async with db_session_factory() as s:
            cam = await s.get(CameraStation, uuid.UUID(w["anon_camera"]))
            assert cam is not None
            row = Classification(
                camera_station_id=cam.id,
                anon_session_id=w["anon_id"],
                anon_retain=True,
                file_name="q.jpg",
                file_sha256=hash_token("q"),
                file_size_bytes=1,
                media_type="image",
                status=ClassificationStatus.QUEUED,
            )
            s.add(row)
            await s.commit()
            queued_id = row.id
        resp = await c.post(
            f"{A}/anon-sessions/{w['anon_id']}/delete",
            json={"reason": "spam"},
            headers=w["admin"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["deleted"]["camera_stations"] == 1
        async with db_session_factory() as s:
            queued = await s.get(Classification, queued_id)
            assert queued is not None and queued.status == ClassificationStatus.CANCELLED
        me = await c.get("/api/v1/camera-stations", headers={"X-Anon-Token": w["anon_token"]})
        assert me.status_code == 401
        listed = (await c.get(f"{A}/anon-sessions", headers=w["admin"])).json()["data"]
        assert listed[0]["is_deleted"] is True and listed[0]["label"].startswith("Anónimo #")


async def test_ca2_cb98_users_deactivate_self_and_others(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        w = await _world(c, db_session_factory)
        own = await c.post(
            f"{A}/users/{w['admin_id']}/deactivate", json={"reason": "x" * 5}, headers=w["admin"]
        )
        assert own.status_code == 409
        assert own.json()["error"]["code"] == "CANNOT_DEACTIVATE_SELF"

        users = (await c.get(f"{A}/users?q=ana", headers=w["admin"])).json()["data"]
        assert users[0]["counts"]["camera_stations_private"] == 1
        assert users[0]["counts"]["classifications"] == 12

        off = await c.post(
            f"{A}/users/{w['ana_id']}/deactivate", json={"reason": "abuso"}, headers=w["admin"]
        )
        assert off.json()["data"]["is_active"] is False
        assert (await c.get("/api/v1/camera-stations", headers=w["ana"])).status_code == 403
        async with db_session_factory() as s:
            live = await s.scalar(
                select(RefreshToken).where(
                    RefreshToken.user_id == uuid.UUID(w["ana_id"]),
                    RefreshToken.revoked_at.is_(None),
                )
            )
            assert live is None
        back = await c.post(f"{A}/users/{w['ana_id']}/reactivate", headers=w["admin"])
        assert back.json()["data"]["is_active"] is True


async def test_password_reset_link_is_audited_without_token(
    db_session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with make_client() as c:
        w = await _world(c, db_session_factory)
        resp = await c.post(
            f"{A}/users/{w['ana_id']}/password-reset-link",
            json={"reason": "sin correo"},
            headers=w["admin"],
        )
        assert resp.status_code == 200, resp.text
        url = resp.json()["data"]["reset_url"]
        token = url.split("token=")[1]
        assert "/restablecer?token=" in url
        assert token not in caplog.text
        async with db_session_factory() as s:
            stored = await s.scalar(select(PasswordResetToken))
            audit = await s.scalar(
                select(AdminAuditLog).where(AdminAuditLog.action == "password_reset_link")
            )
        assert stored is not None and stored.token_hash == hash_token(token)
        assert audit is not None and token not in str(audit.new_value)
        # El enlace sirve en el flujo normal de restablecer.
        reset = await c.post(
            "/api/v1/auth/password/reset", json={"token": token, "new_password": "Nueva1234"}
        )
        assert reset.status_code == 200, reset.text


async def test_ca4_settings_validate_reason_and_audit(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        w = await _world(c, db_session_factory)
        got = (await c.get(f"{A}/settings", headers=w["admin"])).json()["data"]
        assert got["anon_data_retention"]["value"] is True
        bad = await c.put(
            f"{A}/settings",
            json={"anon_data_retention": "no", "reason": "x"},
            headers=w["admin"],
        )
        assert bad.json()["error"]["code"] == "SETTING_INVALID"
        no_reason = await c.put(
            f"{A}/settings", json={"anon_data_retention": False}, headers=w["admin"]
        )
        assert no_reason.json()["error"]["code"] == "DELETE_REASON_REQUIRED"
        put = await c.put(
            f"{A}/settings",
            json={"anon_data_retention": False, "reason": "Pedido de WWF"},
            headers=w["admin"],
        )
        data = put.json()["data"]["anon_data_retention"]
        assert data["value"] is False and data["updated_by"] == "admin@example.com"

        # CB-43: lo ya creado conserva su anon_retain; lo nuevo nace con false.
        new = await c.post("/api/v1/anon-sessions")
        new_cam = await _camera(c, {"X-Anon-Token": new.json()["data"]["anon_token"]}, "N-1")
        async with db_session_factory() as s:
            old = await s.get(CameraStation, uuid.UUID(w["anon_camera"]))
            fresh = await s.get(CameraStation, uuid.UUID(new_cam))
        assert old is not None and old.anon_retain is True
        assert fresh is not None and fresh.anon_retain is False

        log = (await c.get(f"{A}/audit-log?action=update_setting", headers=w["admin"])).json()
        entry = log["data"][0]
        assert entry["old_value"] is True and entry["new_value"] is False
        assert entry["reason"] == "Pedido de WWF"


async def test_cb99_cli_create_and_reset_admin_password(
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.db.uow import UnitOfWork

    monkeypatch.setattr(cli, "UnitOfWork", lambda: UnitOfWork(db_session_factory))
    monkeypatch.setenv(cli.ADMIN_PASSWORD_ENV, "Admin-Temporal-12")
    created = await cli._run_create_admin("Root@Example.com", "Admin")
    assert created["result"] == "created"
    monkeypatch.setenv(cli.ADMIN_PASSWORD_ENV, "Otra-Temporal-123")
    reset = await cli._run_reset_admin_password("root@example.com")
    assert reset["result"] == "password_reset"
    async with db_session_factory() as s:
        admin = await s.scalar(select(User).where(User.email == "root@example.com"))
    assert admin is not None and admin.role == UserRole.ADMIN
    assert admin.must_change_password is True  # SEC-11: temporal, cambiarla al entrar
    assert verify_password("Otra-Temporal-123", admin.password_hash)
    assert "Otra-Temporal-123" not in capsys.readouterr().out
