"""Pedidos del front (FE-51, FE-28 CA-8, FD J3/J10) contra el contrato del back.

1. Catálogo único de errores y ``GET /meta/error-codes`` (solo desarrollo).
2. ``must_change_password`` → ``403 PASSWORD_CHANGE_REQUIRED`` (BE-50, SEC-11).
3. ``Retry-After`` en todo 429 de límite de intentos, y expuesto en CORS.
4. ``GET /admin/classifications`` con los filtros de §8.1 (API §13.3).
"""

import ast
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.cors import CORSMiddleware

from app.core import errors
from app.core.config import settings
from app.core.enums import Category, EnvironmentMode, Rank, ValidationStatus
from app.core.error_catalog import BY_CODE, CATALOG
from app.main import app
from app.models import Classification
from app.models.user import User
from app.services.catalog_service import get_catalog
from tests.conftest import bearer, make_client, register_user, requires_db
from tests.test_hu07_projects import _camera, _project
from tests.test_hu13_catalog_stats import _row, _taxon
from tests.test_hu15a_admin_panel import _admin

APP = Path(__file__).resolve().parents[1] / "app"
A = "/api/v1/admin"
# Constantes en MAYÚSCULAS que no son códigos de error (variables de entorno, CLI).
NOT_CODES = {"SECRET_KEY", "REFRESH_SECRET_KEY", "WWF_ADMIN_PASSWORD", "WWF_E2E_PASSWORD"}


# --- 1. Catálogo de errores ------------------------------------------------------------------


def _python_files() -> list[Path]:
    return [p for p in APP.rglob("*.py") if "ia_contract" not in p.parts]


def test_every_code_the_back_uses_is_in_the_catalog() -> None:
    """Toda constante tipo CÓDIGO en app/ (salvo los IA_* internos) está en el catálogo."""
    literal = re.compile(r"""["']([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)["']""")
    used = {
        code
        for path in _python_files()
        for code in literal.findall(path.read_text(encoding="utf-8"))
        if not code.startswith("IA_") and code not in NOT_CODES
    }
    missing = sorted(used - set(BY_CODE) - {"FORBIDDEN"})
    assert not missing, f"Códigos usados en app/ que faltan en error_catalog.py: {missing}"
    assert len(CATALOG) == len(BY_CODE), "código repetido en el catálogo"


def test_raised_errors_use_the_catalog_http_status() -> None:
    """``XxxError("CODIGO", …)``: el HTTP de la clase coincide con el del catálogo (STD §6.1)."""
    classes = {
        name: cls
        for name, cls in vars(errors).items()
        if isinstance(cls, type) and issubclass(cls, errors.AppError)
    }
    mismatches = []
    for path in _python_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            cls = classes.get(node.func.id)
            first = node.args[0] if node.args else None
            if (
                cls is None
                or not isinstance(first, ast.Constant)
                or not isinstance(first.value, str)
            ):
                continue
            spec = BY_CODE.get(first.value)
            assert spec is not None, f"{path.name}: {first.value} no está en el catálogo"
            allowed = (spec.http_status, *spec.also_http)
            if spec.kind == "error" and cls.http_status not in allowed:
                mismatches.append(f"{path.name}: {first.value} {cls.http_status} ∉ {allowed}")
    assert not mismatches, mismatches


async def test_meta_error_codes_only_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    async with make_client() as c:
        monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentMode.DEVELOPMENT)
        resp = await c.get("/api/v1/meta/error-codes")
        assert resp.status_code == 200
        codes = {e["code"]: e for e in resp.json()["data"]}
        assert codes["SERVICE_UNAVAILABLE"]["http_status"] == 503
        assert codes["PASSWORD_CHANGE_REQUIRED"]["http_status"] == 403
        assert codes["CAMERA_DELETED"]["kind"] == "item"
        assert codes["VIDEO_TRUNCATED"]["kind"] == "warning"

        monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentMode.PRODUCTION)
        hidden = await c.get("/api/v1/meta/error-codes")
        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "ROUTE_NOT_FOUND"


# --- 3. Retry-After -----------------------------------------------------------------------------


def test_cors_exposes_retry_after_and_not_the_old_anon_header() -> None:
    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    exposed = cors.kwargs["expose_headers"]
    assert "Retry-After" in exposed and "X-Request-ID" in exposed
    assert "X-Anon-Session-ID" not in exposed  # nombre viejo: el header real es X-Anon-Token


