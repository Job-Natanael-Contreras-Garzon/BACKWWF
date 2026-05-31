from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime

class IndividualBase(BaseModel):
    name: str
    is_verified: Optional[bool] = None

class IndividualCreate(IndividualBase):
    species_id: Optional[int] = None

class IndividualUpdate(BaseModel):
    name: Optional[str] = None

class IndividualRead(IndividualBase):
    id: UUID
    species_id: Optional[int]
    created_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)
