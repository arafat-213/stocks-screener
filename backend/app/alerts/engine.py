# app/alerts/engine.py
import datetime
import logging

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.alerts.email import (
    build_exit_alert_email,
    build_signal_email,
    send_alert_email,
)
from app.core.trading_config import TREND_INITIATION, UnifiedTradingConfig
from app.db.models import (
    AlertLog,
    DailyDigestLog,
    ScreenResult,
    Stock,
    TechnicalSignal,
    TradeJournal,
)
from app.pipeline.ohlcv_cache import OHLCVCache
from app.pipeline.trade_setup import compute_trade_setup
from app.pipeline.utils import get_market_regime

logger = logging.getLogger(__name__)


def _compute_entry_status(close_price: float, ema21: float) -> tuple[str, float]:
    """Returns (entry_status, pct_above_ema21)."""
    if not close_price or not ema21 or ema21 == 0:
        return "unknown", 0.0

    pct = (close_price - ema21) / ema21 * 100
    if pct <= 3.0:
        status = "in_zone"
    elif pct <= 8.0:
        status = "extended"
    else:
        status = "chasing"
    return status, round(pct, 2)


def _already_alerted(
    db: Session, symbol: str, signal_date: datetime.date, alert_type: str
) -> bool:
    return (
        db.query(AlertLog)
        .filter_by(
            symbol=symbol,
            signal_date=signal_date,
            alert_type=alert_type,
        )
        .first()
        is not None
    )


def _log_alert(
    db: Session,
    symbol: str,
    signal_date: datetime.date,
    alert_type: str,
    quality_tier: str,
    entry_score: float,
    email_id: str | None,
):
    try:
        log = AlertLog(
            symbol=symbol,
            signal_date=signal_date,
            alert_type=alert_type,
            quality_tier=quality_tier,
            entry_score=entry_score,
            email_id=email_id,
        )
        db.add(log)
        db.commit()
    except IntegrityError:
        # Race condition — already logged by a concurrent run, safe to ignore
        db.rollback()


def get_new_signals_for_alert(
    db: Session,
    signal_date: datetime.date,
    config: UnifiedTradingConfig,
) -> tuple[list[dict], int]:
    """Scans for new actionable signals and returns (signals_to_alert, skipped_count)."""
    # Define signals to match based on config
    ema_signals = ["bullish_cross", "bullish_pullback"]

    query = db.query(TechnicalSignal, Stock).join(
        Stock, TechnicalSignal.symbol == Stock.symbol
    )

    if config.screen_signal_mode and config.screen_slug:
        query = query.join(
            ScreenResult,
            and_(
                TechnicalSignal.symbol == ScreenResult.symbol,
                func.date(TechnicalSignal.date) == ScreenResult.computed_at,
                ScreenResult.screen_slug == config.screen_slug,
            ),
        )

    query = query.filter(
        and_(
            func.date(TechnicalSignal.date) == signal_date,
            TechnicalSignal.timeframe == "D",
            TechnicalSignal.ema_signal.in_(ema_signals),
            TechnicalSignal.above_200ema,
            TechnicalSignal.rsi >= config.rsi_min,
            TechnicalSignal.rsi <= config.rsi_max,
            TechnicalSignal.momentum_12m > 0,
            TechnicalSignal.entry_score >= config.effective_score_threshold,
        )
    )

    # Signal Tier Filtering
    if config.min_signal_tier == 1:
        # Strict: Both volume breakout and Tier 1 ADX threshold must be met
        query = query.filter(
            and_(
                TechnicalSignal.volume_breakout,
                TechnicalSignal.adx >= config.tier1_adx_threshold,
            )
        )
    else:
        # Relaxed: Either volume breakout or base ADX threshold must be met (Tier 2)
        query = query.filter(
            or_(
                TechnicalSignal.volume_breakout,
                TechnicalSignal.adx >= config.min_adx,
            )
        )

    if config.require_consolidation:
        query = query.filter(TechnicalSignal.is_consolidating)

    candidates = query.all()

    if not candidates:
        return [], 0

    signals_to_alert = []
    skipped = 0

    for tech, stock in candidates:
        alert_type = f"{config.strategy_id}_signal"

        if _already_alerted(db, tech.symbol, signal_date, alert_type):
            skipped += 1
            continue

        if not tech.close_price or not tech.ema21_level:
            continue

        # Compute signal_tier from technical indicators only
        if tech.volume_breakout and (tech.adx or 0.0) >= config.tier1_adx_threshold:
            tier = 1
        elif tech.volume_breakout or (tech.adx or 0.0) >= config.min_adx:
            tier = 2
        else:
            tier = 3

        entry_status, pct_above_ema21 = _compute_entry_status(
            tech.close_price, tech.ema21_level
        )

        setup = compute_trade_setup(tech, config=config)
        stop_loss = setup["stop_loss"] if setup else None
        target_price = (
            setup["targets"][-1]["level"] if setup and setup.get("targets") else None
        )

        signals_to_alert.append(
            {
                "symbol": tech.symbol,
                "name": stock.name,
                "sector": stock.sector or "Unknown",
                "score": tech.entry_score,
                "signal_tier": tier,
                "alert_type": alert_type,
                "ema_signal": tech.ema_signal,
                "rsi": tech.rsi or 0.0,
                "adx": tech.adx or 0.0,
                "volume_breakout": tech.volume_breakout or False,
                "entry_status": entry_status,
                "pct_above_ema21": pct_above_ema21,
                "stop_loss": stop_loss,
                "target_price": target_price,
                "momentum_12m": tech.momentum_12m or 0.0,
                "close_price": tech.close_price,
                "ema21_level": tech.ema21_level,
            }
        )

    # Sort: tier 1 first, then by score descending
    signals_to_alert.sort(key=lambda x: (x["signal_tier"], -x["score"]))
    return signals_to_alert, skipped


