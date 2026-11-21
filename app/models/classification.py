"""Lotes de subida y clasificaciones: **una fila por archivo** (DD-1, FLUJOS_SISTEMA §3)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    BatchSource,
    BatchStatus,
    CaptureSource,
    Category,
    ClassificationSource,
    ClassificationStatus,
    CorrectionSource,
    MediaType,
    Rank,
    ValidationStatus,
)
from app.models.base import (
    Base,
    JSONDict,
    Owned,
    SoftDelete,
    Timestamps,
    UUIDPrimaryKey,
    enum_type,
    owner_xor,
)


class ClassificationBatch(UUIDPrimaryKey, Owned, SoftDelete, Timestamps, Base):
    """Un envío de N archivos a una cámara."""

    __tablename__ = "classification_batches"
    __table_args__ = (
        owner_xor(),
        CheckConstraint("expected_files BETWEEN 1 AND 500", name="expected_files_range"),
    )

    camera_station_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("camera_stations.id", ondelete="RESTRICT"), index=True
    )
    source: Mapped[BatchSource] = mapped_column(
        enum_type(BatchSource, "batch_source"), default=BatchSource.WEB
    )
    status: Mapped[BatchStatus] = mapped_column(
        enum_type(BatchStatus, "batch_status"), default=BatchStatus.OPEN
    )
    expected_files: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    done: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Classification(UUIDPrimaryKey, Owned, SoftDelete, Timestamps, Base):
    __tablename__ = "classifications"
    __table_args__ = (
        owner_xor(),
        CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="file_sha256_hex"),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence_range"
        ),
        # CB-50: el mismo archivo no se cuenta dos veces en la misma cámara.
        Index(
            "uq_classifications_camera_sha256_active",
            "camera_station_id",
            "file_sha256",
            unique=True,
            postgresql_where=text(
                "is_deleted = false AND status IN ('queued', 'processing', 'done')"
            ),
        ),
        Index("ix_classifications_sha256", "file_sha256"),  # CB-51: mismo archivo en otra cámara
        Index("ix_classifications_queue", "status", "queued_at"),
        Index("ix_classifications_camera_captured", "camera_station_id", "captured_at"),
    )

    # Origen
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("classification_batches.id", ondelete="RESTRICT"), index=True
    )
    client_index: Mapped[int | None] = mapped_column(Integer)
    camera_station_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("camera_stations.id", ondelete="RESTRICT")
    )
    source: Mapped[ClassificationSource] = mapped_column(
        enum_type(ClassificationSource, "classification_source"),
        default=ClassificationSource.WEB,
    )
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[MediaType] = mapped_column(enum_type(MediaType, "media_type"))
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    # Fecha de captura: hora local de la cámara, sin zona
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    captured_at_source: Mapped[CaptureSource | None] = mapped_column(
        enum_type(CaptureSource, "capture_source")
    )

    # Resultado de la IA
    category: Mapped[Category | None] = mapped_column(enum_type(Category, "category"))
    label_id: Mapped[str | None] = mapped_column(String(64), index=True)
    class_: Mapped[str | None] = mapped_column("class", String(100))
    order_: Mapped[str | None] = mapped_column("order", String(100))
    family: Mapped[str | None] = mapped_column(String(100))
    genus: Mapped[str | None] = mapped_column(String(100))
    species: Mapped[str | None] = mapped_column(String(100))
    scientific_name: Mapped[str | None] = mapped_column(String(200))
    common_name: Mapped[str | None] = mapped_column(String(200))
    rank: Mapped[Rank | None] = mapped_column(enum_type(Rank, "rank"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    label_raw: Mapped[str | None] = mapped_column(Text)
    alternatives: Mapped[list[JSONDict]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    frames_analyzed: Mapped[int | None] = mapped_column(Integer)

    # Evidencia (DD-3): solo la clave del storage, nunca rutas ni URLs
    evidence_key: Mapped[str | None] = mapped_column(String(255))
    evidence_frame_index: Mapped[int | None] = mapped_column(Integer)
    evidence_timestamp_seconds: Mapped[float | None] = mapped_column(Float)
    evidence_bbox: Mapped[list[float] | None] = mapped_column(JSONB)
    evidence_width: Mapped[int | None] = mapped_column(Integer)
    evidence_height: Mapped[int | None] = mapped_column(Integer)

    # Trazabilidad del modelo (sin geofence)
    model_detector: Mapped[str | None] = mapped_column(String(64))
    model_classifier: Mapped[str | None] = mapped_column(String(64))
    model_sampling: Mapped[str | None] = mapped_column(String(128))
    pipeline_version: Mapped[str | None] = mapped_column(String(32))
    low_evidence: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    truncated_at_seconds: Mapped[float | None] = mapped_column(Float)

    # Procesamiento (cola)
    status: Mapped[ClassificationStatus] = mapped_column(
        enum_type(ClassificationStatus, "classification_status"),
        default=ClassificationStatus.QUEUED,
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    warnings: Mapped[list[JSONDict]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    tmp_key: Mapped[str | None] = mapped_column(String(255))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Validación humana
    validation_status: Mapped[ValidationStatus] = mapped_column(
        enum_type(ValidationStatus, "validation_status"),
        default=ValidationStatus.UNVALIDATED,
        server_default=ValidationStatus.UNVALIDATED,
    )
    repeat_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("classifications.id", ondelete="SET NULL")
    )
    burst_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correction_source: Mapped[CorrectionSource | None] = mapped_column(
        enum_type(CorrectionSource, "correction_source")
    )
    corrected_label_id: Mapped[str | None] = mapped_column(String(64))
    corrected_class: Mapped[str | None] = mapped_column(String(100))
    corrected_order: Mapped[str | None] = mapped_column(String(100))
    corrected_family: Mapped[str | None] = mapped_column(String(100))
    corrected_genus: Mapped[str | None] = mapped_column(String(100))
    corrected_species: Mapped[str | None] = mapped_column(String(100))
    corrected_scientific_name: Mapped[str | None] = mapped_column(String(200))
    corrected_common_name: Mapped[str | None] = mapped_column(String(200))
    corrected_rank: Mapped[Rank | None] = mapped_column(enum_type(Rank, "corrected_rank"))
    suggested_name: Mapped[str | None] = mapped_column(String(200))
    validated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_notes: Mapped[str | None] = mapped_column(Text)
    validation_history: Mapped[list[JSONDict]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
