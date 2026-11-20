from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import models  # noqa: F401  (registra los modelos en el metadata de SQLAlchemy)
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, logger
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.responses import ApiResponse, error_response, ok
from app.db.session import engine

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "API de Monitoreo de Fauna con Cámaras Trampa, Autenticación JWT, Ingesta Multimedia, "
        "Análisis IA y Resúmenes Taxonómicos."
    ),
    version="4.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title, version=app.version, description=app.description, routes=app.routes
    )
    openapi_schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Token JWT de /api/v1/auth/login o /api/v1/auth/register",
        }
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]  # OpenAPI con BearerAuth


# ─────────────────────────────────────────────
#  Handlers globales (ESTANDARES §5.2): un solo lugar
# ─────────────────────────────────────────────
# Traduce HTTPException nativas de FastAPI/Starlette fuera del flujo AppError.
_HTTP_CODES = {
    400: "VALIDATION_ERROR",
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    405: "METHOD_NOT_ALLOWED",
    413: "MEDIA_TOO_LARGE",
    422: "VALIDATION_ERROR",
}


def register_exception_handlers(target: FastAPI) -> None:
    @target.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        extra = {**exc.context, "event": "http.request.failed", "error_code": exc.code}
        logger.log(exc.log_level, exc.message, extra=extra)
        return error_response(exc.http_status, exc.code, exc.message, exc.details)

    @target.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404 and exc.detail == "Not Found":
            return error_response(404, "ROUTE_NOT_FOUND", "La ruta solicitada no existe.")
        if exc.status_code == 405:
            return error_response(405, "METHOD_NOT_ALLOWED", "Método no permitido para esta ruta.")
        fallback = "NOT_FOUND" if exc.status_code == 404 else "INTERNAL_ERROR"
        code = _HTTP_CODES.get(exc.status_code, fallback)
        return error_response(exc.status_code, code, str(exc.detail))

    @target.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Sin el valor recibido: podría ser una contraseña.
        details = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ())),
                "code": error.get("type"),
                "message": error.get("msg"),
            }
            for error in exc.errors()
        ]
        return error_response(
            422, "VALIDATION_ERROR", "Hay datos inválidos en la petición.", details
        )

    @target.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error(
            "Error de base de datos", exc_info=exc, extra={"event": "http.request.db_error"}
        )
        message = "No se pudo completar la operación. Intenta de nuevo."
        return error_response(500, "DATABASE_ERROR", message)

    @target.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Excepción no controlada", exc_info=exc, extra={"event": "http.request.unhandled"}
        )
        return error_response(
            500, "INTERNAL_ERROR", "Ocurrió un error inesperado. Intenta de nuevo."
        )


register_exception_handlers(app)

# Orden: el último agregado es el más externo. RequestContext envuelve a todo lo demás.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Anon-Session-ID", "X-Request-ID"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)


# ─────────────────────────────────────────────
#  Sistema
# ─────────────────────────────────────────────
@app.get("/", response_model=ApiResponse[dict[str, str]], tags=["System"])
async def root() -> ApiResponse[dict[str, str]]:
    return ok(
        {
            "app_name": settings.PROJECT_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT.value,
            "docs_url": "/docs",
        },
        message="Backend de Monitoreo de Fauna WWF operativo.",
    )


app.include_router(api_router)
