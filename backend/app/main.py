import datetime
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.cache import response_cache
from app.db import session as db_session
from app.db.models import PipelineRun
from app.pipeline.ohlcv_cache import OHLCVCache
from app.pipeline.orchestrator import cleanup_zombie_runs
from app.routers import (
    backtest,
    dashboard,
    journal,
    paper_trading,
    paper_v2,
    reports,
    screener,
    screens,
    stocks,
    watchlist,
)

_ohlcv_cache = OHLCVCache()


# Configure Logging
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db = db_session.SessionLocal()
    try:
        cleanup_zombie_runs(db)
    finally:
        db.close()

    logger.info("Application started")
    yield
    # Shutdown
    logger.info("Application shutdown")


app = FastAPI(title="Stock AI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api")
app.include_router(screener.router)
app.include_router(screens.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(paper_trading.router, prefix="/api")
app.include_router(paper_v2.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(journal.router, prefix="/api")
app.include_router(stocks.router, prefix="/api")
app.include_router(reports.router)


def db_query_pipeline_run(db):
    """Helper for health check and testing."""
    return db.query(PipelineRun).order_by(PipelineRun.timestamp.desc()).first()


@app.get("/api/health")
def health_check():
    db = db_session.SessionLocal()
    db_status = "ok"
    pipeline_info = {"last_status": "unknown", "data_age_hours": 0, "is_stale": True}

    try:
        # DB Check with 2s timeout
        db.execute(text("SELECT 1").execution_options(timeout=2.0))
    except Exception as e:
        logger.error(f"Health check DB error: {e}")
        db_status = "error"

    if db_status == "ok":
        try:
            run = db_query_pipeline_run(db)
            if run:
                age_delta = datetime.datetime.now(datetime.timezone.utc) - run.timestamp
                data_age_hours = round(age_delta.total_seconds() / 3600.0, 1)
                pipeline_info = {
                    "last_status": run.status,
                    "data_age_hours": data_age_hours,
                    "is_stale": data_age_hours > 26,
                }
        except Exception as e:
            logger.error(f"Health check Pipeline status error: {e}")
            # We don't fail the whole DB check if just one query fails, but maybe we should?
            # For now, we'll just keep the default pipeline_info.

    db.close()

    # Overall Status
    status = "ok"
    if db_status == "error":
        status = "error"
    elif pipeline_info["is_stale"]:
        status = "degraded"

    return {
        "status": status,
        "db": db_status,
        "cache": response_cache.stats(),
        "ohlcv_cache": _ohlcv_cache.stats(),
        "pipeline": pipeline_info,
        "version": "2.1.0",
    }
