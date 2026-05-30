import datetime
import logging

from sqlalchemy.orm import Session

from app.db.models import TechnicalSignal
from app.pipeline.fetcher import fetch_stock_data

logger = logging.getLogger(__name__)


def compute_rs_ranks(db: Session, signal_date: datetime.date):
    """
    Computes RS percentile rank based on 12-month momentum against a benchmark.
    Uses bulk update for efficiency.
    """
    RS_BENCHMARK_CANDIDATES = ["^CRSLDX", "^NSEI"]  # Nifty 500, Nifty 50
    benchmark_symbol = None
    benchmark_return = 0.0

    logger.info("Resolving RS benchmark candidate...")
    for candidate in RS_BENCHMARK_CANDIDATES:
        hist, _ = fetch_stock_data(candidate, append_ns=False, period="2y")
        if hist is not None and len(hist) >= 252:
            benchmark_symbol = candidate
            # 12-month return: (price_now / price_252_bars_ago - 1) * 100
            benchmark_return = (
                hist["Close"].iloc[-1] / hist["Close"].iloc[-252] - 1
            ) * 100
            logger.info(
                f"Selected RS benchmark: {benchmark_symbol} with 12m return: {benchmark_return:.2f}%"
            )
            break

    if not benchmark_symbol:
        logger.warning(
            "No suitable RS benchmark found with enough history. Skipping RS computation."
        )
        return

    # Get all TechnicalSignals for signal_date and timeframe == 'D'
    signals = (
        db.query(TechnicalSignal)
        .filter(TechnicalSignal.date == signal_date, TechnicalSignal.timeframe == "D")
        .all()
    )

    if not signals:
        logger.info(f"No signals found for {signal_date} to compute RS ranks.")
        return

    # Filter signals that have momentum_12m
    valid_signals = [s for s in signals if s.momentum_12m is not None]
    if not valid_signals:
        logger.info("No signals with 12m momentum found.")
        return

    # Sort signals by excess return (momentum_12m - benchmark_return)
    # Percentile = (Rank / Count) * 100
    valid_signals.sort(key=lambda x: (x.momentum_12m - benchmark_return))
    count = len(valid_signals)

    updates = []
    for i, s in enumerate(valid_signals):
        rank = ((i + 1) / count) * 100
        updates.append({"id": s.id, "rs_score": rank})

    if updates:
        db.bulk_update_mappings(TechnicalSignal, updates)
        db.commit()
        logger.info(
            f"Successfully updated RS scores (percentile ranks) for {len(updates)} stocks."
        )
