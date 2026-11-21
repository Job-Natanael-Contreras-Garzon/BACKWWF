"""HU-16 · Matriz IDOR (S1, CB-96): cada ruta con id, atacada por otro usuario y por un anónimo.

Regla: lo privado ajeno responde 404 (nunca 403/409/422 que revelen que existe) y no cambia nada.
Si se agrega una ruta con ``{param}`` y no está en ``MATRIX``, ``test_matrix_covers_every_route``
falla: así ninguna ruta nueva entra sin su prueba IDOR.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import ValidationStatus
from app.main import app
from app.models import Classification
from app.models.camera_station import CameraStation
from app.models.project import Project
from tests.conftest import FakeQueue, bearer, make_client, register_user, requires_db
from tests.test_hu07_projects import _camera
from tests.test_hu08_batches import _batch, _jpeg
from tests.test_hu10_desktop_import import _pkg, _upload
from tests.test_hu13_catalog_stats import _row, _taxon

pytestmark = requires_db
V1 = "/api/v1"
OWNER_ONLY = {404}  # privado ajeno
ADMIN_ONLY = {401, 403}  # anónimo sin Bearer → 401; usuario sin rol → 403 ADMIN_REQUIRED
PUBLIC = {"/api/v1/catalog/species/{label_id}"}  # catálogo: no tiene dueño


@dataclass(frozen=True)
class Case:
    method: str
    path: str
    json: Any = None
    files: bool = False
    if_match: bool = False
    expected: frozenset[int] = field(default=frozenset(OWNER_ONLY))


def _c(method: str, path: str, **kw: Any) -> Case:
    if "expected" in kw:
        kw["expected"] = frozenset(kw["expected"])
    return Case(method, V1 + path, **kw)


REASON = {"reason": "prueba IDOR"}
MATRIX: list[Case] = [
    _c("GET", "/camera-stations/{camera_id}"),
    _c("PATCH", "/camera-stations/{camera_id}", json={"name": "x"}, if_match=True),
    _c("DELETE", "/camera-stations/{camera_id}"),
    _c(
        "POST", "/camera-stations/{camera_id}/redeploy", json={"deployed_at": "2026-04-01T08:00:00"}
    ),
    _c(
        "POST",
        "/camera-stations/{camera_id}/time-offset",
        json={"offset_seconds": 60, "reason": "reloj"},
    ),
    _c("GET", "/camera-stations/{camera_id}/stats"),
    _c("POST", "/classification-batches/{batch_id}/files", files=True),
    _c("GET", "/classification-batches/{batch_id}"),
    _c("POST", "/classification-batches/{batch_id}/cancel"),
    _c("DELETE", "/classification-batches/{batch_id}/items/{client_index}"),
    _c("POST", "/classification-batches/{batch_id}/items/{client_index}/retry"),
    _c("POST", "/classification-batches/{batch_id}/complete"),
    _c("GET", "/classifications/{classification_id}"),
    _c("PATCH", "/classifications/{classification_id}", json={"camera_station_id": "{own_camera}"}),
    _c("DELETE", "/classifications/{classification_id}"),
    _c("PUT", "/classifications/{classification_id}/validation", json={"action": "confirm"}),
    _c("GET", "/classifications/{classification_id}/evidence"),
    _c("POST", "/imports/{import_id}/confirm", json={}, expected={401, 404}),
    _c("GET", "/imports/{import_id}", expected={401, 404}),
    _c("DELETE", "/imports/{import_id}", expected={401, 404}),
    _c("GET", "/projects/{project_id}"),
    _c("PATCH", "/projects/{project_id}", json={"name": "x"}, if_match=True),
    _c("DELETE", "/projects/{project_id}"),
    _c(
        "POST", "/projects/{project_id}/camera-stations", json={"camera_station_id": "{own_camera}"}
    ),
    _c("DELETE", "/projects/{project_id}/camera-stations/{camera_station_id}"),
    _c("GET", "/projects/{project_id}/stats"),
    _c("GET", "/admin/classifications/{classification_id}/evidence", expected=ADMIN_ONLY),
    _c("POST", "/admin/{entity}/{entity_id}/restore", json=REASON, expected=ADMIN_ONLY),
    _c("POST", "/admin/{entity}/{entity_id}/delete", json=REASON, expected=ADMIN_ONLY),
    _c("POST", "/admin/users/{user_id}/deactivate", json=REASON, expected=ADMIN_ONLY),
    _c("POST", "/admin/users/{user_id}/reactivate", json=REASON, expected=ADMIN_ONLY),
    _c("POST", "/admin/users/{user_id}/password-reset-link", json=REASON, expected=ADMIN_ONLY),
]
# Filtros por id en query: un id privado ajeno no puede devolver datos.
# Los lotes solo listan los del propio dueño, así que un filtro ajeno da una lista vacía.
QUERY_SCOPED = [
    ("/classifications?camera_station_id={camera_id}", {404}),
    ("/classifications?project_id={project_id}", {404}),
    ("/classification-batches?camera_station_id={camera_id}", {200}),
    ("/classifications/burst-candidates?camera_station_id={camera_id}", {404}),
    ("/reports/excel?camera_station_id={camera_id}", {404}),
    ("/reports/pdf?project_id={project_id}", {404}),
]


def test_matrix_covers_every_route() -> None:
    routes = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and "{" in route.path
        for method in route.methods
    }
    covered = {(case.method, case.path) for case in MATRIX}
    missing = routes - covered - {("GET", p) for p in PUBLIC}
    assert not missing, f"Rutas sin prueba IDOR: {sorted(missing)}"
    assert not covered - routes, f"Casos de rutas que ya no existen: {sorted(covered - routes)}"


async def _victim(
    c: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession]
) -> dict[str, str]:
    ana = await register_user(c, "ana@example.com")
    h = bearer(ana)
    camera = await _camera(c, h, "ANA-PRIV")
    project = await c.post(f"{V1}/projects", json={"name": "Privado de Ana"}, headers=h)
    project_id = str(project.json()["data"]["id"])
    link = await c.post(
        f"{V1}/projects/{project_id}/camera-stations", json={"camera_station_id": camera}, headers=h
    )
    assert link.status_code in (200, 201), link.text
    row = await _row(
        factory,
        camera,
        ana["user"]["id"],
        evidence_key="evidence/2026/11/a.jpg",
        **_taxon("Panthera onca"),
    )
    batch = await _batch(c, h, camera)
    imported = await _upload(c, h, _pkg("sample_valid"), camera_station_id=camera)
    assert imported.status_code == 201, imported.text
    return {
        "camera_id": camera,
        "camera_station_id": camera,
        "project_id": project_id,
        "classification_id": str(row),
        "entity": "classifications",
        "entity_id": str(row),
        "batch_id": batch,
        "client_index": "0",
        "import_id": str(imported.json()["data"]["import_id"]),
        "user_id": str(ana["user"]["id"]),
    }


async def _attackers(c: httpx.AsyncClient) -> dict[str, tuple[dict[str, str], str]]:
    beto = bearer(await register_user(c, "beto@example.com"))
    anon = await c.post(f"{V1}/anon-sessions")
    anon_h = {"X-Anon-Token": anon.json()["data"]["anon_token"]}
    return {
        "user": (beto, await _camera(c, beto, "BETO-1")),
        "anonymous": (anon_h, await _camera(c, anon_h, "ANON-1")),
    }


def _fill(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {k: _fill(v, ids) for k, v in value.items()}
    return value


@pytest.mark.parametrize("who", ["user", "anonymous"])
async def test_foreign_private_resources_are_invisible_and_untouched(
    who: str, db_session_factory: async_sessionmaker[AsyncSession], queue: FakeQueue
) -> None:
    async with make_client() as c:
        ids = await _victim(c, db_session_factory)
        headers, own_camera = (await _attackers(c))[who]
        values = {**ids, "own_camera": own_camera}
        failures = []
        for case in MATRIX:
            url = case.path.format(**values)
            extra = {"If-Match": '"1"'} if case.if_match else {}
            kwargs: dict[str, Any] = {"headers": {**headers, **extra}}
            if case.files:
                kwargs["files"] = {"file": ("a.jpg", _jpeg(1), "image/jpeg")}
                kwargs["data"] = {"client_index": "0"}
            elif case.json is not None:
                kwargs["json"] = _fill(case.json, values)
            resp = await c.request(case.method, url, **kwargs)
            if resp.status_code not in case.expected:
                failures.append(f"{case.method} {case.path} → {resp.status_code} {resp.text[:120]}")
        for template, expected in QUERY_SCOPED:
            resp = await c.get(V1 + template.format(**values), headers=headers)
            leaked = resp.status_code == 200 and resp.json()["data"]
            if resp.status_code not in expected or leaked:
                failures.append(f"GET {template} → {resp.status_code} {resp.text[:120]}")
        assert not failures, "\n".join(failures)

    async with db_session_factory() as s:  # nada de Ana cambió
        camera = await s.get(CameraStation, uuid.UUID(ids["camera_id"]))
        project = await s.get(Project, uuid.UUID(ids["project_id"]))
        row = await s.scalar(
            select(Classification).where(Classification.id == uuid.UUID(ids["classification_id"]))
        )
    assert camera is not None and not camera.is_deleted and camera.name != "x"
    assert project is not None and not project.is_deleted and project.name == "Privado de Ana"
    assert (
        row is not None
        and not row.is_deleted
        and row.validation_status == ValidationStatus.UNVALIDATED
    )
    assert row.camera_station_id == uuid.UUID(ids["camera_id"])
