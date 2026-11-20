"""Compatibilidad con los routers legados: ``StandardResponse`` es la ``ApiResponse`` de HU-01.

``meta`` se completa solo desde el contexto, así las rutas viejas ya responden la envoltura
estándar ``{status, data, message, error, meta}`` sin tocarlas.
"""

from app.core.responses import ApiResponse

# shortcut: alias hasta que cada router use ok() y AppError en su HU (HU-03/06/07).
StandardResponse = ApiResponse
StandardErrorResponse = ApiResponse
