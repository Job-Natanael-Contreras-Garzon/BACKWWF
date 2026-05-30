from contextlib import asynccontextmanager
from fastapi import FastAPI
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
    lifespan=lifespan
)

app.include_router(users_router)
app.include_router(projects_router)
app.include_router(stations_router)
app.include_router(videos_router)
app.include_router(species_router)
app.include_router(individuals_router)
app.include_router(reports_router)
app.include_router(ai_router)
