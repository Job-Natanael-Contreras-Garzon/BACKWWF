import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import EnvironmentMode

logger = logging.getLogger(__name__)

_PLACEHOLDER_MARKERS = (
    "super-secret-key",
    "change-me",
    "cambiar",
    "placeholder",
)


class Settings(BaseSettings):
    PROJECT_NAME: str = "Fauna Monitoring API"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: EnvironmentMode = EnvironmentMode.DEVELOPMENT
    LOG_LEVEL: str = "INFO"
    APP_VERSION: str = "dev"  # lo inyecta el build

    # Fotogramas de evidencia (LocalStorage; la BD guarda solo la clave)
    STORAGE_LOCAL_PATH: str = "/data/evidence"

    # Base de datos (inyectada por variable de entorno)
    DATABASE_URL: str = ""

    # Claves de Seguridad JWT (sin valores débiles por defecto)
    SECRET_KEY: str = ""
    REFRESH_SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"

    # Tiempos de Expiración Configurables
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Límites públicos, carga y mapa (/api/v1/config/public)
    MAX_FILE_MB: int = 300
    MAX_IMAGE_PIXELS: int = 100_000_000
    MAX_VIDEO_SECONDS: int = 15
    BROWSER_DURATION_CHECK_EXTENSIONS: str | list[str] = "mp4,mov,webm"
    ANON_MAX_FILES: int = 50
    ANON_MAX_CAMERAS: int = 5
    ANON_SESSION_TTL_HOURS: int = 24
    ANON_SESSION_RATE_LIMIT_PER_HOUR: int = 5
    UPLOAD_MAX_PARALLEL_FILES: int = 3
    QUEUE_MAX_PENDING_PER_USER: int = 500
    UPLOAD_POLL_INTERVAL_SECONDS: int = 3
    IMPORT_MAX_MB: int = 200
    MAP_DEFAULT_CENTER_LAT: float = -17.7833
    MAP_DEFAULT_CENTER_LNG: float = -63.1821
    MAP_DEFAULT_ZOOM: int = 8
    MAP_DEFAULT_LABEL: str = "Santa Cruz, Bolivia"

    # Recuperación de contraseña por correo (HU-04, FL-14). Apagada hasta tener dominio verificado.
    PASSWORD_RECOVERY_ENABLED: bool = False
    EMAIL_PROVIDER: str = "console"  # console (solo desarrollo) | resend
    RESEND_API_KEY: str = ""
    RESEND_API_URL: str = "https://api.resend.com/emails"
    EMAIL_FROM: str = ""
    EMAIL_TIMEOUT_SECONDS: float = 10.0
    FRONTEND_BASE_URL: str = "http://localhost:5173"
    DEV_MAILBOX_PATH: str = "/code/uploads/dev-mailbox"
    PASSWORD_RESET_TTL_MINUTES: int = 30
    EMAIL_DAILY_CAP: int = 80
    EMAIL_MONTHLY_CAP: int = 2500
    PASSWORD_FORGOT_EMAIL_PER_HOUR: int = 3
    PASSWORD_FORGOT_EMAIL_PER_DAY: int = 5
    PASSWORD_FORGOT_IP_PER_HOUR: int = 10
    PASSWORD_FORGOT_IP_ABUSE_PER_HOUR: int = 30

    # Servicios Externos
    AI_SERVICE_URL: str = ""
    AI_API_KEY: str = ""
    # Mayor que PROCESS_TIMEOUT_SECONDS de la IA (150 s) para recibir su 504 en vez de cortar antes.
    AI_TIMEOUT_SECONDS: float = 180.0
    VISUALCROSSING_API_KEY: str = ""

    # CORS
    ALLOWED_ORIGINS: str | list[str] = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Aborta el arranque en producción si faltan secretos o son débiles."""
        if self.ENVIRONMENT != EnvironmentMode.PRODUCTION:
            return self

        errors: list[str] = []
        if not self.DATABASE_URL.strip() or "password@host" in self.DATABASE_URL:
            errors.append("DATABASE_URL faltante o con placeholder")

        for name, value in (
            ("SECRET_KEY", self.SECRET_KEY),
            ("REFRESH_SECRET_KEY", self.REFRESH_SECRET_KEY),
        ):
            lowered = value.lower()
            if len(value.encode("utf-8")) < 32:
                errors.append(f"{name} < 32 bytes")
            elif any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
                errors.append(f"{name} contiene placeholder")

        if self.SECRET_KEY and self.SECRET_KEY == self.REFRESH_SECRET_KEY:
            errors.append("SECRET_KEY y REFRESH_SECRET_KEY deben ser distintas")

        if self.PASSWORD_RECOVERY_ENABLED:
            if self.EMAIL_PROVIDER != "resend":
                errors.append("EMAIL_PROVIDER debe ser 'resend' en producción")
            if not self.RESEND_API_KEY.strip():
                errors.append("RESEND_API_KEY faltante")
            if not self.EMAIL_FROM.strip():
                errors.append("EMAIL_FROM faltante")
            if not self.FRONTEND_BASE_URL.startswith("https://"):
                errors.append("FRONTEND_BASE_URL debe usar https")

        if errors:
            detail = "; ".join(errors)
            logger.critical("config.invalid: %s", detail)
            raise ValueError(f"config.invalid: {detail}")

        return self

    @property
    def cors_origins(self) -> list[str]:
        if isinstance(self.ALLOWED_ORIGINS, list):
            raw = self.ALLOWED_ORIGINS
        elif isinstance(self.ALLOWED_ORIGINS, str):
            if self.ALLOWED_ORIGINS.strip() == "*":
                return ["*"]
            raw = [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]
        else:
            raw = []

        clean_origins = {o.strip().rstrip("/") for o in raw if o.strip()}

        # Solo en desarrollo garantizamos orígenes locales
        if self.ENVIRONMENT == EnvironmentMode.DEVELOPMENT:
            clean_origins.update(
                {
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                }
            )

        return sorted(clean_origins)

    @property
    def browser_duration_check_extensions(self) -> list[str]:
        if isinstance(self.BROWSER_DURATION_CHECK_EXTENSIONS, list):
            raw = self.BROWSER_DURATION_CHECK_EXTENSIONS
        else:
            raw = self.BROWSER_DURATION_CHECK_EXTENSIONS.split(",")
        return [ext.strip().lstrip(".").lower() for ext in raw if ext.strip()]


settings = Settings()
