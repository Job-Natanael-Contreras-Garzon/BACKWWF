import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.enums import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    institution: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class AuthTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = Field(default="bearer")
    expires_in: int


class AuthSessionData(BaseModel):
    user: UserRead
    tokens: AuthTokens
    anon_session: dict[str, Any] | None = None


class RefreshTokenData(BaseModel):
    tokens: AuthTokens


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = Field(min_length=1, max_length=150)
    institution: str | None = Field(default=None, max_length=200)

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre completo no puede estar vacío.")
        return cleaned

    @field_validator("institution")
    @classmethod
    def strip_institution(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class UpdateMeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    institution: str | None = Field(default=None, max_length=200)

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre completo no puede estar vacío.")
        return cleaned


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str
