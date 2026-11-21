"""Todas las rutas públicas del back viven bajo ``/api/v1`` (ESTANDARES §3)."""

from fastapi import APIRouter

from app.api.v1.anon_sessions import router as anon_sessions_router
from app.api.v1.auth import router as auth_router
from app.api.v1.batches import router as batches_router
from app.api.v1.camera_stations import router as camera_stations_router
from app.api.v1.catalog import router as catalog_router
from app.api.v1.classifications import router as classifications_router
from app.api.v1.config import router as config_router
from app.api.v1.health import router as health_router
from app.api.v1.imports import router as imports_router
from app.api.v1.projects import router as projects_router
from app.api.v1.reports import router as reports_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(camera_stations_router)
api_router.include_router(batches_router)
api_router.include_router(anon_sessions_router)
api_router.include_router(classifications_router)
api_router.include_router(catalog_router)
api_router.include_router(config_router)
api_router.include_router(health_router)
api_router.include_router(imports_router)
api_router.include_router(projects_router)
api_router.include_router(reports_router)
