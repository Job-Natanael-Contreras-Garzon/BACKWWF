"""Todas las rutas públicas del back viven bajo ``/api/v1`` (ESTANDARES §3).

HU-02 retiró los routers legados (escritos sobre el esquema viejo). Se reconstruyen desde el
contrato en HU-03 (auth), HU-05 (anon-sessions), HU-06 (camera-stations) y HU-07 (projects).
"""

from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")
