import logging
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import SessionLocal
from app.db.models import TechnicalSignal

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def backfill_rs_ranks():
    """
    Iterates over all historical dates in TechnicalSignal and computes
    RS percentile ranks (rs_score) for each date.
    
    This is necessary for screens like 'momentum-monsters' which depend on RS rank.
    """
    db: Session = SessionLocal()
    try:
        # Find all unique dates where timeframe is 'D'
        logger.info("Fetching unique dates from technical_signals...")
        dates_query = (
            db.query(func.date(TechnicalSignal.date))
            .filter(TechnicalSignal.timeframe == 'D')
            .distinct()
            .order_by(func.date(TechnicalSignal.date).desc())
            .all()
        )
        dates = [d[0] for d in dates_query if d[0] is not None]
        
        total_dates = len(dates)
        logger.info(f"Found {total_dates} dates to process.")
        
        for i, target_date in enumerate(dates, 1):
            # Check if this date already has RS scores (resumable)
            # We check if more than 10% of signals have rs_score to determine if it's done
            total_signals = db.query(func.count(TechnicalSignal.id)).filter(
                func.date(TechnicalSignal.date) == target_date,
                TechnicalSignal.timeframe == 'D'
            ).scalar()
            
            if total_signals == 0:
                continue
                
            done_count = db.query(func.count(TechnicalSignal.id)).filter(
                func.date(TechnicalSignal.date) == target_date,
                TechnicalSignal.timeframe == 'D',
                TechnicalSignal.rs_score.isnot(None)
            ).scalar()
            
            if done_count > (total_signals * 0.5):
                logger.info(f"[{i}/{total_dates}] Skipping {target_date} - already has {done_count}/{total_signals} RS scores.")
                continue
            
            logger.info(f"[{i}/{total_dates}] Computing RS ranks for {target_date} ({total_signals} symbols)...")
            
            # Fetch all signals for this date with momentum_12m
            signals = (
                db.query(TechnicalSignal.id, TechnicalSignal.momentum_12m)
                .filter(
                    func.date(TechnicalSignal.date) == target_date,
                    TechnicalSignal.timeframe == 'D',
                    TechnicalSignal.momentum_12m.isnot(None)
                )
                .all()
            )
            
            if not signals:
                logger.warning(f"  -> No signals with 12m momentum found for {target_date}.")
                continue
                
            # Sort by momentum_12m (ascending for percentile calculation)
            # Percentile = (Rank / Count) * 100
            # A higher momentum gets a higher percentile.
            sorted_signals = sorted(signals, key=lambda x: x.momentum_12m)
            count = len(sorted_signals)
            
            updates = []
            for rank_idx, s in enumerate(sorted_signals):
                # rank is 1-based
                percentile = ((rank_idx + 1) / count) * 100
                updates.append({"id": s.id, "rs_score": percentile})
                
            # Bulk update
            if updates:
                db.bulk_update_mappings(TechnicalSignal, updates)
                db.commit()
                logger.info(f"  -> Successfully updated {len(updates)} RS scores.")
            
    except Exception as e:
        db.rollback()
        logger.error(f"Error during RS backfill: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        db.close()
        logger.info("Historical RS backfill complete.")

if __name__ == "__main__":
    backfill_rs_ranks()
