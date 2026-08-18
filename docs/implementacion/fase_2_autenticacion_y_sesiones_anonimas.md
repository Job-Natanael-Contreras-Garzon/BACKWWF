# 📘 Fase 2: Autenticación, Sesión Anónima y Flujo de Reclamo

## 🎯 Objetivo de la Fase
Implementar el módulo completo de autenticación JWT (`/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`), el soporte para sesiones anónimas mediante el Header `X-Anon-Session-ID` (generando automáticamente un UUID si no se proporciona) y los endpoints para **reclamar datos anónimos** (`POST /users/me/claim`) y consultar **mi historial** (`GET /users/me/history`).

---

## 🛠️ Archivos a Crear / Modificar

| Acción | Archivo | Descripción |
| :--- | :--- | :--- |
| **[NEW]** | `app/models/anon_session.py` | Modelo ORM de la tabla `anon_sessions` |
| **[MODIFY]** | `app/api/deps.py` | Dependencias de autenticación JWT y manejo de `X-Anon-Session-ID` |
| **[NEW]** | `app/api/v1/auth.py` | Endpoints de autenticación (`register`, `login`, `refresh`, `me`) |
| **[MODIFY]** | `app/api/v1/users.py` | Endpoints `/users/me/claim` y `/users/me/history` |

---

## 📝 Instrucciones Paso a Paso

### 1. Modelo ORM `AnonSession` (`app/models/anon_session.py`)

```python
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base

class AnonSession(Base):
    __tablename__ = "anon_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    is_claimed = Column(Boolean, default=False, nullable=False)
    claimed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
```

---

### 2. Dependencias de Autenticación y Header Anónimo (`app/api/deps.py`)

Modificar `app/api/deps.py` para manejar adecuadamente:
1. Usuario Autenticado (`get_current_user`)
2. Usuario Opcional (`get_current_user_optional`)
3. ID de Sesión Anónima (`get_anon_session_id`)

```python
import uuid
from typing import Optional
from fastapi import Header, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.db.session import get_db
from app.core.security import decode_token
from app.models.user import User

async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación no proporcionado o inválido."
        )
    
    token = authorization.split(" ")[1]
    payload = decode_token(token, is_refresh=False)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado."
        )
        
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == UUID(user_id), User.is_deleted == False))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return user

async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(authorization=authorization, db=db)
    except HTTPException:
        return None

async def get_anon_session_id(
    response: Response,
    x_anon_session_id: Optional[UUID] = Header(None)
) -> UUID:
    """
    Obtiene el anon_session_id enviado en la cabecera. Si no viene, asume sesión anónima,
    genera un nuevo UUID y lo envía de vuelta en la cabecera de respuesta 'X-Anon-Session-ID'.
    """
    if x_anon_session_id:
        return x_anon_session_id
    
    new_anon_id = uuid.uuid4()
    response.headers["X-Anon-Session-ID"] = str(new_anon_id)
    return new_anon_id
```

---

### 3. Router de Autenticación (`app/api/v1/auth.py`)

Crear `app/api/v1/auth.py` con las siguientes rutas:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

from app.db.session import get_db
from app.models.user import User
from app.core.security import get_password_hash, verify_password, create_access_token, create_refresh_token, decode_token
from app.schemas.response_wrapper import StandardResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

class RegisterSchema(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    institucion: Optional[str] = None
    sexo: Optional[str] = None

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class RefreshSchema(BaseModel):
    refresh_token: str

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user_in: RegisterSchema, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado.")
        
    hashed_pwd = get_password_hash(user_in.password)
    new_user = User(
        full_name=user_in.full_name,
        email=user_in.email,
        hashed_password=hashed_pwd,
        institucion=user_in.institucion,
        sexo=user_in.sexo
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    access_token = create_access_token(subject=new_user.id)
    refresh_token = create_refresh_token(subject=new_user.id)
    
    return StandardResponse(
        message="Usuario registrado exitosamente",
        data={
            "user": {"id": str(new_user.id), "full_name": new_user.full_name, "email": new_user.email},
            "tokens": {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}
        }
    )

@router.post("/login")
async def login(credentials: LoginSchema, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == credentials.email, User.is_deleted == False))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas.")
        
    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)
    
    return StandardResponse(
        message="Autenticación exitosa",
        data={
            "user": {"id": str(user.id), "full_name": user.full_name, "email": user.email},
            "tokens": {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}
        }
    )

