from enum import Enum


class CameraStationStatus(str, Enum):
    """Estados del ciclo de vida de una estación de cámara trampa."""
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    RETRIEVED = "retrieved"


class ProjectStatus(str, Enum):
    """Niveles de visibilidad y acceso de un proyecto de investigación."""
    PUBLIC = "public"
    PRIVATE = "private"


class MediaType(str, Enum):
    """Tipos de archivo multimedia capturados en campo."""
    VIDEO = "video"
    IMAGE = "image"


class ResponseStatus(str, Enum):
    """Estatus unificado de respuestas JSON de la API."""
    SUCCESS = "success"
    ERROR = "error"


class UserGender(str, Enum):
    """Opciones de género/sexo para usuarios registrados."""
    MALE = "M"
    FEMALE = "F"


class DetectionCategory(str, Enum):
    """Categorías estándar de detección de objetos / fauna de visión por computadora."""
    ANIMAL = "animal"
    PERSON = "person"
    VEHICLE = "vehicle"
    UNKNOWN = "unknown"


class EnvironmentMode(str, Enum):
    """Entornos de ejecución de la aplicación."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
