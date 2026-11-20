"""Base declarativa y columnas comunes del esquema canónico (FLUJOS_SISTEMA §3)."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, MetaData, Text, Uuid, false
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

# Nombres estables para constraints e índices: la migración y el modelo siempre coinciden.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def enum_type(enum_cls: type[Enum], name: str) -> SAEnum:
    """VARCHAR + CHECK con los valores del enum (sin tipos nativos: migrar valores es un ALTER)."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda cls: [member.value for member in cls],
    )


def owner_xor() -> CheckConstraint:
    """Cada recurso es de un usuario **o** de una sesión anónima: nunca ambos ni ninguno."""
    return CheckConstraint("(owner_user_id IS NULL) <> (anon_session_id IS NULL)", name="owner_xor")


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SoftDelete:
    """Borrado lógico: la aplicación nunca borra físicamente (salvo FL-30 con anon_retain=false)."""

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # usuario o admin
    deleted_reason: Mapped[str | None] = mapped_column(Text)


class Owned:
    """Dueño XOR (usuario o sesión anónima). Cada tabla agrega ``owner_xor()`` a sus constraints."""

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    anon_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("anon_sessions.id", ondelete="RESTRICT"), index=True
    )
    # Copia de anon_data_retention al crear la fila (FL-44); NULL en filas de usuarios.
    anon_retain: Mapped[bool | None] = mapped_column(Boolean)


JSONDict = dict[str, Any]
