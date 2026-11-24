import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, false, func, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import UserRole
from app.models.base import Base, Timestamps, UUIDPrimaryKey, enum_type


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", func.lower(text("email")), unique=True),)

    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    institution: Mapped[str | None] = mapped_column(String(200))
    # El rol no se asigna por la API pública (solo CLI o admin).
    role: Mapped[UserRole] = mapped_column(
        enum_type(UserRole, "user_role"), default=UserRole.USER, server_default=UserRole.USER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # 0004 (BE-50, SEC-11): contraseña temporal del CLI; hasta cambiarla, 403
    # PASSWORD_CHANGE_REQUIRED.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(UUIDPrimaryKey, Base):
    """Refresh tokens rotatorios, guardados como hash (S5). Reuso de uno revocado = robo (CB-78)."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetToken(UUIDPrimaryKey, Base):
    """Un solo uso, 30 min; al crear uno se invalidan los anteriores (FL-14)."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_ip_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
