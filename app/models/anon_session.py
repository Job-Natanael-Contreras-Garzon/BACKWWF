import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AnonSessionStatus
from app.models.base import Base, UUIDPrimaryKey, enum_type


class AnonSession(UUIDPrimaryKey, Base):
    """Sesión anónima: se guarda el **hash** del token, nunca el token (DD-2)."""

    __tablename__ = "anon_sessions"

    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[AnonSessionStatus] = mapped_column(
        enum_type(AnonSessionStatus, "anon_session_status"),
        default=AnonSessionStatus.ACTIVE,
        server_default=AnonSessionStatus.ACTIVE,
    )
    claimed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
