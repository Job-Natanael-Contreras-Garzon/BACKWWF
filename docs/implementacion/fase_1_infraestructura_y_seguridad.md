# 📘 Fase 1: Infraestructura Base, Seguridad JWT y Middleware de Respuestas

## 🎯 Objetivo de la Fase
Establecer la configuración de entorno, el sistema de seguridad JWT con Access y Refresh Token (configurables desde `.env`), la envoltura estandarizada de respuestas `{status, data, message}` y los Exception Handlers globales de FastAPI.

---

## 🛠️ Archivos a Crear / Modificar

| Acción | Archivo | Descripción |
| :--- | :--- | :--- |
| **[NEW]** | `app/core/config.py` | Carga de variables de entorno con Pydantic Settings |
| **[NEW]** | `.env.example` | Plantilla de configuración de entorno |
| **[NEW]** | `app/core/security.py` | Hashing de passwords y gestión de tokens JWT |
| **[NEW]** | `app/schemas/response_wrapper.py` | Esquemas Pydantic para respuestas estandarizadas |
| **[MODIFY]** | `app/main.py` | Exception Handlers globales y middleware CORS/Headers |

---

## 📝 Instrucciones Paso a Paso

### 1. Configuración de Entorno (`app/core/config.py` y `.env.example`)

1. Crear el archivo `.env.example`:
```env
PROJECT_NAME="Fauna Monitoring API"
API_V1_STR="/api/v1"
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/wwf_db"

# Claves de Seguridad JWT
SECRET_KEY="CAMBIAR_POR_UNA_CLAVE_SUPER_SECRETA_ACCESS"
REFRESH_SECRET_KEY="CAMBIAR_POR_UNA_CLAVE_SUPER_SECRETA_REFRESH"
ALGORITHM="HS256"

# Tiempos de Expiración Configurables
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Servicios Externos
AI_SERVICE_URL="http://localhost:8080"
```

2. Crear `app/core/config.py`:
```python
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Fauna Monitoring API"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/wwf_db"
    
    SECRET_KEY: str = "super-secret-key-access-change-me"
    REFRESH_SECRET_KEY: str = "super-secret-key-refresh-change-me"
    ALGORITHM: str = "HS256"
    
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    AI_SERVICE_URL: str = "http://localhost:8080"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
```

---

### 2. Módulo de Seguridad JWT (`app/core/security.py`)

1. Instalar librerías requeridas si faltan (`passlib[bcrypt]`, `pyjwt` o `python-jose`):
```bash
pip install "passlib[bcrypt]" PyJWT
```

2. Implementar `app/core/security.py`:
```python
from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
import jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    encoded_jwt = jwt.encode(to_encode, settings.REFRESH_SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_token(token: str, is_refresh: bool = False) -> Optional[dict]:
    secret = settings.REFRESH_SECRET_KEY if is_refresh else settings.SECRET_KEY
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
```

---

### 3. Esquemas de Respuesta Estandarizada (`app/schemas/response_wrapper.py`)

Implementar las clases genéricas Pydantic:
```python
from pydantic import BaseModel
from typing import Generic, TypeVar, Optional, Any

T = TypeVar('T')

class StandardResponse(BaseModel, Generic[T]):
    status: str = "success"
    data: Optional[T] = None
    message: str = "Operación realizada exitosamente"

class StandardErrorResponse(BaseModel):
    status: str = "error"
    data: Optional[Any] = None
    message: str
```

---

### 4. Exception Handlers Globale en `main.py`

Actualizar `app/main.py` para asegurar que cualquier excepción HTTP (`HTTPException`), error de validación (`RequestValidationError`) o error 500 se transforme automáticamente en el formato `{status: "error", data: null, message: "..."}`:

```python
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException, RequestValidationError
from app.schemas.response_wrapper import StandardErrorResponse

app = FastAPI(title="Fauna Monitoring API", version="4.0.0")

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "data": None, "message": str(exc.detail)}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = errors[0]["msg"] if errors else "Error de validación en la petición"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"status": "error", "data": None, "message": f"Validación fallida: {msg}"}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "data": None, "message": f"Error interno del servidor: {str(exc)}"}
    )
```

---

## ✅ Criterios de Aceptación de la Fase 1
- El archivo `.env` se lee correctamente y sobreescribe los valores por defecto.
- Toda respuesta HTTP de error (400, 401, 403, 404, 422, 500) devuelve la estructura `{"status": "error", "data": null, "message": "..."}`.
- La función `create_access_token` expira en los minutos definidos en `.env`.
- La función `create_refresh_token` expira en los días definidos en `.env`.
