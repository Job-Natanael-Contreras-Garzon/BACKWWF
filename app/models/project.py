import uuid
from typing import List, Optional
from sqlalchemy import String, Text, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.models.base import BaseEntity


class Project(BaseEntity):
    """
    Modelo ORM para Proyectos de Investigación.
    Hereda de BaseEntity (id, created_at, updated_at, is_deleted, deleted_at).
    """
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("status IN ('public', 'private', 'archived')", name="check_project_status"),
    )

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    anon_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("anon_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    objectives: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expected_results: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default="public")
    colaborators: Mapped[Optional[List[uuid.UUID]]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)

    user = relationship("User", back_populates="projects", lazy="selectin")
    reports = relationship("Report", back_populates="project", cascade="all, delete-orphan", lazy="raise")
    
    # Relación N:M a través de project_stations
    project_stations = relationship(
        "ProjectStation",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
        overlaps="camera_stations",
    )
    camera_stations: Mapped[List["CameraStation"]] = relationship(
        "CameraStation",
        secondary="project_stations",
        back_populates="projects",
        lazy="selectin",
        overlaps="project_stations",
    )
