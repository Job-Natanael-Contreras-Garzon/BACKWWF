from .base import CRUDBase
from .crud_project import project as project_crud
from .crud_species import species as species_crud
from .crud_camera_station import camera_station as camera_station_crud

from app.models import User, Project, Report, CameraStation, Video, Species, Individual
from app.schemas import (
    UserCreate, UserUpdate,
    ProjectCreate, ProjectUpdate,
    ReportCreate, ReportUpdate,
    CameraStationCreate, CameraStationUpdate,
    VideoCreate, VideoUpdate,
    SpeciesCreate, SpeciesUpdate,
    IndividualCreate, IndividualUpdate
)

# Instanciamos los CRUD dinámicamente para cada entidad
user = CRUDBase[User, UserCreate, UserUpdate](User)
project = project_crud
report = CRUDBase[Report, ReportCreate, ReportUpdate](Report)
camera_station = camera_station_crud
video = CRUDBase[Video, VideoCreate, VideoUpdate](Video)
species = species_crud
individual = CRUDBase[Individual, IndividualCreate, IndividualUpdate](Individual)
