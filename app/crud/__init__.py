from .base import CRUDBase

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
project = CRUDBase[Project, ProjectCreate, ProjectUpdate](Project)
report = CRUDBase[Report, ReportCreate, ReportUpdate](Report)
camera_station = CRUDBase[CameraStation, CameraStationCreate, CameraStationUpdate](CameraStation)
video = CRUDBase[Video, VideoCreate, VideoUpdate](Video)
species = CRUDBase[Species, SpeciesCreate, SpeciesUpdate](Species)
individual = CRUDBase[Individual, IndividualCreate, IndividualUpdate](Individual)
