from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr

from app.core.enums import UserGender


class RegisterSchema(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    institucion: Optional[str] = None
    sexo: Optional[UserGender] = None


class LoginSchema(BaseModel):
    email: EmailStr
    password: str


class RefreshSchema(BaseModel):
    refresh_token: str


class AuthTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserReadBasic(BaseModel):
    id: UUID
    full_name: str
    email: str
    institucion: Optional[str] = None
    sexo: Optional[UserGender] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AuthDataResponse(BaseModel):
    user: UserReadBasic
    tokens: AuthTokens
