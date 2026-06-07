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
