"""Envoltura única de respuesta ``{status, data, message, error, meta}`` (ESTANDARES §4)."""

from datetime import UTC, datetime
from typing import Any, Generic, Literal, TypeVar

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.logging import flow_var, request_id_var

T = TypeVar("T")


class ErrorDetail(BaseModel):
    field: str | None = None
    code: str | None = None
    message: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ErrorBody(BaseModel):
    code: str
    flow: str | None = None
    details: list[ErrorDetail] = Field(default_factory=list)


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class ApiWarning(BaseModel):
    """Aviso que no impide la operación (p. ej. ``VIDEO_TRUNCATED``)."""

    code: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class Meta(BaseModel):
    request_id: str
    timestamp: datetime
    pagination: Pagination | None = None
    warnings: list[ApiWarning] = Field(default_factory=list)


def current_meta() -> Meta:
    """``meta`` sale del contexto de la petición: el router nunca lo arma a mano."""
    return Meta(request_id=request_id_var.get(), timestamp=datetime.now(UTC))


class ApiResponse(BaseModel, Generic[T]):
    status: Literal["success", "error"] = "success"
    data: T | None = None
    message: str = "OK"
    error: ErrorBody | None = None
    meta: Meta = Field(default_factory=current_meta)


def ok(
    data: T,
    message: str = "OK",
    *,
    pagination: Pagination | None = None,
    warnings: list[ApiWarning] | None = None,
) -> ApiResponse[T]:
    meta = current_meta()
    meta.pagination = pagination
    meta.warnings = warnings or []
    return ApiResponse[T](data=data, message=message, meta=meta)


def error_response(
    http_status: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ApiResponse[None](
        status="error",
        message=message,
        error=ErrorBody(
            code=code,
            flow=flow_var.get(),
            details=[ErrorDetail(**detail) for detail in details or []],
        ),
    )
    return JSONResponse(
        status_code=http_status,
        content=body.model_dump(mode="json"),
        headers={"X-Request-ID": body.meta.request_id, **(headers or {})},
    )
