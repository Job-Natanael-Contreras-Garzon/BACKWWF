from typing import List, Optional
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseEntity


class User(BaseEntity):
    """
    Modelo ORM para Usuarios del Sistema.
    Hereda de BaseEntity (id, created_at, updated_at, is_deleted, deleted_at).
    """
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    institucion: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    sexo: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    projects: Mapped[List["Project"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    reports: Mapped[List["Report"]] = relationship(
        back_populates="user", lazy="selectin"
    )
