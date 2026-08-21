import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from app.models.base import BaseEntity


class AnonSession(BaseEntity):
    """
    Modelo ORM para el registro y seguimiento de sesiones anónimas.
    Hereda de BaseEntity (id, created_at, updated_at, is_deleted, deleted_at).
    """
    __tablename__ = "anon_sessions"

    is_claimed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    claimed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    claimed_by_user = relationship("User", backref="claimed_sessions", lazy="raise")
