import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Visibility
from app.models.base import (
    Base,
    Owned,
    SoftDelete,
    Timestamps,
    UUIDPrimaryKey,
    enum_type,
    owner_xor,
)


class Project(UUIDPrimaryKey, Owned, SoftDelete, Timestamps, Base):
    """Proyecto individual, sin colaboradores (FL-07)."""

    __tablename__ = "projects"
    __table_args__ = (owner_xor(),)

    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[Visibility] = mapped_column(
        enum_type(Visibility, "project_visibility"),
        default=Visibility.PRIVATE,
        server_default=Visibility.PRIVATE,
    )
    # Bloqueo optimista para PATCH con If-Match (HU-07, CB-15).
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class ProjectCameraStation(Base):
    """N:M proyecto–cámara. Solo cámaras del mismo dueño: lo valida el servicio (CB-23)."""

    __tablename__ = "project_camera_stations"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    camera_station_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("camera_stations.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
