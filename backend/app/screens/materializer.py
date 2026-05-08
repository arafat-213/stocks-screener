import logging
import datetime
from sqlalchemy.orm import Session
from app.db.models import ScreenResult
from app.screens.registry import SCREEN_REGISTRY

logger = logging.getLogger(__name__)

def materialize_all_screens(db: Session):
    """
    Truncates the screen_results table and runs all registered screen functions,
    persisting the results for fast API retrieval.
    """
    logger.info("Starting screen materialization")
    start_time = datetime.datetime.now()
    
    try:
        # 1. Truncate existing results (latest-only policy)
        db.query(ScreenResult).delete()
        db.commit()
        
        # 2. Run each screen and save results
        total_results = 0
        for slug, meta in SCREEN_REGISTRY.items():
            try:
                logger.info(f"Running screen: {slug}")
                results = meta['fn'](db)
                
                for rank, item in enumerate(results, start=1):
                    # Handle tuples (symbol, score), dicts, or SQLAlchemy objects
                    if isinstance(item, tuple):
                        symbol = item[0]
                        score = item[1] if len(item) > 1 else 0.0
                        timeframe = 'D'
                    elif isinstance(item, dict):
                        symbol = item.get('symbol')
                        score = item.get('score', 0.0)
                        timeframe = item.get('timeframe', 'D')
                    else:
                        symbol = getattr(item, 'symbol', None)
                        score = getattr(item, 'entry_score', 0.0)
                        timeframe = getattr(item, 'timeframe', 'D')

                    if not symbol:
                        continue

                    res = ScreenResult(
                        screen_slug=slug,
                        symbol=symbol,
                        timeframe=timeframe,
                        rank=rank,
                        score_used=float(score) if score is not None else 0.0,
                        computed_at=datetime.datetime.utcnow()
                    )
                    db.add(res)
                    total_results += 1
                
                db.commit()
                logger.info(f"Materialized {len(results)} results for {slug}")
                
            except Exception as e:
                logger.error(f"Failed to materialize screen {slug}: {e}")
                db.rollback()
                
        duration = (datetime.datetime.now() - start_time).total_seconds()
        logger.info(f"Screen materialization complete. Total rows: {total_results}. Duration: {duration:.2f}s")
        
    except Exception as e:
        logger.error(f"Critical failure in materializer: {e}")
        db.rollback()
