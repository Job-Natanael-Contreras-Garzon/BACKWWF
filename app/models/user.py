import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from app.models.base import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    institucion: Mapped[Optional[str]] = mapped_column(String(150))
    created_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    sexo: Mapped[Optional[str]] = mapped_column(String(10))

    projects: Mapped[List["Project"]] = relationship(back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    reports: Mapped[List["Report"]] = relationship(back_populates="user", lazy="selectin")