def run_alert_cycle(
    db: Session,
    signal_date: datetime.date | None = None,
    config: UnifiedTradingConfig = None,
) -> dict:
    """
    Main entry point. Called after pipeline completes.
    Finds new actionable signals, deduplicates, and fires email.
    Returns summary dict for logging.
    """
    if config is None:
        config = TREND_INITIATION

    if signal_date is None:
        from app.screens.base import get_latest_signal_date

        signal_date = get_latest_signal_date(db, "D")

    logger.info(
        "alert_cycle: scanning signals for %s using strategy '%s'",
        signal_date,
        config.strategy_id,
    )
    regime_bullish = get_market_regime(db, signal_date)

    signals_to_alert, skipped = get_new_signals_for_alert(db, signal_date, config)

    if not signals_to_alert:
        logger.info(
            "alert_cycle: no candidates found or all already alerted (skipped=%d)",
            skipped,
        )
        return {
            "signals_found": skipped,
            "alerts_sent": 0,
            "skipped_duplicate": skipped,
        }

    # Build and send single batched email
    subject = (
        f"📊 [{config.strategy_id.upper()}] {len(signals_to_alert)} Stock Signal{'s' if len(signals_to_alert) > 1 else ''} "
        f"— {signal_date.strftime('%d %b %Y')}"
    )
    html = build_signal_email(signals_to_alert, str(signal_date), regime_bullish)
    email_id = send_alert_email(subject, html)

    # Log each signal to AlertLog
    for sig in signals_to_alert:
        _log_alert(
            db,
            symbol=sig["symbol"],
            signal_date=signal_date,
            alert_type=sig["alert_type"],
            quality_tier=None,
            entry_score=sig["score"],
            email_id=email_id,
        )

    logger.info(
        "alert_cycle: sent %d signals in 1 email (id=%s), skipped %d duplicates",
        len(signals_to_alert),
        email_id,
        skipped,
    )
    return {
        "signals_found": len(signals_to_alert) + skipped,
        "alerts_sent": len(signals_to_alert),
        "skipped_duplicate": skipped,
        "email_id": email_id,
        "regime_bullish": regime_bullish,
    }


