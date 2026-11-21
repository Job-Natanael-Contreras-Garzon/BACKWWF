"""HU-16: semilla E2E y scripts de respaldo FL-32 (la restauración real se prueba con PostgreSQL
en la bitácora; acá, sintaxis y que la contraseña nunca salga a la línea de comandos)."""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.enums import EnvironmentMode
from app.core.errors import ForbiddenError
from app.db.uow import UnitOfWork
from app.integrations.storage.local import LocalStorage
from app.models import Classification
from app.models.user import User
from app.services import seed_e2e
from tests.conftest import make_client, requires_db

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


@pytest.mark.parametrize("name", ["backup.sh", "restore_test.sh", "_pgenv.sh"])
def test_backup_scripts_are_valid_bash(name: str) -> None:
    subprocess.run(["bash", "-n", str(SCRIPTS / name)], check=True)  # noqa: S603, S607


def test_pgenv_turns_sqlalchemy_url_into_pg_vars_without_argv() -> None:
    script = (
        f"source {SCRIPTS / '_pgenv.sh'}; "
        "pgenv 'postgresql+asyncpg://wwf:p%40ss@db.example.com:25060/fauna?ssl=require'; "
        'echo "$PGHOST|$PGPORT|$PGUSER|$PGPASSWORD|$PGDATABASE|$PGSSLMODE"'
    )
    out = subprocess.run(  # noqa: S603
        ["bash", "-c", script],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert out == "db.example.com|25060|wwf|p@ss|fauna|require"


@requires_db
async def test_seed_e2e_is_deterministic_idempotent_and_never_in_production(
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = LocalStorage(tmp_path / "evidence")
    async with UnitOfWork(db_session_factory) as uow:
        first = await seed_e2e.seed(uow, storage, "E2e-Password1")
    async with UnitOfWork(db_session_factory) as uow:
        again = await seed_e2e.seed(uow, storage, "E2e-Password1")
    assert first.status == "seeded" and again.status == "already_seeded"
    assert (first.users, first.camera_stations, first.classifications) == (3, 2, 30)
    async with db_session_factory() as s:
        assert await s.scalar(select(func.count()).select_from(User)) == 3
        rows = (await s.scalars(select(Classification))).all()
    with_frames = [r for r in rows if r.evidence_key]
    assert len(with_frames) == 26
    for r in with_frames:
        assert await storage.exists(r.evidence_key or "")

    async with make_client() as c:  # las cuentas sirven para entrar
        login = await c.post(
            "/api/v1/auth/login",
            json={"email": seed_e2e.ADMIN_EMAIL, "password": "E2e-Password1"},
        )
        assert login.status_code == 200, login.text

    monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentMode.PRODUCTION)
    async with UnitOfWork(db_session_factory) as uow:
        with pytest.raises(ForbiddenError):
            await seed_e2e.seed(uow, storage, "E2e-Password1")
