import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import engine
from app.integrations.queue import ArqTaskQueue
from app.integrations.storage.local import LocalStorage
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


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("purge-anon", help="Ejecuta la purga FL-30 de sesiones anónimas.")
    subparsers.add_parser("reaper", help="Ejecuta el reaper FL-33 de la cola.")
    subparsers.add_parser("cleanup", help="Ejecuta la limpieza FL-31 de temporales y huérfanos.")

    args = parser.parse_args(argv)
    runners = {"purge-anon": _run_purge_anon, "reaper": _run_reaper, "cleanup": _run_cleanup}
    result = asyncio.run(runners[args.command]())
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
