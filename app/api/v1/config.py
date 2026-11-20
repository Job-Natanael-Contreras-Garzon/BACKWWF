from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import UoWDep
from app.core.config import settings
from app.core.responses import ApiResponse, ok
from app.integrations.ia_contract.formats import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

router = APIRouter(prefix="/config", tags=["System"])


class MediaPublicConfig(BaseModel):
    max_file_mb: int
    max_video_seconds: int
    image_extensions: list[str]
    video_extensions: list[str]
    browser_duration_check_extensions: list[str]


class AnonLimitsConfig(BaseModel):
    max_files: int
    max_camera_stations: int


class UploadPublicConfig(BaseModel):
    max_parallel_files: int
    max_pending_per_user: int
    poll_interval_seconds: int


class PasswordRecoveryConfig(BaseModel):
    enabled: bool


class MapCenterConfig(BaseModel):
    lat: float
    lng: float


class MapPublicConfig(BaseModel):
    default_center: MapCenterConfig
    default_zoom: int
    label: str


class ImportPublicConfig(BaseModel):
    max_package_mb: int
    supported_format_versions: list[str]


class PublicConfigData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    anon_data_retention: bool
    media: MediaPublicConfig
    anon_limits: AnonLimitsConfig
    upload: UploadPublicConfig
    password_recovery: PasswordRecoveryConfig
    map: MapPublicConfig
    import_config: ImportPublicConfig = Field(alias="import")
    app_version: str


@router.get("/public", response_model=ApiResponse[PublicConfigData])
async def get_public_config(uow: UoWDep) -> ApiResponse[PublicConfigData]:
    anon_retention = bool(await uow.settings.get_value("anon_data_retention", True))
    data = PublicConfigData.model_validate(
        {
            "anon_data_retention": anon_retention,
            "media": MediaPublicConfig(
                max_file_mb=settings.MAX_FILE_MB,
                max_video_seconds=settings.MAX_VIDEO_SECONDS,
                image_extensions=sorted(ext.lstrip(".") for ext in IMAGE_EXTENSIONS),
                video_extensions=sorted(ext.lstrip(".") for ext in VIDEO_EXTENSIONS),
                browser_duration_check_extensions=settings.browser_duration_check_extensions,
            ),
            "anon_limits": AnonLimitsConfig(
                max_files=settings.ANON_MAX_FILES,
                max_camera_stations=settings.ANON_MAX_CAMERAS,
            ),
            "upload": UploadPublicConfig(
                max_parallel_files=settings.UPLOAD_MAX_PARALLEL_FILES,
                max_pending_per_user=settings.QUEUE_MAX_PENDING_PER_USER,
                poll_interval_seconds=settings.UPLOAD_POLL_INTERVAL_SECONDS,
            ),
            "password_recovery": PasswordRecoveryConfig(enabled=False),
            "map": MapPublicConfig(
                default_center=MapCenterConfig(
                    lat=settings.MAP_DEFAULT_CENTER_LAT,
                    lng=settings.MAP_DEFAULT_CENTER_LNG,
                ),
                default_zoom=settings.MAP_DEFAULT_ZOOM,
                label=settings.MAP_DEFAULT_LABEL,
            ),
            "import": ImportPublicConfig(
                max_package_mb=settings.IMPORT_MAX_MB,
                supported_format_versions=["1.0"],
            ),
            "app_version": settings.APP_VERSION,
        }
    )
    return ok(data)
