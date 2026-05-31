from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uuid # 👈 Importación que faltaba y causaba el error

from app.db.session import engine
from app.models.base import Base
import app.models

# Routers
from app.api.v1.users import router as users_router
from app.api.v1.projects import router as projects_router
from app.api.v1.camera_stations import router as stations_router
from app.api.v1.videos import router as videos_router
from app.api.v1.species import router as species_router
from app.api.v1.individuals import router as individuals_router
from app.api.v1.reports import router as reports_router
from app.api.v1.ai_router import router as ai_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Fauna Monitoring API",
    description="Backend completo con manejo de multimedia (Subida de videos) y metadatos.",
    version="4.0.0",
    lifespan=lifespan,
)

# ─────────────────────────────────────────────
#  CORS
#  En producción: define ALLOWED_ORIGINS en las variables de entorno
#  como una lista separada por comas, por ejemplo:
#    ALLOWED_ORIGINS=https://mi-frontend.com,https://app.mi-dominio.com
#  Si no se define, permite todos los orígenes (útil en desarrollo).
# ─────────────────────────────────────────────
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")

if _raw_origins.strip() == "*":
    allowed_origins = ["*"]
else:
    allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,   # Necesario para cookies / auth headers
    allow_methods=["*"],      # GET, POST, PUT, PATCH, DELETE, OPTIONS
    allow_headers=["*"],      # Authorization, Content-Type, etc.
    expose_headers=["Content-Disposition"],  # Útil si sirves descargas de archivos
    max_age=600,              # Cachea el preflight 10 minutos
)

# ─────────────────────────────────────────────
#  Routers
# ─────────────────────────────────────────────
app.include_router(users_router)
app.include_router(projects_router)
app.include_router(stations_router)
app.include_router(videos_router)
app.include_router(species_router)
app.include_router(individuals_router)
app.include_router(reports_router)
app.include_router(ai_router)

