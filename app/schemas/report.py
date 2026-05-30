from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from uuid import UUID
from datetime import datetime

class ReportBase(BaseModel):
    title: Optional[str] = None
    report_data: dict[str, Any]
    applied_filters: dict[str, Any]

class ReportCreate(ReportBase):
    project_id: UUID
    user_id: Optional[UUID] = None

class ReportUpdate(BaseModel):
    title: Optional[str] = None

class ReportRead(ReportBase):
    id: UUID
    user_id: Optional[UUID]
    project_id: UUID
    generated_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)
