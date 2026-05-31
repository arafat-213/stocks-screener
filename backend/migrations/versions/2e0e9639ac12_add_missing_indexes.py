"""add_missing_indexes

Revision ID: 2e0e9639ac12
Revises: ece6eaedeaec
Create Date: 2026-05-22 12:29:18.214503

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e0e9639ac12"
down_revision: Union[str, Sequence[str], None] = "bb53787bd712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())

    # Backtest trades indexes
    bt_indexes = [idx["name"] for idx in inspector.get_indexes("backtest_trades")]
    if "ix_bt_run_id" not in bt_indexes:
        op.create_index("ix_bt_run_id", "backtest_trades", ["run_id"], unique=False)
    if "ix_bt_run_id_exit_reason" not in bt_indexes:
        op.create_index(
            "ix_bt_run_id_exit_reason",
            "backtest_trades",
            ["run_id", "exit_reason"],
            unique=False,
        )

    # Pipeline errors indexes
    pe_indexes = [idx["name"] for idx in inspector.get_indexes("pipeline_errors")]
    if "ix_pe_run_id" not in pe_indexes:
        op.create_index("ix_pe_run_id", "pipeline_errors", ["run_id"], unique=False)

    # Technical signals indexes
    ts_indexes = [idx["name"] for idx in inspector.get_indexes("technical_signals")]
    if "ix_ts_screener_core" not in ts_indexes:
        op.create_index(
            "ix_ts_screener_core",
            "technical_signals",
            ["timeframe", "date", "above_200ema", "is_bullish"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())

    ts_indexes = [idx["name"] for idx in inspector.get_indexes("technical_signals")]
    if "ix_ts_screener_core" in ts_indexes:
        op.drop_index("ix_ts_screener_core", table_name="technical_signals")
    if "ix_ts_symbol_timeframe_date" in ts_indexes:
        op.drop_index("ix_ts_symbol_timeframe_date", table_name="technical_signals")
    if "ix_ts_timeframe_date" in ts_indexes:
        op.drop_index("ix_ts_timeframe_date", table_name="technical_signals")

    pe_indexes = [idx["name"] for idx in inspector.get_indexes("pipeline_errors")]
    if "ix_pe_run_id" in pe_indexes:
        op.drop_index("ix_pe_run_id", table_name="pipeline_errors")

    bt_indexes = [idx["name"] for idx in inspector.get_indexes("backtest_trades")]
    if "ix_bt_run_id_exit_reason" in bt_indexes:
        op.drop_index("ix_bt_run_id_exit_reason", table_name="backtest_trades")
    if "ix_bt_run_id" in bt_indexes:
        op.drop_index("ix_bt_run_id", table_name="backtest_trades")
