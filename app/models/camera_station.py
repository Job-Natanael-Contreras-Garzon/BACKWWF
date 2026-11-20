import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Visibility
from app.models.base import (
    Base,
    Owned,
    SoftDelete,
    Timestamps,
    UUIDPrimaryKey,
    enum_type,
    owner_xor,
)

_ACTIVE = text("is_deleted = false")


class CameraStation(UUIDPrimaryKey, Owned, SoftDelete, Timestamps, Base):
    __tablename__ = "camera_stations"
    __table_args__ = (
        owner_xor(),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        # CB-13: code único por dueño, sin distinguir mayúsculas, entre las no borradas.
        Index(
            "uq_camera_stations_user_code",
            "owner_user_id",
            func.lower(text("code")),
            unique=True,
            postgresql_where=text("is_deleted = false AND owner_user_id IS NOT NULL"),
        ),
        Index(
            "uq_camera_stations_anon_code",
            "anon_session_id",
            func.lower(text("code")),
            unique=True,
            postgresql_where=text("is_deleted = false AND anon_session_id IS NOT NULL"),
        ),
        Index("ix_camera_stations_public", "visibility", postgresql_where=_ACTIVE),
    )

    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str | None] = mapped_column(String(120))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    # Hora local de la cámara, sin zona: las cámaras trampa no registran la zona.
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    still_installed: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    observations: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[Visibility] = mapped_column(
        enum_type(Visibility, "camera_visibility"),
        default=Visibility.PRIVATE,
        server_default=Visibility.PRIVATE,
    )
    previous_camera_station_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("camera_stations.id", ondelete="SET NULL")
    )
    # Bloqueo optimista: PATCH exige If-Match con esta versión (CB-15).
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
