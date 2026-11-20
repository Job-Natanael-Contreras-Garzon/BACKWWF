import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import UoWDep
from app.core.config import settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import flow_var, logger
from app.core.responses import ApiResponse, ErrorBody, current_meta, ok
from app.db.uow import UnitOfWork

router = APIRouter(prefix="/health", tags=["System"])


async def get_health_http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=3.0) as client:
        yield client


HealthHttpClientDep = Annotated[httpx.AsyncClient, Depends(get_health_http_client)]


def _probe_storage(base_path: str) -> str:
    root = Path(base_path)
    root.mkdir(parents=True, exist_ok=True)
    probe = root / f".healthcheck-{uuid.uuid4().hex}.tmp"
    probe.write_bytes(b"ok")
    probe.unlink(missing_ok=True)
    return "ok"


async def _check_database(uow: UnitOfWork) -> str:
    try:
        await uow.session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning(
            "health.ready.database_down",
            extra={"event": "health.ready.database_down", "error_type": type(exc).__name__},
        )
        return "down"
    return "ok"


async def _check_storage() -> str:
    try:
        return await asyncio.to_thread(_probe_storage, settings.STORAGE_LOCAL_PATH)
    except OSError as exc:
        logger.warning(
            "health.ready.storage_down",
            extra={"event": "health.ready.storage_down", "error_type": type(exc).__name__},
        )
        return "down"


async def _check_ai(client: httpx.AsyncClient) -> str:
    base_url = settings.AI_SERVICE_URL.strip().rstrip("/")
    if not base_url:
        return "down"
    try:
        response = await client.get(f"{base_url}/api/v1/health")
        if response.status_code == status.HTTP_200_OK:
            payload: Any = response.json()
            if isinstance(payload, dict) and payload.get("status") == "ok":
                return "ok"
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "health.ready.ai_down",
            extra={"event": "health.ready.ai_down", "error_type": type(exc).__name__},
        )
    return "down"


@router.get("", response_model=ApiResponse[dict[str, str]])
async def health_check() -> ApiResponse[dict[str, str]]:
    """Liveness para Docker y plataformas PaaS."""
    return ok({"status": "ok", "version": settings.APP_VERSION})


@router.get("/ready", response_model=ApiResponse[dict[str, str]])
async def readiness_check(
    uow: UoWDep,
    http_client: HealthHttpClientDep,
) -> ApiResponse[dict[str, str]] | JSONResponse:
    db_status = await _check_database(uow)
    storage_status, ai_status = await asyncio.gather(
        _check_storage(),
        _check_ai(http_client),
    )
    statuses = {"database": db_status, "ai": ai_status, "storage": storage_status}
    if all(value == "ok" for value in statuses.values()):
        return ok(statuses, message="Servicio listo.")

    err = ServiceUnavailableError("SERVICE_UNAVAILABLE")
    body = ApiResponse[dict[str, str]](
        status="error",
        data=statuses,
        message=err.message,
        error=ErrorBody(code=err.code, flow=flow_var.get(), details=[]),
        meta=current_meta(),
    )
    return JSONResponse(
        status_code=err.http_status,
        content=body.model_dump(mode="json"),
        headers={"X-Request-ID": body.meta.request_id},
    )
