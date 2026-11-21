"""Esquema canónico (FLUJOS_SISTEMA §3). Importar el paquete registra todas las tablas."""

from app.models.admin import AdminAuditLog, AnonPurgeRun, EmailLog, SystemSetting
from app.models.anon_session import AnonSession
from app.models.base import Base
from app.models.camera_station import CameraStation
from app.models.classification import Classification, ClassificationBatch
from app.models.desktop_import import DesktopImport
from app.models.project import Project, ProjectCameraStation
from app.models.user import PasswordResetToken, RefreshToken, User

__all__ = [
    "AdminAuditLog",
    "AnonPurgeRun",
    "AnonSession",
    "Base",
    "CameraStation",
    "Classification",
    "ClassificationBatch",
    "DesktopImport",
    "EmailLog",
    "PasswordResetToken",
    "Project",
    "ProjectCameraStation",
    "RefreshToken",
    "SystemSetting",
    "User",
]
