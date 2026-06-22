import logging

from app.backtest.engine import run_backtest as execute_backtest_engine
from app.core.celery_app import celery_app
from app.core.trading_config import UnifiedTradingConfig as BacktestConfig
from app.db.session import SessionLocal
from app.pipeline.cleanup import run_cleanup
from app.pipeline.orchestrator import run_pipeline

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.execute_backtest_task")
def execute_backtest_task(run_id: str, config_dict: dict):
    logger.info(f"Starting backtest task (run_id={run_id})")
    db = SessionLocal()
    try:
        # Reconstruct config object from dict using robust helper
        config = BacktestConfig.from_dict(config_dict)
        execute_backtest_engine(db, run_id, config)
    except Exception as e:
        logger.error(f"Backtest task {run_id} failed: {e}")
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.execute_pipeline_task")
def execute_pipeline_task(limit: int | None = None, resume_run_id: str | None = None):
    logger.info(
        f"Starting pipeline task (limit={limit}, resume_run_id={resume_run_id})"
    )
    db = SessionLocal()
    try:
        run_pipeline(db, limit=limit, resume_run_id=resume_run_id)
    except Exception as e:
        logger.error(f"Pipeline task failed: {e}")
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.execute_paper_daily_task")
def execute_paper_daily_task(process_date: str | None = None):
    """Daily post-close S3 paper job (11 §4a/§4b/§4c).

    Date-parameterized, ordered replay: appends bhavcopy through the target date
    (inception-anchored, §5a corrected), then processes every unprocessed trading day in
    ascending order (so a backfilled gap reproduces continuous operation, §7.2). On each
    month-end it runs the shadow-parity check and HALTS the run on a break (11 §8/§7.1).
    """
    import datetime as _dt

    import pandas as pd

    from app.backtest_v2 import benchmark
    from app.data.bhavcopy import incremental, store
    from app.paper_v2 import alerter, live_engine, parity

    target = (
        _dt.date.fromisoformat(process_date)
        if process_date
        else _dt.datetime.now(_dt.timezone.utc).astimezone().date()
    )
    logger.info("Starting S3 paper daily task (target=%s)", target)

    db = SessionLocal()
    try:
        # 1. Append bhavcopy through target via the existing v2 pipeline (§5a/§5b/§5d).
        incremental.incremental_append(target)
        prices = store.read_prices_adjusted()
        prices["date"] = pd.to_datetime(prices["date"])
        inception = prices["date"].min().date()
        index_prices = benchmark.load_price_index(inception, target)

        pf = live_engine.get_or_create_book(db)

        # 2. Ordered replay of every CONFIRMED unprocessed trading day (§4c). The latest
        #    stored day is an unconfirmed month-end (no successor yet) and is held back
        #    until the next run confirms it — holiday-proof, fidelity-neutral (§7.2).
        cal = sorted(d.date() for d in prices["date"].drop_duplicates())
        to_process = live_engine.confirmed_replay_days(
            cal, pf.last_processed_date, target
        )
        for d in to_process:
            report = live_engine.process_day(db, pf.id, prices, index_prices, d)
            if report.skipped:
                continue
            alerter.emit_alerts(report)
            if report.is_rebalance:
                par = parity.shadow_parity(db, pf.id, prices, index_prices, d)
                logger.info(par.summary)
                if not par.passed:
                    raise RuntimeError(
                        f"PARITY BREAK on {d}: {par.summary} — halting (11 §8); "
                        "the 6-month clock resets per §7.1."
                    )
        logger.info("S3 paper daily task done: processed %d day(s)", len(to_process))
    except Exception as e:
        logger.error(f"Paper daily task failed: {e}")
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.execute_cleanup_task")
def execute_cleanup_task():
    logger.info("Starting scheduled cleanup task")
    db = SessionLocal()
    try:
        run_cleanup(db)
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")
        raise
    finally:
        db.close()
