"""Proceso worker (HU-11): ``arq app.worker.main.WorkerSettings``.

Corre el job ``process_next`` (un archivo por aviso) y los crons de mantenimiento:
reaper FL-33 (cada 5 min), cleanup FL-31 (cada hora y al arrancar) y purga anónima FL-30 (cada
hora).
"""

from dataclasses import asdict
from typing import Any, ClassVar

import httpx
from arq import cron, func
from arq.connections import RedisSettings

from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.db.session import engine
from app.integrations.queue import ArqTaskQueue
from app.integrations.storage.local import LocalStorage
from app.worker import cron_jobs
from app.worker.classify_file_job import process_next
from app.worker.cron_anon import purge_anon_sessions
from app.worker.import_job import import_package


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging()
    ctx["storage"] = LocalStorage(settings.STORAGE_LOCAL_PATH)
    ctx["http"] = httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS)
    ctx["queue"] = ArqTaskQueue()
    summary = await cron_jobs.cleanup(ctx["storage"])  # FL-31 también al arrancar
    logger.info("Worker listo", extra={"event": "worker.started", **cron_jobs.vars_of(summary)})


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["http"].aclose()
    await ctx["queue"].close()
    await engine.dispose()


async def run_reaper(ctx: dict[str, Any]) -> dict[str, int]:
    return cron_jobs.vars_of(await cron_jobs.reaper(ctx["queue"]))


async def run_cleanup(ctx: dict[str, Any]) -> dict[str, int]:
    return cron_jobs.vars_of(await cron_jobs.cleanup(ctx["storage"]))


async def run_purge_anon(ctx: dict[str, Any]) -> dict[str, int]:
    summary = await purge_anon_sessions(storage=ctx["storage"])
    return asdict(summary)


class WorkerSettings:
    # keep_result=0: si arq guardara el resultado, ignoraría avisos nuevos con el mismo _job_id.
    functions: ClassVar[list[Any]] = [
        func(process_next, keep_result=0),
        func(import_package, keep_result=0),
    ]
    cron_jobs: ClassVar[list[Any]] = [
        cron(run_reaper, minute=set(range(0, 60, 5)), keep_result=0),
        cron(run_cleanup, minute={7}, keep_result=0),
        cron(run_purge_anon, minute={37}, keep_result=0),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = settings.WORKER_CONCURRENCY
    health_check_interval = 30  # HU-15b: /admin/queue sabe si hay un worker vivo
    job_timeout = settings.AI_TIMEOUT_SECONDS + 120  # la IA + reintentos (5 s y 30 s)