def get_exit_alerts_for_date(
    db: Session, signal_date: datetime.date
) -> tuple[list[dict], int]:
    """Checks open positions and returns (alerts, positions_checked)."""
    open_positions = db.query(TradeJournal).filter_by(status="open").all()
    if not open_positions:
        return [], 0

    cache = OHLCVCache()
    alerts = []

    for pos in open_positions:
        # Fetch minimum data required for indicators (RSI_14 needs ~40-60 bars for convergence)
        df = cache.get(pos.symbol, period="60d")
        if df is None or df.empty:
            continue

        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)

        # Calculate only required indicator (RSI) to save CPU/memory
        df.ta.rsi(length=14, append=True)

        # Get today's bar
        today_rows = df[df.index.date == signal_date]
        if today_rows.empty:
            continue

        today_idx = df.index.get_loc(today_rows.index[0])
        row = df.iloc[today_idx]
        prev_row = df.iloc[today_idx - 1] if today_idx > 0 else None

        day_low = float(row["Low"])
        day_high = float(row["High"])
        current = float(row["Close"])
        rsi = float(row.get("RSI_14", 0))

        unrealised_pct = (current - pos.entry_price) / pos.entry_price * 100
        distance_to_stop_pct = (
            (current - pos.stop_loss) / pos.entry_price * 100
            if pos.stop_loss
            else 999.0
        )
        distance_to_target_pct = (
            (pos.target - current) / pos.entry_price * 100 if pos.target else 999.0
        )

        alert_type = None
        urgency = None

        if pos.stop_loss and day_low <= pos.stop_loss:
            alert_type = "stop_hit"
            urgency = "critical"
        elif distance_to_stop_pct < 2.0:
            alert_type = "stop_approached"
            urgency = "high"
        elif pos.target and day_high >= pos.target:
            alert_type = "target_hit"
            urgency = "critical"
        elif distance_to_target_pct < 2.0:
            alert_type = "target_approached"
            urgency = "medium"
        elif rsi > 80.0 and prev_row is not None and current < prev_row["Low"]:
            alert_type = "overextended_exit"
            urgency = "high"

        if not alert_type:
            continue

        # Deduplicate — one exit alert per symbol per day per type
        if _already_alerted(db, pos.symbol, signal_date, alert_type):
            continue

        alerts.append(
            {
                "symbol": pos.symbol,
                "alert_type": alert_type,
                "urgency": urgency,
                "entry_price": pos.entry_price,
                "current_price": current,
                "stop_loss": pos.stop_loss,
                "target": pos.target,
                "unrealised_pct": round(unrealised_pct, 2),
                "distance_to_stop_pct": round(distance_to_stop_pct, 2)
                if distance_to_stop_pct != 999.0
                else None,
                "holding_days": (signal_date - pos.entry_date).days
                if pos.entry_date
                else 0,
            }
        )

    # Sort: critical first
    urgency_order = {"critical": 0, "high": 1, "medium": 2}
    alerts.sort(key=lambda x: urgency_order.get(x["urgency"], 3))
    return alerts, len(open_positions)


def run_exit_alert_cycle(db: Session, signal_date: datetime.date | None = None) -> dict:
    """
    Checks all open TradeJournal positions against today's price.
    Fires alerts for: stop approached, stop hit, target approached, target hit, overextended.
    """
    if signal_date is None:
        from app.screens.base import get_latest_signal_date

        signal_date = get_latest_signal_date(db, "D")

    alerts, positions_checked = get_exit_alerts_for_date(db, signal_date)

    if not alerts:
        return {"positions_checked": positions_checked, "alerts_fired": 0}

    subject = f"⚠️ Position Alert — {signal_date.strftime('%d %b %Y')}"
    html = build_exit_alert_email(alerts, str(signal_date))
    email_id = send_alert_email(subject, html)

    if email_id:
        for a in alerts:
            _log_alert(
                db, a["symbol"], signal_date, a["alert_type"], None, None, email_id
            )

    return {"positions_checked": positions_checked, "alerts_fired": len(alerts)}


