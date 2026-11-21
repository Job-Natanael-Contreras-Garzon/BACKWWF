"""Estados y categorías del dominio (FLUJOS_SISTEMA §3, API_BACK_FRONT).

``Category``, ``Rank`` y ``MediaType`` vienen de la copia del contrato de la IA: la BD acepta
exactamente lo que la IA devuelve.
"""

from enum import StrEnum

from app.integrations.ia_contract.enums import Category, MediaType, Rank

__all__ = [
    "AdminAction",
    "AnonSessionStatus",
    "BatchSource",
    "BatchStatus",
    "CaptureSource",
    "Category",
    "ClassificationSource",
    "ClassificationStatus",
    "CorrectionSource",
    "EmailStatus",
    "EmailType",
    "EnvironmentMode",
    "ImportStatus",
    "MediaType",
    "Rank",
    "UserRole",
    "ValidationStatus",
    "Visibility",
]


class EnvironmentMode(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class AnonSessionStatus(StrEnum):
    ACTIVE = "active"
    CLAIMED = "claimed"
    EXPIRED = "expired"  # el token ya no sirve; los datos se conservan


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class BatchSource(StrEnum):
    WEB = "web"
    DESKTOP_IMPORT = "desktop_import"


class BatchStatus(StrEnum):
    OPEN = "open"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    CANCELLED = "cancelled"
    INCOMPLETE = "incomplete"


class ClassificationSource(StrEnum):
    WEB = "web"
    DESKTOP = "desktop"


class CaptureSource(StrEnum):
    EXIF = "exif"
    CONTAINER = "container"
    FILENAME = "filename"
    CLIENT_MTIME = "client_mtime"
    UPLOAD_TIME = "upload_time"


class ClassificationStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class ValidationStatus(StrEnum):
    UNVALIDATED = "unvalidated"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    CORRECTED_UNLISTED = "corrected_unlisted"
    REJECTED = "rejected"
    DISCARDED_REPEAT = "discarded_repeat"


class CorrectionSource(StrEnum):
    ALTERNATIVE = "alternative"
    CATALOG = "catalog"
    UNLISTED = "unlisted"


class ImportStatus(StrEnum):
    PREVIEW = "preview"
    PROCESSING = "processing"  # D10: el worker la está importando
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AdminAction(StrEnum):
    SOFT_DELETE = "soft_delete"
    RESTORE = "restore"
    DEACTIVATE_USER = "deactivate_user"
    REACTIVATE_USER = "reactivate_user"
    EXPORT = "export"
    UPDATE_SETTING = "update_setting"


class EmailType(StrEnum):
    PASSWORD_RESET = "password_reset"  # noqa: S105 (tipo de correo, no una contraseña)


class EmailStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED_LIMIT = "skipped_limit"
