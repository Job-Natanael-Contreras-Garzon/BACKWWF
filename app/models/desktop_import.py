import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ImportStatus
from app.models.base import Base, JSONDict, SoftDelete, Timestamps, UUIDPrimaryKey, enum_type


class DesktopImport(UUIDPrimaryKey, SoftDelete, Timestamps, Base):
    """Auditoría de FL-23. Importar exige cuenta: el dueño es siempre un usuario."""

    __tablename__ = "desktop_imports"
    __table_args__ = (
        CheckConstraint("package_sha256 ~ '^[0-9a-f]{64}$'", name="package_sha256_hex"),
        # CB-82: el mismo paquete no se importa dos veces en la misma cámara.
        Index(
            "uq_desktop_imports_camera_package_completed",
            "camera_station_id",
            "package_sha256",
            unique=True,
            postgresql_where=text("status = 'completed' AND is_deleted = false"),
        ),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    # Puede faltar en la vista previa: la cámara se crea al confirmar (create_camera=true).
    camera_station_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("camera_stations.id", ondelete="RESTRICT")
    )
    package_sha256: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[JSONDict] = mapped_column(JSONB)
    status: Mapped[ImportStatus] = mapped_column(
        enum_type(ImportStatus, "import_status"), default=ImportStatus.PREVIEW
    )
    counts: Mapped[JSONDict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    tmp_key: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
