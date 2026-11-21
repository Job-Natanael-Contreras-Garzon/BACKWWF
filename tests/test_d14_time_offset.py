"""#15d / CB-18 / D14: corregir la hora de una cámara conserva la fecha original y se audita."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import CaptureSource
from app.models import CameraTimeOffset, Classification
from tests.conftest import bearer, make_client, register_user, requires_db
from tests.test_hu07_projects import _camera
from tests.test_hu13_catalog_stats import _row, _taxon

pytestmark = requires_db


async def test_time_offset_shifts_camera_dates_keeps_original_and_audits(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    f = db_session_factory
    jaguar = _taxon("Panthera onca")
    async with make_client() as c:
        ana = await register_user(c, "ana@wwf.org")
        h, uid = bearer(ana), ana["user"]["id"]  # type: ignore[index]
        cam = await _camera(c, h, "CAM01")
        public = await _camera(c, h, "PUB", visibility="public")
        exif = await _row(f, cam, uid, **jaguar, captured_at=datetime(2026, 3, 10, 22, 0))
        name = await _row(
            f,
            cam,
            uid,
            **jaguar,
            captured_at=datetime(2026, 3, 11, 1, 0),
            captured_at_source=CaptureSource.FILENAME,
        )
        outside = await _row(f, cam, uid, **jaguar, captured_at=datetime(2026, 4, 1, 0, 0))
        upload = await _row(
            f,
            cam,
            uid,
            **jaguar,
            captured_at=datetime(2026, 3, 10, 23, 0),
            captured_at_source=CaptureSource.UPLOAD_TIME,
        )
        url = f"/api/v1/camera-stations/{cam}/time-offset"
        body = {
            "offset_seconds": 3600,
            "from": "2026-03-01T00:00:00",
            "to": "2026-03-31T23:59:59",
            "reason": "Reloj en horario de verano",
        }
        first = await c.post(url, json=body, headers=h)
        second = await c.post(url, json={**body, "offset_seconds": -1800}, headers=h)
        zero = await c.post(url, json={**body, "offset_seconds": 0}, headers=h)
        no_reason = await c.post(url, json={"offset_seconds": 60}, headers=h)
        luis = bearer(await register_user(c, "luis@wwf.org"))
        foreign_private = await c.post(url, json=body, headers=luis)
        foreign_public = await c.post(
            f"/api/v1/camera-stations/{public}/time-offset", json=body, headers=luis
        )
        read = (await c.get(f"/api/v1/classifications/{exif}", headers=h)).json()["data"]

    assert first.status_code == 200 and first.json()["data"] == {"updated": 2}
    assert second.json()["data"] == {"updated": 2}
    assert zero.status_code == 422 and no_reason.status_code == 422
    assert foreign_private.status_code == 404 and foreign_public.status_code == 403
    async with f() as s:
        rows = {
            r.id: r
            for r in await s.scalars(
                select(Classification).where(Classification.id.in_([exif, name, outside, upload]))
            )
        }
        audits = list(
            await s.scalars(select(CameraTimeOffset).order_by(CameraTimeOffset.created_at))
        )
    # +1 h y luego −30 min = +30 min; el original es el de antes de la primera corrección.
    assert rows[exif].captured_at == datetime(2026, 3, 10, 22, 30)
    assert rows[exif].captured_at_original == datetime(2026, 3, 10, 22, 0)
    assert rows[name].captured_at == datetime(2026, 3, 11, 1, 30)
    assert rows[outside].captured_at == datetime(2026, 4, 1, 0, 0)  # fuera del rango
    assert rows[outside].captured_at_original is None
    assert rows[upload].captured_at == datetime(2026, 3, 10, 23, 0)  # fecha de subida: no se toca
    assert read["captured_at"] == "2026-03-10T22:30:00"
    assert read["captured_at_original"] == "2026-03-10T22:00:00"
    assert [(a.offset_seconds, a.updated) for a in audits] == [(3600, 2), (-1800, 2)]
    assert audits[0].actor_user_id == uuid.UUID(uid) and audits[0].reason.startswith("Reloj")
