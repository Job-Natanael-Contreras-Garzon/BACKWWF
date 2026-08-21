import uuid
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseEntity


class ProjectStation(BaseEntity):
    """
    Tabla intermedia para la relación Muchos a Muchos (N:M) entre Proyectos y Estaciones.
    Hereda de BaseEntity para permitir auditoría y desvinculación lógica (Soft Delete).
    """
    __tablename__ = "project_stations"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("camera_stations.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )

    project = relationship(
        "Project",
        back_populates="project_stations",
        lazy="selectin",
        overlaps="camera_stations,projects",
    )
    station = relationship(
        "CameraStation",
        back_populates="project_stations",
        lazy="selectin",
        overlaps="camera_stations,projects",
    )
