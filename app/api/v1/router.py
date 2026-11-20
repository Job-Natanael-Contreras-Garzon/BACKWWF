"""Todas las rutas públicas del back viven bajo ``/api/v1`` (ESTANDARES §3)."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.camera_stations import router as camera_stations_router
from app.api.v1.projects import router as projects_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(camera_stations_router)
