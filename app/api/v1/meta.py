"""Metadatos para el front en desarrollo (FE-51): la lista de códigos de error del back."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.core.enums import EnvironmentMode
from app.core.error_catalog import CATALOG, ErrorKind
from app.core.errors import NotFoundError
from app.core.responses import ApiResponse, ok

router = APIRouter(
    prefix="/meta",
    tags=["Meta"],
    include_in_schema=settings.ENVIRONMENT == EnvironmentMode.DEVELOPMENT,
)


class ErrorCodeRead(BaseModel):
    code: str
    http_status: int | None
    also_http: list[int]
    kind: ErrorKind
    message: str


@router.get("/error-codes", response_model=ApiResponse[list[ErrorCodeRead]])
async def error_codes() -> ApiResponse[list[ErrorCodeRead]]:
    """Solo en desarrollo: Miguel compara ``utils/errorMessages.js`` con esta lista. En
    producción responde 404, como cualquier ruta que no existe."""
    if settings.ENVIRONMENT != EnvironmentMode.DEVELOPMENT:
        raise NotFoundError("ROUTE_NOT_FOUND", "La ruta solicitada no existe.")
    data = [
        ErrorCodeRead(
            code=s.code,
            http_status=s.http_status,
            also_http=list(s.also_http),
            kind=s.kind,
            message=s.message,
        )
        for s in CATALOG
    ]
    return ok(data)
