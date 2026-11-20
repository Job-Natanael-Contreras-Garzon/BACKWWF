"""Middlewares ASGI: contexto de la petición + access log, y cabeceras de seguridad.

Son ASGI puros (no ``BaseHTTPMiddleware``) para que las ``ContextVar`` que fijan lleguen
intactas a los handlers de error.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.enums import EnvironmentMode
from app.core.logging import flow_var, request_id_var, step_var

logger = logging.getLogger("app.http")

# Un X-Request-ID ajeno solo se acepta si es corto y sin caracteres raros (evita inyección en logs).
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex[:12]
        request_id_var.set(request_id)
        flow_var.set(None)
        step_var.set(None)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            route = getattr(scope.get("route"), "path", scope["path"])
            logger.info(
                "%s %s %s",
                scope["method"],
                route,
                status_code,
                extra={
                    "event": "http.request",
                    "method": scope["method"],
                    "route": route,
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.headers = dict(_SECURITY_HEADERS)
        if settings.ENVIRONMENT == EnvironmentMode.PRODUCTION:
            self.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.headers.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)
