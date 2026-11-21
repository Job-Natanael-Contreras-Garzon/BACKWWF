"""0003 · Panel admin (HU-15a).

Revision ID: 0003
Revises: 0002

- ``admin_audit_log.action`` acepta ``password_reset_link`` (enlace manual de reset, CB-76).
- ``anon_sessions`` con borrado lógico (el admin puede borrar y restaurar una sesión anónima).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = (
    "soft_delete", "restore", "deactivate_user", "reactivate_user", "export", "update_setting",
)
_NEW = (*_OLD, "password_reset_link")


def _action_check(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_admin_audit_log_admin_action"), "admin_audit_log", type_="check")
    listed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint("admin_action", "admin_audit_log", f"action IN ({listed})")


def upgrade() -> None:
    _action_check(_NEW)
    op.add_column(
        "anon_sessions",
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("anon_sessions", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("anon_sessions", sa.Column("deleted_by", sa.Uuid()))
    op.add_column("anon_sessions", sa.Column("deleted_reason", sa.Text()))


def downgrade() -> None:
    for column in ("deleted_reason", "deleted_by", "deleted_at", "is_deleted"):
        op.drop_column("anon_sessions", column)
    op.execute("DELETE FROM admin_audit_log WHERE action = 'password_reset_link'")
    _action_check(_OLD)
