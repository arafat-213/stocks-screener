import logging

import redis as _redis

from app.backtest.engine import run_backtest as execute_backtest_engine
from app.core.celery_app import celery_app, redis_url
from app.core.trading_config import UnifiedTradingConfig as BacktestConfig
from app.db.session import SessionLocal
from app.pipeline.cleanup import run_cleanup
from app.pipeline.orchestrator import run_pipeline

logger = logging.getLogger(__name__)

# Advisory lock for the paper daily task (CLAUDE.md Pipeline Law §1 / 11 §4).
# TTL auto-expires a stale lock left by a crashed process (zombie cleanup).
_PAPER_LOCK_KEY = "paper_daily_task_running"
_PAPER_LOCK_TTL = 7200  # 2 hours


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
    from zoneinfo import ZoneInfo

    import pandas as pd

    from app.backtest_v2 import benchmark
    from app.data.bhavcopy import incremental, store
    from app.paper_v2 import alerter, live_engine, parity

    # Concurrency guard: a beat fire that races a still-running replay must skip,
    # not corrupt the book. TTL auto-expires a lock left by a crashed process.
    _r = _redis.from_url(redis_url)
    if not _r.set(_PAPER_LOCK_KEY, "1", nx=True, ex=_PAPER_LOCK_TTL):
        logger.warning(
            "execute_paper_daily_task: another instance is already running — skipping "
            "(concurrency guard; lock TTL=%ds)",
            _PAPER_LOCK_TTL,
        )
        return

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

        # Go-live = the IST date the probation book was armed (11 §1/P11.2 warm-start
        # semantics). Days BEFORE it are the warm-start replay (inception → today's S3
        # holdings), NOT the counted probation. Two things are therefore gated to the
        # counted forward window (date >= go_live):
        #   * §2 shadow-parity (the fidelity deliverable P11.3 evaluates) — during a single
        #     continuous replay the live book and the shadow are the identical step_day
        #     sequence over the identical context, so warm-start parity is true by
        #     construction; gating also stops a NULL-start from running ~115 full shadow
        #     backtests (the second O(N²), P11.2 perf fix).
        #   * alerts — warm-start would otherwise email a rebalance preview + fills-executed
        #     for every historical month-end (~115×2 emails for 2017→today), pure inbox
        #     noise about trades that never happened live. Only forward days alert.
        go_live = pf.created_at.astimezone(ZoneInfo("Asia/Kolkata")).date()

        # 2. Ordered replay of every CONFIRMED unprocessed trading day (§4c). The latest
        #    stored day is an unconfirmed month-end (no successor yet) and is held back
        #    until the next run confirms it — holiday-proof, fidelity-neutral (§7.2).
        cal = sorted(d.date() for d in prices["date"].drop_duplicates())
        to_process = live_engine.confirmed_replay_days(
            cal, pf.last_processed_date, target
        )
        # Build the S3 engine context ONCE and reuse it across the whole replay (engine.run
        # does the same — ctx is immutable, step_day mutates only state). Hoisted out of the
        # per-day loop so the warm-start replay is O(days), not O(days²) (P11.2 perf fix).
        ctx = (
            live_engine.build_live_context(prices, index_prices)[0]
            if to_process
            else None
        )
        for d in to_process:
            report = live_engine.process_day(
                db, pf.id, prices, index_prices, d, ctx=ctx
            )
            if report.skipped:
                continue
            if d >= go_live:
                alerter.emit_alerts(report)
            if report.is_rebalance and d >= go_live:
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
        _r.delete(_PAPER_LOCK_KEY)


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
