"""Dueño y visibilidad: el filtro que evita IDOR vive aquí y lo usan todos los repositorios (S1).

Un recurso privado ajeno se trata como inexistente (404), así que los repositorios nunca
devuelven filas que el ``viewer`` no puede ver.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, false, or_

from app.core.enums import Visibility
from app.core.geo import round_1km
from app.models.base import Owned
from app.models.camera_station import CameraStation
from app.models.project import Project


@dataclass(frozen=True)
class Owner:
    """Quien actúa: un usuario **o** una sesión anónima (mismo XOR que el CHECK de la BD)."""

    user_id: uuid.UUID | None = None
    anon_session_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if (self.user_id is None) == (self.anon_session_id is None):
            raise ValueError("Owner necesita user_id o anon_session_id, uno solo")

    @property
    def is_anonymous(self) -> bool:
        return self.anon_session_id is not None

    def assign_to(self, entity: Owned, *, anon_retain: bool) -> None:
        """Marca el dueño de una fila nueva. ``anon_retain`` se congela al crear (FL-44)."""
        entity.owner_user_id = self.user_id
        entity.anon_session_id = self.anon_session_id
        entity.anon_retain = anon_retain if self.is_anonymous else None


def owned_by(model: type[Owned], owner: Owner) -> ColumnElement[bool]:
    if owner.user_id is not None:
        return model.owner_user_id == owner.user_id
    return model.anon_session_id == owner.anon_session_id


def visible_to(
    model: type[CameraStation] | type[Project], viewer: Owner | None
) -> ColumnElement[bool]:
    """Público para cualquiera; privado solo para su dueño. Los anónimos nunca publican."""
    public = model.visibility == Visibility.PUBLIC
    return public if viewer is None else or_(public, owned_by(model, viewer))


def is_mine_sql(model: type[Owned], viewer: Owner | None) -> ColumnElement[bool]:
    """Como ``owned_by`` pero nunca NULL: se puede negar sin perder filas de otro tipo de dueño."""
    if viewer is None:
        return false()
    if viewer.user_id is not None:
        return and_(model.owner_user_id.is_not(None), model.owner_user_id == viewer.user_id)
    return and_(model.anon_session_id.is_not(None), model.anon_session_id == viewer.anon_session_id)


def is_owner(entity: Owned, viewer: Owner | None) -> bool:
    if viewer is None:
        return False
    if viewer.user_id is not None:
        return entity.owner_user_id == viewer.user_id
    return entity.anon_session_id == viewer.anon_session_id


def serialize_location(camera: CameraStation, viewer: Owner | None) -> tuple[float, float, str]:
    """DD-17: coordenadas exactas solo para el dueño; ~1 km (2 decimales) para los demás."""
    if is_owner(camera, viewer):
        return float(camera.latitude), float(camera.longitude), "exact"
    return round_1km(camera.latitude), round_1km(camera.longitude), "approx_1km"
