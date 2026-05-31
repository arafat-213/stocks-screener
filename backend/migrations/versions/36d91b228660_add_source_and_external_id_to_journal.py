"""add_source_and_external_id_to_journal

Revision ID: 36d91b228660
Revises: ebe325b82d9e
Create Date: 2026-05-30 09:44:20.797536

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "36d91b228660"
down_revision: Union[str, Sequence[str], None] = "ebe325b82d9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    columns = [col["name"] for col in inspector.get_columns("trade_journal")]

    if "source" not in columns:
        op.add_column(
            "trade_journal",
            sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        )
    if "external_id" not in columns:
        op.add_column(
            "trade_journal", sa.Column("external_id", sa.Integer(), nullable=True)
        )

    op.alter_column(
        "trade_journal",
        "stop_loss",
        existing_type=sa.DOUBLE_PRECISION(precision=53),
        nullable=True,
    )
    op.alter_column(
        "trade_journal",
        "target",
        existing_type=sa.DOUBLE_PRECISION(precision=53),
        nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "trade_journal",
        "target",
        existing_type=sa.DOUBLE_PRECISION(precision=53),
        nullable=False,
    )
    op.alter_column(
        "trade_journal",
        "stop_loss",
        existing_type=sa.DOUBLE_PRECISION(precision=53),
        nullable=False,
    )
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    columns = [col["name"] for col in inspector.get_columns("trade_journal")]
    if "external_id" in columns:
        op.drop_column("trade_journal", "external_id")
    if "source" in columns:
        op.drop_column("trade_journal", "source")
