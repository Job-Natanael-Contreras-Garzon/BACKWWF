from uuid import UUID
from pydantic import BaseModel, ConfigDict


class AssociateStationSchema(BaseModel):
    station_id: UUID


class AssociateStationResponse(BaseModel):
    project_id: UUID
    station_id: UUID
    model_config = ConfigDict(from_attributes=True)
