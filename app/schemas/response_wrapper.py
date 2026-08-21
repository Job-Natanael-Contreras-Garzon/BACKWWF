from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel

from app.core.enums import ResponseStatus

T = TypeVar("T")


class StandardResponse(BaseModel, Generic[T]):
    status: ResponseStatus = ResponseStatus.SUCCESS
    data: Optional[T] = None
    message: str = "Operación realizada exitosamente"


class StandardErrorResponse(BaseModel):
    status: ResponseStatus = ResponseStatus.ERROR
    data: Optional[Any] = None
    message: str
