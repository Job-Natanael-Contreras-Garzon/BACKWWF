"""Todas las rutas públicas del back viven bajo ``/api/v1`` (ESTANDARES §3)."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.config import router as config_router
from app.api.v1.health import router as health_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(config_router)
api_router.include_router(health_router)
