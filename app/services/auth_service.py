from typing import Any, Dict
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.interfaces.auth_service import IAuthService
from app.models.user import User
from app.schemas.auth import LoginSchema, RefreshSchema, RegisterSchema


class AuthService(IAuthService):
    """
    Implementación del caso de uso de autenticación y seguridad JWT.
    Cumple con la interfaz IAuthService.
    """

    async def register_user(self, db: AsyncSession, user_in: RegisterSchema) -> Dict[str, Any]:
        result = await db.execute(
            select(User).where(User.email == user_in.email, User.is_deleted == False)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo electrónico ya está registrado.",
            )

        hashed_pwd = get_password_hash(user_in.password)
        new_user = User(
            full_name=user_in.full_name,
            email=user_in.email,
            hashed_password=hashed_pwd,
            institucion=user_in.institucion,
            sexo=user_in.sexo,
            is_active=True,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        access_token = create_access_token(subject=str(new_user.id))
        refresh_token = create_refresh_token(subject=str(new_user.id))

        return {
            "user": {
                "id": str(new_user.id),
                "full_name": new_user.full_name,
                "email": new_user.email,
                "institucion": new_user.institucion,
                "sexo": new_user.sexo,
                "created_at": new_user.created_at,
            },
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
            },
        }

    async def authenticate_user(self, db: AsyncSession, credentials: LoginSchema) -> Dict[str, Any]:
        result = await db.execute(
            select(User).where(User.email == credentials.email, User.is_deleted == False)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(credentials.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="La cuenta de usuario se encuentra desactivada.",
            )

        access_token = create_access_token(subject=str(user.id))
        refresh_token = create_refresh_token(subject=str(user.id))

        return {
            "user": {
                "id": str(user.id),
                "full_name": user.full_name,
                "email": user.email,
                "institucion": user.institucion,
                "sexo": user.sexo,
                "created_at": user.created_at,
            },
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
            },
        }

    async def refresh_tokens(self, db: AsyncSession, data: RefreshSchema) -> Dict[str, Any]:
        payload = decode_token(data.refresh_token, is_refresh=True)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido o expirado.",
            )

        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token con estructura de sujeto inválida.",
            )

        try:
            user_uuid = UUID(user_id_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Identificador de usuario inválido en token.",
            )

        result = await db.execute(
            select(User).where(User.id == user_uuid, User.is_deleted == False)
        )
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario asociado al token no existe o está inactivo.",
            )

        new_access_token = create_access_token(subject=str(user.id))
        new_refresh_token = create_refresh_token(subject=str(user.id))

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        }

    async def get_user_profile(self, current_user: User) -> Dict[str, Any]:
        return {
            "id": str(current_user.id),
            "full_name": current_user.full_name,
            "email": current_user.email,
            "institucion": current_user.institucion,
            "sexo": current_user.sexo,
            "is_active": current_user.is_active,
            "created_at": current_user.created_at,
        }


auth_service = AuthService()
