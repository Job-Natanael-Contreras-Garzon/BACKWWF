from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.db.session import engine
from app.models.base import Base
from app.schemas.response_wrapper import StandardResponse
import app.models

# Routers
from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.projects import router as projects_router
from app.api.v1.camera_stations import router as stations_router
from app.api.v1.media_files import router as media_files_router
from app.api.v1.videos import router as videos_router
from app.api.v1.species import router as species_router
from app.api.v1.individuals import router as individuals_router
from app.api.v1.reports import router as reports_router
from app.api.v1.ai_router import router as ai_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API de Monitoreo de Fauna con Cámaras Trampa, Autenticación JWT, Ingesta Multimedia, Análisis IA y Resúmenes Taxonómicos.",
    version="4.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)

# ─────────────────────────────────────────────
#  Esquema OpenAPI Personalizado (Authorize Bearer)
# ─────────────────────────────────────────────
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Ingrese el token JWT de acceso obtenido en /auth/login o /auth/register",
        }
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# ─────────────────────────────────────────────
#  Exception Handlers Globales
# ─────────────────────────────────────────────
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "data": None, "message": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = errors[0]["msg"] if errors else "Error de validación en la petición"
    loc = " -> ".join([str(l) for l in errors[0].get("loc", [])]) if errors else ""
    full_message = f"Validación fallida ({loc}): {msg}" if loc else f"Validación fallida: {msg}"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"status": "error", "data": None, "message": full_message},
    )


import logging

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.getLogger(__name__).exception("Unhandled internal error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "data": None, "message": "Error interno del servidor (INTERNAL_ERROR)."},
    )


# ─────────────────────────────────────────────
#  CORS
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Anon-Session-ID"],
    max_age=600,
)

# ─────────────────────────────────────────────
#  Endpoints de Salud y Metadatos Raíz
# ─────────────────────────────────────────────
@app.get(
    "/",
    response_model=StandardResponse,
    tags=["System"],
    summary="Información y estado del servicio",
)
async def root():
    return StandardResponse(
        status="success",
        data={
            "app_name": settings.PROJECT_NAME,
            "version": "4.0.0",
            "environment": settings.ENVIRONMENT,
            "docs_url": "/docs",
            "redoc_url": "/redoc",
        },
        message="Backend de Monitoreo de Fauna WWF operativo.",
    )


@app.get(
    "/health",
    response_model=StandardResponse,
    tags=["System"],
    summary="Healthcheck del sistema y base de datos",
)
async def health_check():
    db_status = "connected"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    is_healthy = db_status == "connected"
    return StandardResponse(
        status="success" if is_healthy else "degraded",
        data={
            "status": "healthy" if is_healthy else "unhealthy",
            "database": db_status,
            "version": "4.0.0",
        },
        message="Chequeo de salud del sistema completado con éxito." if is_healthy else "Servicio con incidencias en base de datos.",
    )


# ─────────────────────────────────────────────
#  Routers
# ─────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(projects_router)
app.include_router(stations_router)
app.include_router(media_files_router)
app.include_router(videos_router)
app.include_router(species_router)
app.include_router(individuals_router)
app.include_router(reports_router)
app.include_router(ai_router)