@router.post("/refresh")
async def refresh_tokens(data: RefreshSchema, db: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token, is_refresh=True)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token inválido o expirado.")
        
    user_id = payload.get("sub")
    access_token = create_access_token(subject=user_id)
    new_refresh_token = create_refresh_token(subject=user_id)
    
    return StandardResponse(
        message="Tokens renovados exitosamente",
        data={"access_token": access_token, "refresh_token": new_refresh_token, "token_type": "bearer"}
    )

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return StandardResponse(
        message="Perfil obtenido exitosamente",
        data={
            "id": str(current_user.id),
            "full_name": current_user.full_name,
            "email": current_user.email,
            "institucion": current_user.institucion,
            "sexo": current_user.sexo,
            "created_at": current_user.created_at
        }
    )
```

---

### 4. Endpoints de Reclamo y Mi Historial (`app/api/v1/users.py`)

Implementar `POST /users/me/claim` y `GET /users/me/history`:

```python
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from uuid import UUID

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.camera_station import CameraStation
from app.models.anon_session import AnonSession
from app.schemas.response_wrapper import StandardResponse

router = APIRouter(prefix="/users", tags=["Users & Sessions"])

class ClaimRequest(BaseModel):
    anon_session_id: UUID

@router.post("/me/claim")
async def claim_anon_data(
    data: ClaimRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Reasigna todas las estaciones y proyectos pertenecientes a `anon_session_id`
    hacia el `user_id` del usuario autenticado actual.
    """
    # 1. Actualizar proyectos anónimos
    proj_stmt = (
        update(Project)
        .where(Project.anon_session_id == data.anon_session_id, Project.is_deleted == False)
        .values(user_id=current_user.id)
    )
    proj_res = await db.execute(proj_stmt)
    
    # 2. Actualizar estaciones anónimas
    stat_stmt = (
        update(CameraStation)
        .where(CameraStation.anon_session_id == data.anon_session_id, CameraStation.is_deleted == False)
        .values(user_id=current_user.id)
    )
    stat_res = await db.execute(stat_stmt)
    
    # 3. Registrar o actualizar sesión anónima como reclamada
    session_res = await db.execute(select(AnonSession).where(AnonSession.id == data.anon_session_id))
    anon_session = session_res.scalar_one_or_none()
    if not anon_session:
        anon_session = AnonSession(id=data.anon_session_id, is_claimed=True, claimed_by_user_id=current_user.id, claimed_at=datetime.now(timezone.utc))
        db.add(anon_session)
    else:
        anon_session.is_claimed = True
        anon_session.claimed_by_user_id = current_user.id
        anon_session.claimed_at = datetime.now(timezone.utc)
        
    await db.commit()
    
    return StandardResponse(
        message="Datos anónimos vinculados exitosamente a su cuenta",
        data={
            "claimed_projects_count": proj_res.rowcount,
            "claimed_stations_count": stat_res.rowcount,
            "anon_session_id": str(data.anon_session_id),
            "claimed_by_user_id": str(current_user.id)
        }
    )

@router.get("/me/history")
async def get_my_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Devuelve los proyectos y estaciones pertenecientes al usuario autenticado.
    """
    projects_res = await db.execute(select(Project).where(Project.user_id == current_user.id, Project.is_deleted == False))
    projects = projects_res.scalars().all()
    
    stations_res = await db.execute(select(CameraStation).where(CameraStation.user_id == current_user.id, CameraStation.is_deleted == False))
    stations = stations_res.scalars().all()
    
    return StandardResponse(
        message="Historial del usuario obtenido exitosamente",
        data={
            "projects": [{"id": str(p.id), "title": p.title, "status": p.status, "created_at": p.created_at} for p in projects],
            "camera_stations": [{"id": str(s.id), "station_code": s.station_code, "location_name": s.location_name, "status": s.status, "created_at": s.created_at} for s in stations]
        }
    )
```

---

## ✅ Criterios de Aceptación de la Fase 2
- `/auth/register` crea el usuario y devuelve access_token y refresh_token.
- `/auth/login` valida credenciales bcrypt y entrega tokens.
- Al enviar un request sin `Authorization` ni `X-Anon-Session-ID`, el servidor inyecta automáticamente en los headers de la respuesta `X-Anon-Session-ID: <UUID>`.
- `/users/me/claim` traspasa la propiedad de estaciones/proyectos desde `anon_session_id` hacia `user_id`.
