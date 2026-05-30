import datetime
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import ScreenResult, TechnicalSignal
from app.db.session import SessionLocal
from app.screens.materializer import materialize_all_screens

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def backfill_screens():
    """
    Iterates over all unique dates in TechnicalSignal where timeframe='D'
    and materializes screen results for each date.
    """
    db: Session = SessionLocal()
    try:
        # Find all unique dates in the technical_signals table for Daily signals
        logger.info("Fetching unique daily signal dates...")
        dates_query = (
            db.query(func.date(TechnicalSignal.date))
            .filter(TechnicalSignal.timeframe == "D")
            .distinct()
            .order_by(func.date(TechnicalSignal.date).asc())
            .all()
        )
        dates = [d[0] for d in dates_query if d[0] is not None]

        total_dates = len(dates)
        logger.info(f"Found {total_dates} historical trading dates to materialize.")

        for i, target_date in enumerate(dates, 1):
            if isinstance(target_date, str):
                target_date = datetime.date.fromisoformat(target_date)

            # Check if this date already has results for the most sensitive screens.
            # If any of these are missing, we re-run the date.
            momentum_count = (
                db.query(func.count(ScreenResult.id))
                .filter(
                    ScreenResult.computed_at == target_date,
                    ScreenResult.screen_slug == "momentum-monsters",
                )
                .scalar()
            )

            (
                db.query(func.count(ScreenResult.id))
                .filter(
                    ScreenResult.computed_at == target_date,
                    ScreenResult.screen_slug == "mtf-confluence",
                )
                .scalar()
            )

            (
                db.query(func.count(ScreenResult.id))
                .filter(
                    ScreenResult.computed_at == target_date,
                    ScreenResult.screen_slug == "near-breakout",
                )
                .scalar()
            )

            # Since MTF and Near-Breakout can naturally be 0 on many days,
            # we also check if there are ANY results at all for the date.
            (
                db.query(func.count(ScreenResult.id))
                .filter(ScreenResult.computed_at == target_date)
                .scalar()
            )

            # We skip only if momentum-monsters exists.
            # (MTF and Near-Breakout might genuinely have 0 results, so we can't rely on them alone)
            if momentum_count > 0:
                logger.info(
                    f"[{i}/{total_dates}] Skipping {target_date} - already has results."
                )
                continue
            logger.info(
                f"[{i}/{total_dates}] Materializing screens for {target_date}..."
            )

            # The materializer internally deletes any existing rows for this date
            # so it will repopulate all screens for this date.
            materialize_all_screens(db, target_date=target_date)

    except Exception as e:
        logger.error(f"Error during historical materialization: {e}")
    finally:
        db.close()
        logger.info("Historical screen materialization complete.")


if __name__ == "__main__":
    backfill_screens()
