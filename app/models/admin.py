"""Tablas de operación: auditoría del admin, configuración en caliente, purgas y correos."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AdminAction, EmailStatus, EmailType
from app.models.base import Base, UUIDPrimaryKey, enum_type


class AdminAuditLog(UUIDPrimaryKey, Base):
    """Solo inserción: toda acción del admin queda registrada (FL-40..44)."""

    __tablename__ = "admin_audit_log"

    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    action: Mapped[AdminAction] = mapped_column(enum_type(AdminAction, "admin_action"))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    old_value: Mapped[object | None] = mapped_column(JSONB)
    new_value: Mapped[object | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class SystemSetting(Base):
    """Configuración que cambia el admin en caliente. Primera clave: anon_data_retention."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[object] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AnonPurgeRun(UUIDPrimaryKey, Base):
    """Conteos de cada purga FL-30, sin datos personales ni taxonómicos."""

    __tablename__ = "anon_purge_runs"

    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    classifications: Mapped[int] = mapped_column(Integer, default=0)
    camera_stations: Mapped[int] = mapped_column(Integer, default=0)
    projects: Mapped[int] = mapped_column(Integer, default=0)
    frames: Mapped[int] = mapped_column(Integer, default=0)


class EmailLog(UUIDPrimaryKey, Base):
    """Cuota y auditoría de correos. Nunca guarda el correo en claro (to_hash)."""

    __tablename__ = "email_log"

    type: Mapped[EmailType] = mapped_column(enum_type(EmailType, "email_type"))
    to_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[EmailStatus] = mapped_column(enum_type(EmailStatus, "email_status"))
    provider_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
