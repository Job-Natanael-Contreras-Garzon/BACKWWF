import logging
from typing import List, Union
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

    # Base de datos (inyectada por variable de entorno)
    DATABASE_URL: str = ""

    # Claves de Seguridad JWT (sin valores débiles por defecto)
    SECRET_KEY: str = ""
    REFRESH_SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"

    # Tiempos de Expiración Configurables
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Servicios Externos
    AI_SERVICE_URL: str = ""
    AI_API_KEY: str = ""
    # Mayor que PROCESS_TIMEOUT_SECONDS de la IA (150 s) para recibir su 504 en vez de cortar antes.
    AI_TIMEOUT_SECONDS: float = 180.0
    VISUALCROSSING_API_KEY: str = ""

    # CORS
    ALLOWED_ORIGINS: Union[str, List[str]] = ""

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

        if errors:
            detail = "; ".join(errors)
            logger.critical("config.invalid: %s", detail)
            raise ValueError(f"config.invalid: {detail}")

        return self

    @property
    def cors_origins(self) -> List[str]:
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


settings = Settings()
