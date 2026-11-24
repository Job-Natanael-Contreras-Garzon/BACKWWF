"""0004 · Cambio obligatorio de contraseña (BE-50, SEC-11).

Revision ID: 0004
Revises: 0003

``users.must_change_password``: la cuenta admin creada (o recuperada) por CLI tiene una
contraseña temporal y debe cambiarla antes de usar la API (``PASSWORD_CHANGE_REQUIRED``).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
