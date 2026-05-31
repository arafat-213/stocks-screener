"""add alert_logs table

Revision ID: a36b9de49fa6
Revises: db96f22308eb
Create Date: 2026-05-24 14:00:36.023685

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a36b9de49fa6"
down_revision: Union[str, Sequence[str], None] = "db96f22308eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    if "alert_logs" not in inspector.get_table_names():
        op.create_table(
            "alert_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("symbol", sa.String(), nullable=False),
            sa.Column("signal_date", sa.Date(), nullable=False),
            sa.Column("alert_type", sa.String(), nullable=False),
            sa.Column("quality_tier", sa.String(length=1), nullable=True),
            sa.Column("entry_score", sa.Float(), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("email_id", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("symbol", "signal_date", "alert_type"),
        )
        op.create_index(
            "ix_alert_logs_sent_at", "alert_logs", ["sent_at"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    if "alert_logs" in inspector.get_table_names():
        op.drop_index("ix_alert_logs_sent_at", table_name="alert_logs")
        op.drop_table("alert_logs")
