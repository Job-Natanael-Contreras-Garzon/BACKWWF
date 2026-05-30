from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime

class UserBase(BaseModel):
    full_name: str
    email: str
    institucion: Optional[str] = None
    sexo: Optional[str] = None

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    institucion: Optional[str] = None
    sexo: Optional[str] = None

class UserRead(UserBase):
    id: UUID
    created_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)
