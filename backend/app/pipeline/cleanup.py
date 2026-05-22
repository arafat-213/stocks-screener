import logging
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import delete, and_, func, select
from app.db.models import (
    TechnicalSignal, FundamentalData, PipelineError, PipelineCheckpoint, MarketSnapshot, ScreenResult, BacktestRun, BacktestTrade, PipelineRun
)

logger = logging.getLogger(__name__)

def run_cleanup(db: Session) -> dict:
    """
    Deletes stale rows across all accumulating tables.
    Safe to run daily after pipeline completion.
    Returns counts of deleted rows per table.
    """
    now = datetime.datetime.utcnow()
    today = datetime.date.today()
    summary = {}

    # 1. TechnicalSignal: keep only latest 90 days of daily signals.
    # Weekly/Monthly are lightweight — keep 2 years.
    cutoff_daily = now - datetime.timedelta(days=90)
    cutoff_weekly = now - datetime.timedelta(days=730)
    cutoff_monthly = now - datetime.timedelta(days=730)

    for tf, cutoff in [('D', cutoff_daily), ('W', cutoff_weekly), ('M', cutoff_monthly)]:
        result = db.execute(
            delete(TechnicalSignal).where(
                and_(
                    TechnicalSignal.timeframe == tf,
                    TechnicalSignal.date < cutoff,
                )
            )
        )
        summary[f'technical_signals_{tf}'] = result.rowcount

    # 2. FundamentalData: keep only the latest snapshot per symbol.
    # We never use historical snapshots — only the most recent values matter.
    # Safer approach: delete anything older than 14 days
    fund_cutoff = now - datetime.timedelta(days=14)
    result = db.execute(
        delete(FundamentalData).where(FundamentalData.date < fund_cutoff)
    )
    summary['fundamental_data'] = result.rowcount

    # 3. PipelineError: keep last 30 days
    result = db.execute(
        delete(PipelineError).where(
            PipelineError.occurred_at < now - datetime.timedelta(days=30)
        )
    )
    summary['pipeline_errors'] = result.rowcount

    # 4. PipelineCheckpoint: keep only checkpoints for runs that aren't 'running'
    # (completed/failed runs don't need their checkpoints)
    stale_runs = (
        select(PipelineRun.run_id)
        .where(
            and_(
                PipelineRun.status.in_(['complete', 'failed', 'stopped']),
                PipelineRun.timestamp < now - datetime.timedelta(days=7),
            )
        )
        .scalar_subquery()
    )
    result = db.execute(
        delete(PipelineCheckpoint).where(PipelineCheckpoint.run_id.in_(stale_runs))
    )
    summary['pipeline_checkpoints'] = result.rowcount

    # 5. MarketSnapshot: keep last 90 days
    result = db.execute(
        delete(MarketSnapshot).where(
            MarketSnapshot.date < today - datetime.timedelta(days=90)
        )
    )
    summary['market_snapshots'] = result.rowcount

    # 6. ScreenResult: keep last 7 days only (used for "latest run" lookups)
    result = db.execute(
        delete(ScreenResult).where(
            ScreenResult.computed_at < today - datetime.timedelta(days=7)
        )
    )
    summary['screen_results'] = result.rowcount

    # 7. BacktestTrade: delete trades for failed/old runs (older than 60 days)
    old_runs = (
        select(BacktestRun.run_id)
        .where(
            and_(
                BacktestRun.status.in_(['failed']),
            )
        )
        .scalar_subquery()
    )
    result = db.execute(
        delete(BacktestTrade).where(BacktestTrade.run_id.in_(old_runs))
    )
    summary['backtest_trades_failed_runs'] = result.rowcount

    # Delete trades for successful runs older than 60 days (keep metrics, drop raw trades)
    old_complete_runs = (
        select(BacktestRun.run_id)
        .where(
            and_(
                BacktestRun.status == 'complete',
                BacktestRun.created_at < now - datetime.timedelta(days=60),
            )
        )
        .scalar_subquery()
    )
    result = db.execute(
        delete(BacktestTrade).where(BacktestTrade.run_id.in_(old_complete_runs))
    )
    summary['backtest_trades_old_runs'] = result.rowcount

    db.commit()
    total = sum(summary.values())
    logger.info("Cleanup complete. Deleted %d total rows: %s", total, summary)
    return summary
