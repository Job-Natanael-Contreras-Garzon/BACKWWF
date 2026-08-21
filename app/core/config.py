from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


from app.core.enums import EnvironmentMode


class Settings(BaseSettings):
    PROJECT_NAME: str = "Fauna Monitoring API"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/wwf_db"
    ENVIRONMENT: EnvironmentMode = EnvironmentMode.PRODUCTION

    # Claves de Seguridad JWT
    SECRET_KEY: str = "super-secret-key-access-change-me-wwf-2026"
    REFRESH_SECRET_KEY: str = "super-secret-key-refresh-change-me-wwf-2026"
    ALGORITHM: str = "HS256"

    # Tiempos de Expiración Configurables
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Servicios Externos
    AI_SERVICE_URL: str = "http://localhost:8081"

    # CORS
    ALLOWED_ORIGINS: Union[str, List[str]] = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> List[str]:
        if isinstance(self.ALLOWED_ORIGINS, list):
            return self.ALLOWED_ORIGINS
        if isinstance(self.ALLOWED_ORIGINS, str):
            if self.ALLOWED_ORIGINS.strip() == "*":
                return ["*"]
            return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]
        return ["*"]


settings = Settings()
