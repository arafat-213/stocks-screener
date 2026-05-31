"""convert_to_timezone_aware

Revision ID: c918d2a71c95
Revises: 8f2ced134407
Create Date: 2026-05-30 16:57:15.915018

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c918d2a71c95"
down_revision: Union[str, Sequence[str], None] = "9cc7bd6f4a6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. TechnicalSignal
    op.alter_column(
        "technical_signals",
        "date",
        type_=sa.DateTime(timezone=True),
        postgresql_using="date AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "technical_signals",
        "scored_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="scored_at AT TIME ZONE 'UTC'",
    )

    # 2. FundamentalData
    op.alter_column(
        "fundamental_data",
        "date",
        type_=sa.DateTime(timezone=True),
        postgresql_using="date AT TIME ZONE 'UTC'",
    )

    # 3. FundamentalCache
    op.alter_column(
        "fundamental_cache",
        "retry_after",
        type_=sa.DateTime(timezone=True),
        postgresql_using="retry_after AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "fundamental_cache",
        "last_updated",
        type_=sa.DateTime(timezone=True),
        postgresql_using="last_updated AT TIME ZONE 'UTC'",
    )

    # 4. PipelineRun
    op.alter_column(
        "pipeline_runs",
        "timestamp",
        type_=sa.DateTime(timezone=True),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )

    # 5. PipelineCheckpoint
    op.alter_column(
        "pipeline_checkpoints",
        "started_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="started_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "pipeline_checkpoints",
        "completed_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="completed_at AT TIME ZONE 'UTC'",
    )

    # 6. PipelineError
    op.alter_column(
        "pipeline_errors",
        "occurred_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="occurred_at AT TIME ZONE 'UTC'",
    )

    # 7. BacktestRun
    op.alter_column(
        "backtest_runs",
        "created_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    # 8. PaperPortfolio
    op.alter_column(
        "paper_portfolio",
        "created_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    # 9. PaperPosition
    op.alter_column(
        "paper_positions",
        "opened_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="opened_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "paper_positions",
        "closed_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="closed_at AT TIME ZONE 'UTC'",
    )

    # 10. PaperTrade
    op.alter_column(
        "paper_trades",
        "closed_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="closed_at AT TIME ZONE 'UTC'",
    )

    # 11. AlertLog
    op.alter_column(
        "alert_logs",
        "sent_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="sent_at AT TIME ZONE 'UTC'",
    )

    # 12. TradeJournal
    op.alter_column(
        "trade_journal",
        "created_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "trade_journal",
        "created_at",
        type_=sa.DateTime(),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "alert_logs",
        "sent_at",
        type_=sa.DateTime(),
        postgresql_using="sent_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "paper_trades",
        "closed_at",
        type_=sa.DateTime(),
        postgresql_using="closed_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "paper_positions",
        "closed_at",
        type_=sa.DateTime(),
        postgresql_using="closed_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "paper_positions",
        "opened_at",
        type_=sa.DateTime(),
        postgresql_using="opened_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "paper_portfolio",
        "created_at",
        type_=sa.DateTime(),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "backtest_runs",
        "created_at",
        type_=sa.DateTime(),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "pipeline_errors",
        "occurred_at",
        type_=sa.DateTime(),
        postgresql_using="occurred_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "pipeline_checkpoints",
        "completed_at",
        type_=sa.DateTime(),
        postgresql_using="completed_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "pipeline_checkpoints",
        "started_at",
        type_=sa.DateTime(),
        postgresql_using="started_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "pipeline_runs",
        "timestamp",
        type_=sa.DateTime(),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "fundamental_cache",
        "last_updated",
        type_=sa.DateTime(),
        postgresql_using="last_updated AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "fundamental_cache",
        "retry_after",
        type_=sa.DateTime(),
        postgresql_using="retry_after AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "fundamental_data",
        "date",
        type_=sa.DateTime(),
        postgresql_using="date AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "technical_signals",
        "scored_at",
        type_=sa.DateTime(),
        postgresql_using="scored_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "technical_signals",
        "date",
        type_=sa.DateTime(),
        postgresql_using="date AT TIME ZONE 'UTC'",
    )
