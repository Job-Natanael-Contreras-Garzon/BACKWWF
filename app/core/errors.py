"""Errores de negocio con código estable del catálogo (ESTANDARES §5–§6).

Los servicios lanzan ``AppError`` (o una subclase) y el handler global de ``main.py`` los
convierte en la envoltura de error. ``context`` va al log, nunca a la respuesta.
"""

import logging
from typing import Any


class AppError(Exception):
    http_status: int = 500
    log_level: int = logging.ERROR
    default_message: str = "Ocurrió un error inesperado."

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        details: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message or self.default_message
        self.details = details or []
        self.context = context or {}
        super().__init__(f"{code}: {self.message}")


class BadRequestError(AppError):
    http_status = 400
    log_level = logging.INFO
    default_message = "La petición no es válida."


class NotFoundError(AppError):
    http_status = 404
    log_level = logging.INFO
    default_message = "El recurso no existe."


class GoneError(AppError):
    http_status = 410
    log_level = logging.INFO
    default_message = "El recurso ya no está disponible."


class ForbiddenError(AppError):
    http_status = 403
    log_level = logging.WARNING
    default_message = "No tienes permiso para realizar esta acción."


class ConflictError(AppError):
    http_status = 409
    log_level = logging.INFO
    default_message = "La operación entra en conflicto con el estado actual."


class BusinessRuleError(AppError):
    http_status = 422
    log_level = logging.INFO
    default_message = "La operación no cumple una regla del sistema."


class DependencyError(AppError):
    http_status = 502
    log_level = logging.ERROR
    default_message = "Un servicio externo no respondió correctamente. Intenta de nuevo."


class UnauthorizedError(AppError):
    http_status = 401
    log_level = logging.INFO
    default_message = "Debes iniciar sesión para continuar."


class RateLimitError(AppError):
    http_status = 429
    log_level = logging.WARNING
    default_message = "Demasiados intentos. Espera un momento antes de volver a intentar."


class ServiceUnavailableError(AppError):
    """503 para ``/health/ready``; ``SERVICE_UNAVAILABLE`` es código nuevo a sincronizar."""

    http_status = 503
    log_level = logging.WARNING
    default_message = "Uno o más servicios dependientes no están disponibles."
