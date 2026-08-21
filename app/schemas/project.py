from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from app.core.enums import CameraStationStatus, ProjectStatus


class StationInProjectSummary(BaseModel):
    id: UUID
    station_code: str
    location_name: Optional[str] = None
    status: Optional[CameraStationStatus] = CameraStationStatus.ACTIVE
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ProjectBase(BaseModel):
    title: str
    description: Optional[str] = None
    objectives: Optional[str] = None
    expected_results: Optional[str] = None
    status: Optional[ProjectStatus] = ProjectStatus.PUBLIC
    colaborators: Optional[List[UUID]] = None


class ProjectCreate(ProjectBase):
    user_id: Optional[UUID] = None
    anon_session_id: Optional[UUID] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    objectives: Optional[str] = None
    expected_results: Optional[str] = None
    status: Optional[ProjectStatus] = None
    colaborators: Optional[List[UUID]] = None


class ProjectRead(ProjectBase):
    id: UUID
    user_id: Optional[UUID] = None
    anon_session_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    camera_stations: List[StationInProjectSummary] = []

    model_config = ConfigDict(from_attributes=True)


class ProjectAddCollaborators(BaseModel):
    colaborators: List[UUID]


class UserProjectsResponse(BaseModel):
    owned_projects: List[UUID]
    collaborator_projects: List[UUID]


class ProjectTaxonomyItem(BaseModel):
    name: str
    count: int


class ProjectSummaryResponse(BaseModel):
    project_id: UUID
    total_associated_stations: int
    distinct_species_count: int
    total_detections_count: int
    frequency_by_species: List[Dict[str, Any]] = []
    frequency_by_family: List[Dict[str, Any]] = []
    frequency_by_genus: List[Dict[str, Any]] = []