@requires_db
async def test_429_carries_retry_after_seconds(
    db_session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ANON_SESSION_RATE_LIMIT_PER_HOUR", 2)
    async with make_client(ip="198.51.100.77") as c:
        for _ in range(2):
            assert (await c.post("/api/v1/anon-sessions")).status_code == 201
        blocked = await c.post("/api/v1/anon-sessions")
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "RATE_LIMITED"
        assert 3500 <= int(blocked.headers["Retry-After"]) <= 3600  # ventana de 1 h

        for i in range(10):  # login: 10 por minuto por IP
            await c.post(
                "/api/v1/auth/login", json={"email": f"x{i}@example.com", "password": "Password1"}
            )
        login = await c.post(
            "/api/v1/auth/login", json={"email": "y@example.com", "password": "Password1"}
        )
        assert login.status_code == 429
        assert 1 <= int(login.headers["Retry-After"]) <= 60


# --- 2. Cambio obligatorio de contraseña --------------------------------------------------------


@requires_db
async def test_must_change_password_blocks_everything_but_the_change(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        session = await register_user(c, "nuevo.admin@example.com", "Temporal-123456")
        async with db_session_factory() as s:
            await s.execute(
                update(User)
                .where(User.email == "nuevo.admin@example.com")
                .values(role="admin", must_change_password=True)
            )
            await s.commit()
        login = await c.post(
            "/api/v1/auth/login",
            json={"email": "nuevo.admin@example.com", "password": "Temporal-123456"},
        )
        assert login.status_code == 200  # el login funciona: el front necesita el token
        assert login.json()["data"]["user"]["must_change_password"] is True
        h = bearer(login.json()["data"])

        me = await c.get("/api/v1/auth/me", headers=h)
        assert me.status_code == 200 and me.json()["data"]["must_change_password"] is True
        for path in ("/api/v1/camera-stations", f"{A}/stats"):  # Bearer y admin, bloqueados
            blocked = await c.get(path, headers=h)
            assert blocked.status_code == 403, path
            assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

        changed = await c.post(
            "/api/v1/auth/me/password",
            json={"current_password": "Temporal-123456", "new_password": "Definitiva-2026"},
            headers=h,
        )
        assert changed.status_code == 200, changed.text
        assert (await c.get(f"{A}/stats", headers=h)).status_code == 200
        me = await c.get("/api/v1/auth/me", headers=h)
        assert me.json()["data"]["must_change_password"] is False
        del session


# --- 4. Filtros de /admin/classifications --------------------------------------------------------


@requires_db
async def test_admin_classifications_accepts_section_8_1_filters(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with make_client() as c:
        admin = bearer(await _admin(c, db_session_factory))
        ana = await register_user(c, "ana@example.com")
        h, uid = bearer(ana), ana["user"]["id"]
        public, private = await _camera(c, h, "PUB", "public"), await _camera(c, h, "PRIV")
        puma, jaguar = _taxon("Puma concolor"), _taxon("Panthera onca")
        march = datetime(2026, 3, 10, 22, 0)
        p1 = await _row(db_session_factory, public, uid, captured_at=march, **puma)
        p2 = await _row(db_session_factory, public, uid, captured_at=datetime(2026, 5, 1), **jaguar)
        blank = await _row(db_session_factory, public, uid, category=Category.BLANK)
        p3 = await _row(db_session_factory, public, uid, captured_at=datetime(2026, 6, 1), **jaguar)
        await _row(db_session_factory, private, uid, **puma)  # nunca debe salir
        async with db_session_factory() as s:
            await s.execute(
                update(Classification)
                .where(Classification.id == p2)
                .values(
                    validation_status=ValidationStatus.CORRECTED_UNLISTED,
                    suggested_name="Leopardus jacobita",
                    validated_at=datetime.now(UTC),
                )
            )
            await s.commit()

        async def ids(query: str) -> set[uuid.UUID]:
            resp = await c.get(f"{A}/classifications?{query}", headers=admin)
            assert resp.status_code == 200, resp.text
            return {uuid.UUID(r["id"]) for r in resp.json()["data"]}

        assert await ids("") == {p1, p2, p3, blank}  # nada de la cámara privada
        assert await ids("category=blank") == {blank}
        assert await ids("category=animal,blank") == {p1, p2, p3, blank}
        assert await ids("validation_status=corrected_unlisted") == {p2}  # enlace de FD J10
        assert await ids(f"taxon={puma['label_id']}") == {p1}
        genus = get_catalog().search("Panthera", rank=Rank.GENUS, limit=1)[0].label_id
        # Taxón de cualquier nivel, sobre la taxonomía efectiva (CB-68): p2 dejó de ser Panthera
        # cuando una persona lo marcó como especie no catalogada.
        assert await ids(f"taxon={genus}") == {p3}
        assert await ids("from=2026-03-01&to=2026-03-31") == {p1, blank}  # _row: 10/03 por defecto
        assert await ids("from=2026-05-01") == {p2, p3}
        assert await ids("sort=-captured_at&status=all") >= {p1, p2}

        bad_taxon = await c.get(f"{A}/classifications?taxon=no-existe", headers=admin)
        assert bad_taxon.json()["error"]["code"] == "CATALOG_TAXON_NOT_FOUND"
        bad_dates = await c.get(f"{A}/classifications?from=2026-04-01&to=2026-03-01", headers=admin)
        assert bad_dates.status_code == 422
        assert bad_dates.json()["error"]["code"] == "VALIDATION_ERROR"
        bad_cat = await c.get(f"{A}/classifications?category=dragon", headers=admin)
        assert bad_cat.json()["error"]["code"] == "VALIDATION_ERROR"

        # project_id: el público filtra a sus cámaras visibles; el privado responde 404 (CB-96).
        pub = (await _project(c, h, "Público", visibility="public")).json()["data"]["id"]
        for camera in (public, private):
            link = f"/api/v1/projects/{pub}/camera-stations"
            await c.post(link, json={"camera_station_id": camera}, headers=h)
        assert await ids(f"project_id={pub}") == {p1, p2, p3, blank}
        hidden = (await _project(c, h, "Privado")).json()["data"]["id"]
        resp = await c.get(f"{A}/classifications?project_id={hidden}", headers=admin)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "PROJECT_NOT_FOUND"
