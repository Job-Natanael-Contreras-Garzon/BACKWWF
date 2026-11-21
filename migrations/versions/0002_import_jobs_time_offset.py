"""0002 · Importación en el worker (D10) y corrección de hora de cámaras (#15d, D14).

Revision ID: 0002
Revises: 0001

- ``desktop_imports.status`` acepta ``processing`` y ``failed``.
- ``classifications.captured_at_original``: la fecha antes de corregir la hora (CB-18).
- ``camera_time_offsets``: auditoría de cada corrección (la hace el dueño, no el admin).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = ("preview", "completed", "cancelled", "expired")
_NEW = ("preview", "processing", "completed", "failed", "cancelled", "expired")


def _status_check(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_desktop_imports_import_status"), "desktop_imports", type_="check")
    listed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint("import_status", "desktop_imports", f"status IN ({listed})")


def upgrade() -> None:
    _status_check(_NEW)
    op.add_column(
        "classifications",
        sa.Column("captured_at_original", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_table(
        "camera_time_offsets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("camera_station_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("anon_session_id", sa.Uuid(), nullable=True),
        sa.Column("offset_seconds", sa.Integer(), nullable=False),
        sa.Column("from_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("to_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["camera_station_id"], ["camera_stations.id"],
            name=op.f("fk_camera_time_offsets_camera_station_id_camera_stations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"],
            name=op.f("fk_camera_time_offsets_actor_user_id_users"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["anon_session_id"], ["anon_sessions.id"],
            name=op.f("fk_camera_time_offsets_anon_session_id_anon_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_camera_time_offsets")),
    )
    op.create_index(
        op.f("ix_camera_time_offsets_camera_station_id"),
        "camera_time_offsets",
        ["camera_station_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_camera_time_offsets_camera_station_id"), "camera_time_offsets")
    op.drop_table("camera_time_offsets")
    op.drop_column("classifications", "captured_at_original")
    op.execute(
        "UPDATE desktop_imports SET status = 'expired' WHERE status IN ('processing', 'failed')"
    )
    _status_check(_OLD)
