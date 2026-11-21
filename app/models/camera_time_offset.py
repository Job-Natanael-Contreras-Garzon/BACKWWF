"""Auditoría de las correcciones de hora de una cámara (#15d, CB-18, D14).

``admin_audit_log`` es solo para acciones del admin; esta corrección la hace el dueño (usuario o
sesión anónima), así que tiene su propia tabla de solo inserción.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKey


class CameraTimeOffset(UUIDPrimaryKey, Base):
    __tablename__ = "camera_time_offsets"

    # CASCADE: la purga FL-30 borra cámaras anónimas y su auditoría con ellas.
    camera_station_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("camera_stations.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    anon_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("anon_sessions.id", ondelete="SET NULL")
    )
    offset_seconds: Mapped[int] = mapped_column(Integer)
    from_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    to_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    reason: Mapped[str] = mapped_column(Text)
    updated: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
