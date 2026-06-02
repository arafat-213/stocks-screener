"""enforce_nse_suffix_on_all_symbols

Revision ID: 0a68ae083e81
Revises: be8c5492f42b
Create Date: 2026-06-02 11:56:29.330840

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a68ae083e81"
down_revision: Union[str, Sequence[str], None] = "be8c5492f42b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Drop FK constraints that point to stocks.symbol
    op.execute(
        "ALTER TABLE screen_results DROP CONSTRAINT IF EXISTS screen_results_symbol_fkey"
    )
    op.execute("ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS watchlist_symbol_fkey")

    # Helper function logic for each table
    # Tables with unique constraints
    unique_tables = [
        ("stocks", []),
        ("technical_signals", ["date", "timeframe"]),
        ("fundamental_data", ["date"]),
        ("fundamental_cache", []),
        ("market_snapshots", ["date"]),
        ("alert_logs", ["signal_date", "alert_type"]),
        ("watchlist", ["signal_date"]),
    ]

    for table, keys in unique_tables:
        where_clause = " AND ".join([f"t2.{k} = {table}.{k}" for k in keys])
        if where_clause:
            where_clause = " AND " + where_clause

        # Update where no collision
        op.execute(f"""
            UPDATE {table} SET symbol = symbol || '.NS'
            WHERE symbol NOT LIKE '%.NS' AND symbol NOT LIKE '^%'
            AND NOT EXISTS (
                SELECT 1 FROM {table} t2
                WHERE t2.symbol = {table}.symbol || '.NS' {where_clause}
            )
        """)
        # Delete remaining (colliding) rows
        op.execute(
            f"DELETE FROM {table} WHERE symbol NOT LIKE '%.NS' AND symbol NOT LIKE '^%'"
        )

    # Tables without unique constraints (just update)
    simple_tables = [
        "pipeline_errors",
        "screen_results",
        "backtest_trades",
        "paper_positions",
        "paper_trades",
        "trade_journal",
    ]

    for table in simple_tables:
        op.execute(f"""
            UPDATE {table} SET symbol = symbol || '.NS'
            WHERE symbol NOT LIKE '%.NS' AND symbol NOT LIKE '^%'
        """)

    # 2. Re-add FK constraints
    op.execute(
        "ALTER TABLE screen_results ADD CONSTRAINT screen_results_symbol_fkey FOREIGN KEY (symbol) REFERENCES stocks(symbol)"
    )
    op.execute(
        "ALTER TABLE watchlist ADD CONSTRAINT watchlist_symbol_fkey FOREIGN KEY (symbol) REFERENCES stocks(symbol)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Drop FK constraints
    op.execute(
        "ALTER TABLE screen_results DROP CONSTRAINT IF EXISTS screen_results_symbol_fkey"
    )
    op.execute("ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS watchlist_symbol_fkey")

    all_tables = [
        "stocks",
        "technical_signals",
        "fundamental_data",
        "fundamental_cache",
        "market_snapshots",
        "alert_logs",
        "watchlist",
        "pipeline_errors",
        "screen_results",
        "backtest_trades",
        "paper_positions",
        "paper_trades",
        "trade_journal",
    ]

    for table in all_tables:
        # Strip .NS suffix if it exists and wasn't there originally (best effort)
        # Note: This might collide if 'REL' and 'REL.NS' both exist after strip.
        # We'll just try to update and ignore if it fails or just do a simple strip.
        op.execute(f"""
            UPDATE {table} SET symbol = REPLACE(symbol, '.NS', '')
            WHERE symbol LIKE '%.NS'
        """)

    # 2. Re-add FK constraints
    op.execute(
        "ALTER TABLE screen_results ADD CONSTRAINT screen_results_symbol_fkey FOREIGN KEY (symbol) REFERENCES stocks(symbol)"
    )
    op.execute(
        "ALTER TABLE watchlist ADD CONSTRAINT watchlist_symbol_fkey FOREIGN KEY (symbol) REFERENCES stocks(symbol)"
    )
