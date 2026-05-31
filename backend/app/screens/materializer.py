import datetime
import logging

from sqlalchemy.orm import Session

from app.db.models import ScreenResult
from app.screens.cache import screen_cache
from app.screens.registry import SCREEN_REGISTRY

logger = logging.getLogger(__name__)


def materialize_all_screens(db: Session, target_date: datetime.date = None):
    """
    Truncates the screen_results table and runs all registered screen functions,
    persisting the results for fast API retrieval.
    """
    logger.info("Starting screen materialization")
    start_time = datetime.datetime.now(datetime.timezone.utc)
    today = target_date if target_date else datetime.date.today()

    try:
        # 1. Delete existing results for today to allow re-runs without duplication
        db.query(ScreenResult).filter(ScreenResult.computed_at == today).delete()
        db.commit()

        # 2. Run each screen and save results
        total_results = 0
        for slug, meta in SCREEN_REGISTRY.items():
            try:
                logger.info(f"Running screen: {slug}")
                results = meta["fn"](db, target_date=target_date)

                for rank, item in enumerate(results, start=1):
                    # Handle tuples (symbol, score, quality_tier), dicts, or SQLAlchemy objects
                    quality_tier = None
                    if isinstance(item, tuple):
                        symbol = item[0]
                        score = item[1] if len(item) > 1 else 0.0
                        quality_tier = item[2] if len(item) > 2 else None
                        timeframe = "D"
                    elif isinstance(item, dict):
                        symbol = item.get("symbol")
                        score = item.get("score", 0.0)
                        quality_tier = item.get("quality_tier")
                        timeframe = item.get("timeframe", "D")
                    else:
                        symbol = getattr(item, "symbol", None)
                        score = getattr(item, "entry_score", 0.0)
                        quality_tier = getattr(item, "quality_tier", None)
                        timeframe = getattr(item, "timeframe", "D")

                    if not symbol:
                        continue

                    res = ScreenResult(
                        screen_slug=slug,
                        symbol=symbol,
                        timeframe=timeframe,
                        rank=rank,
                        score_used=float(score) if score is not None else 0.0,
                        quality_tier=quality_tier,
                        computed_at=today,
                    )
                    db.add(res)
                    total_results += 1

                db.commit()
                logger.info(f"Materialized {len(results)} results for {slug}")

            except Exception as e:
                logger.error(f"Failed to materialize screen {slug}: {e}")
                db.rollback()

        duration = (
            datetime.datetime.now(datetime.timezone.utc) - start_time
        ).total_seconds()
        logger.info(
            f"Screen materialization complete. Total rows: {total_results}. Duration: {duration:.2f}s"
        )

        # Clear cache so next API requests fetch fresh database results
        screen_cache.invalidate()

    except Exception as e:
        logger.error(f"Critical failure in materializer: {e}")
        db.rollback()
