import argparse
import asyncio
import getpass
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime

from app.core.config import settings
from app.core.enums import UserRole
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.security import get_password_hash
from app.db.session import engine
from app.db.uow import UnitOfWork
from app.integrations.queue import ArqTaskQueue
from app.integrations.storage.local import LocalStorage
from app.models.user import User
from app.services import catalog_service, seed_e2e
from app.services.auth_service import validate_password_strength
from app.worker import cron_jobs
from app.worker.cron_anon import purge_anon_sessions


async def _run_purge_anon() -> dict[str, int]:
    try:
        summary = await purge_anon_sessions()
        return asdict(summary)
    finally:
        await engine.dispose()


async def _run_reaper() -> dict[str, int]:
    queue = ArqTaskQueue()
    try:
        return cron_jobs.vars_of(await cron_jobs.reaper(queue))
    finally:
        await queue.close()
        await engine.dispose()


async def _run_cleanup() -> dict[str, int]:
    try:
        return cron_jobs.vars_of(await cron_jobs.cleanup(LocalStorage(settings.STORAGE_LOCAL_PATH)))
    finally:
        await engine.dispose()


async def _run_sync_catalog() -> dict[str, int]:
    return {"updated": int(await catalog_service.sync_from_ai() == "updated")}


ADMIN_PASSWORD_ENV = "WWF_ADMIN_PASSWORD"  # noqa: S105 — nombre de la variable, no su valor


def _read_password() -> str:
    """La contraseña llega por variable de entorno o por getpass; nunca por argv ni se imprime."""
    password = os.environ.get(ADMIN_PASSWORD_ENV)
    if password:
        return password
    first = getpass.getpass("Contraseña nueva: ")
    if first != getpass.getpass("Repite la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden.")
    return first


async def _run_create_admin(email: str, full_name: str) -> dict[str, str]:
    """CB-99: crea el admin único (o asciende una cuenta existente sin tocar su contraseña)."""
    normalized = email.strip().lower()
    try:
        async with UnitOfWork() as uow:
            user = await uow.users.get_by_email(normalized)
            if user is not None:
                user.role, user.is_active = UserRole.ADMIN, True
                await uow.commit()
                return {"result": "promoted", "user_id": str(user.id)}
            password = _read_password()
            validate_password_strength(password)
            user = uow.users.add(
                User(
                    email=normalized,
                    password_hash=get_password_hash(password),
                    full_name=full_name,
                    role=UserRole.ADMIN,
                    is_active=True,
                )
            )
            await uow.commit()
            return {"result": "created", "user_id": str(user.id)}
    finally:
        await engine.dispose()


async def _run_reset_admin_password(email: str) -> dict[str, str]:
    """CB-99: única forma de recuperar al admin sin correo. Revoca todas sus sesiones."""
    normalized = email.strip().lower()
    try:
        async with UnitOfWork() as uow:
            user = await uow.users.get_by_email(normalized)
            if user is None or user.role != UserRole.ADMIN:
                raise SystemExit("No existe un admin con ese correo.")
            password = _read_password()
            validate_password_strength(password)
            user.password_hash = get_password_hash(password)
            user.is_active = True
            await uow.refresh_tokens.revoke_all_for_user(user.id, datetime.now(UTC))
            await uow.commit()
            return {"result": "password_reset", "user_id": str(user.id)}
    finally:
        await engine.dispose()


E2E_PASSWORD_ENV = "WWF_E2E_PASSWORD"  # noqa: S105 — nombre de la variable, no su valor


async def _run_seed_e2e() -> dict[str, object]:
    """HU-16: datos fijos para Playwright. La contraseña de las cuentas sale de WWF_E2E_PASSWORD."""
    password = os.environ.get(E2E_PASSWORD_ENV, "")
    if not password:
        raise SystemExit(f"Define {E2E_PASSWORD_ENV} con la contraseña de las cuentas E2E.")
    validate_password_strength(password)
    try:
        async with UnitOfWork() as uow:
            result = await seed_e2e.seed(uow, LocalStorage(settings.STORAGE_LOCAL_PATH), password)
            return asdict(result)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("purge-anon", help="Ejecuta la purga FL-30 de sesiones anónimas.")
    subparsers.add_parser("reaper", help="Ejecuta el reaper FL-33 de la cola.")
    subparsers.add_parser("cleanup", help="Ejecuta la limpieza FL-31 de temporales y huérfanos.")
    subparsers.add_parser("sync-catalog", help="Actualiza el catálogo SpeciesNet desde la IA.")
    create = subparsers.add_parser(
        "create-admin", help=f"Crea o asciende al admin (contraseña por {ADMIN_PASSWORD_ENV})."
    )
    create.add_argument("--email", required=True)
    create.add_argument("--full-name", default="Administrador WWF")
    reset = subparsers.add_parser(
        "reset-admin-password", help="Fija una contraseña nueva al admin y revoca sus sesiones."
    )
    reset.add_argument("--email", required=True)
    subparsers.add_parser(
        "seed-e2e", help=f"Carga datos fijos para E2E (no en producción; {E2E_PASSWORD_ENV})."
    )

    args = parser.parse_args(argv)
    admin_result: dict[str, object] | None
    try:
        if args.command == "create-admin":
            admin_result = dict(asyncio.run(_run_create_admin(args.email, args.full_name)))
        elif args.command == "reset-admin-password":
            admin_result = dict(asyncio.run(_run_reset_admin_password(args.email)))
        elif args.command == "seed-e2e":
            admin_result = asyncio.run(_run_seed_e2e())
        else:
            admin_result = None
    except AppError as exc:  # p. ej. AUTH_WEAK_PASSWORD: se informa sin traza
        sys.stderr.write(f"{exc.code}: {exc.message}\n")
        return 2
    if admin_result is not None:
        sys.stdout.write(json.dumps(admin_result) + "\n")
        return 0
    runners = {
        "purge-anon": _run_purge_anon,
        "reaper": _run_reaper,
        "cleanup": _run_cleanup,
        "sync-catalog": _run_sync_catalog,
    }
    result = asyncio.run(runners[args.command]())
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