def run_daily_digest(
    db: Session,
    pt_results: dict,
    signal_date: datetime.date | None = None,
    configs: list[UnifiedTradingConfig] = None,
) -> dict:
    """
    Main orchestrator for the Full Story Daily Digest.
    Aggregates new signals, entry triggers, exits, and warnings into a single email.
    """
    from app.alerts.email import build_daily_digest_email

    if signal_date is None:
        from app.screens.base import get_latest_signal_date

        signal_date = get_latest_signal_date(db, "D")

    if configs is None:
        configs = [TREND_INITIATION]

    regime_bullish = get_market_regime(db, signal_date)

    # 1. New Signals
    all_new_signals = []
    for config in configs:
        signals_to_alert, skipped = get_new_signals_for_alert(db, signal_date, config)
        all_new_signals.extend(signals_to_alert)

    # Deduplicate new signals by symbol (keeping highest tier/score)
    deduped_signals = {}
    for sig in all_new_signals:
        sym = sig["symbol"]
        if sym not in deduped_signals:
            deduped_signals[sym] = sig
        else:
            # If same symbol found across configs, keep the one with better tier/score
            existing = deduped_signals[sym]
            if sig["signal_tier"] < existing["signal_tier"] or (
                sig["signal_tier"] == existing["signal_tier"]
                and sig["score"] > existing["score"]
            ):
                deduped_signals[sym] = sig

    new_signals = list(deduped_signals.values())
    new_signals.sort(key=lambda x: (x["signal_tier"], -x["score"]))

    # 2. Entries & Exits from Paper Trading
    opened_positions = pt_results.get("pending", {}).get("opened", [])
    closed_positions = pt_results.get("closed", {}).get("closed", [])
    trail_moved = pt_results.get("closed", {}).get("trail_moved", [])

    # 3. Warnings (Near Stop, Near Target)
    # We use get_exit_alerts_for_date but only keep the warnings
    exit_alerts, _ = get_exit_alerts_for_date(db, signal_date)
    warnings = [a for a in exit_alerts if "approached" in a["alert_type"]]

    # If nothing happened today, we might skip email, but usually there are at least new signals.
    if not (
        new_signals or opened_positions or closed_positions or trail_moved or warnings
    ):
        logger.info("daily_digest: No events or signals today. Skipping email.")
        return {"status": "skipped", "reason": "no_events"}

    subject = f"📈 Stock AI Daily Digest — {signal_date.strftime('%d %b %Y')}"
    html = build_daily_digest_email(
        signal_date=str(signal_date),
        regime_bullish=regime_bullish,
        new_signals=new_signals,
        opened_positions=opened_positions,
        closed_positions=closed_positions,
        trail_moved=trail_moved,
        warnings=warnings,
    )

    email_id = send_alert_email(subject, html)

    # Log alerts sent
    if email_id:
        for sig in new_signals:
            _log_alert(
                db,
                sig["symbol"],
                signal_date,
                sig["alert_type"],
                None,
                sig["score"],
                email_id,
            )
        for w in warnings:
            _log_alert(
                db, w["symbol"], signal_date, w["alert_type"], None, None, email_id
            )

    logger.info("daily_digest: Sent unified digest email_id=%s", email_id)

    # Persist the digest in DB
    try:
        existing = db.query(DailyDigestLog).filter_by(date=signal_date).first()
        if existing:
            existing.regime_bullish = regime_bullish
            existing.new_signals = new_signals
            existing.opened_positions = opened_positions
            existing.closed_positions = closed_positions
            existing.trail_moved = trail_moved
            existing.warnings = warnings
        else:
            digest_log = DailyDigestLog(
                date=signal_date,
                regime_bullish=regime_bullish,
                new_signals=new_signals,
                opened_positions=opened_positions,
                closed_positions=closed_positions,
                trail_moved=trail_moved,
                warnings=warnings,
            )
            db.add(digest_log)
        db.commit()
        logger.info("daily_digest: Persisted to database.")
    except Exception as e:
        logger.error("daily_digest: Failed to persist to database: %s", e)
        db.rollback()

    return {
        "status": "sent",
        "email_id": email_id,
        "new_signals": len(new_signals),
        "opened": len(opened_positions),
        "closed": len(closed_positions),
        "trail_moved": len(trail_moved),
        "warnings": len(warnings),
    }
