"""Logs JSON en una línea con ``request_id``, ``flow`` y ``step`` del contexto (ESTANDARES §7)."""

import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.errors import AppError

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
flow_var: ContextVar[str | None] = ContextVar("flow", default=None)
step_var: ContextVar[str | None] = ContextVar("step", default=None)

logger = logging.getLogger("app")

_SENSITIVE = (
    "password",
    "token",
    "authorization",
    "secret",
    "api_key",
    "x_api_key",
    "database_url",
    "image_base64",
)
# Atributos propios de LogRecord (y el color_message de uvicorn) no se copian como contexto.
_RECORD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "color_message",
}


def mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def _safe(key: str, value: Any) -> Any:
    lowered = key.lower().replace("-", "_")
    if any(word in lowered for word in _SENSITIVE):
        return "***"
    if "email" in lowered and isinstance(value, str):
        return mask_email(value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": "backend",
            "env": settings.ENVIRONMENT.value,
            "version": settings.APP_VERSION,
            "request_id": request_id_var.get(),
            "flow": flow_var.get(),
            "step": step_var.get(),
            "event": getattr(record, "event", record.name),
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RECORD_ATTRS and key not in entry:
                entry[key] = _safe(key, value)
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        entry["ts"] = entry["ts"].replace("+00:00", "Z")
        return json.dumps(
            {k: v for k, v in entry.items() if v is not None}, ensure_ascii=False, default=str
        )


def configure_logging() -> None:
    """Un único handler JSON a stdout; uvicorn se registra por el mismo canal."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # El access log lo escribe RequestContextMiddleware (http.request), sin duplicar.
    logging.getLogger("uvicorn.access").disabled = True


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


@contextmanager
def log_step(step: str, **context: Any) -> Iterator[None]:
    """Fija ``step``, mide ``duration_ms`` y registra ``<step>.succeeded`` o ``<step>.failed``."""
    token = step_var.set(step)
    started = time.perf_counter()
    try:
        yield
    except AppError as exc:
        extra = {**context, **exc.context, "error_code": exc.code}
        extra |= {"event": f"{step}.failed", "duration_ms": _elapsed_ms(started)}
        logger.log(exc.log_level, exc.message, extra=extra)
        raise
    else:
        extra = {**context, "event": f"{step}.succeeded", "duration_ms": _elapsed_ms(started)}
        logger.info(step, extra=extra)
    finally:
        step_var.reset(token)


def flow(name: str) -> Callable[[], Awaitable[None]]:
    """Dependencia de router: ``Depends(flow("FL-05"))`` fija el flujo para logs y errores."""

    async def set_flow() -> None:  # async: corre en el contexto de la petición, no en un hilo
        flow_var.set(name)

    return set_flow
