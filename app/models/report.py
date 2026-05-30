import uuid
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import String, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from app.models.base import Base

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[Optional[str]] = mapped_column(String(150))
    report_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    applied_filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    user: Mapped[Optional["User"]] = relationship(back_populates="reports", lazy="selectin")
    project: Mapped[Optional["Project"]] = relationship(back_populates="reports", lazy="selectin")
