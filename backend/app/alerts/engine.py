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
    ScreenResult,
    Stock,
    TechnicalSignal,
    TradeJournal,
)
from app.pipeline.ohlcv_cache import OHLCVCache
from app.pipeline.trade_setup import compute_trade_setup
from app.pipeline.utils import get_market_regime

logger = logging.getLogger(__name__)


def _compute_entry_status(close_price: float, ema20: float) -> tuple[str, float]:
    """Returns (entry_status, pct_above_ema20)."""
    if not close_price or not ema20 or ema20 == 0:
        return "unknown", 0.0

    pct = (close_price - ema20) / ema20 * 100
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
            or_(
                TechnicalSignal.volume_breakout,
                TechnicalSignal.adx >= config.min_adx,
            ),
        )
    )

    if config.require_consolidation:
        query = query.filter(TechnicalSignal.is_consolidating)

    candidates = query.all()

    if not candidates:
        logger.info("alert_cycle: no candidates on %s", signal_date)
        return {"signals_found": 0, "alerts_sent": 0, "skipped_duplicate": 0}

    signals_to_alert = []
    skipped = 0

    for tech, stock in candidates:
        alert_type = f"{config.strategy_id}_signal"

        if _already_alerted(db, tech.symbol, signal_date, alert_type):
            skipped += 1
            continue

        if not tech.close_price or not tech.ema20_level:
            logger.warning(
                "alert_cycle: skipping %s — missing close_price or ema20_level",
                tech.symbol,
            )
            continue

        # Compute signal_tier from technical indicators only
        if tech.volume_breakout and (tech.adx or 0.0) >= config.min_adx:
            tier = 1
        elif tech.volume_breakout or (tech.adx or 0.0) >= config.min_adx:
            tier = 2
        else:
            tier = 2

        entry_status, pct_above_ema20 = _compute_entry_status(
            tech.close_price, tech.ema20_level
        )

        setup = compute_trade_setup(tech)
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
                "pct_above_ema20": pct_above_ema20,
                "stop_loss": stop_loss,
                "target_price": target_price,
                "momentum_12m": tech.momentum_12m or 0.0,
                "close_price": tech.close_price,
            }
        )

    if not signals_to_alert:
        logger.info(
            "alert_cycle: %d candidates found, all already alerted or filtered (skipped=%d)",
            len(candidates),
            skipped,
        )
        return {
            "signals_found": len(candidates),
            "alerts_sent": 0,
            "skipped_duplicate": skipped,
        }

    # Sort: tier 1 first, then by score descending
    signals_to_alert.sort(key=lambda x: (x["signal_tier"], -x["score"]))

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
        "signals_found": len(candidates),
        "alerts_sent": len(signals_to_alert),
        "skipped_duplicate": skipped,
        "email_id": email_id,
        "regime_bullish": regime_bullish,
    }


def run_exit_alert_cycle(db: Session, signal_date: datetime.date | None = None) -> dict:
    """
    Checks all open TradeJournal positions against today's price.
    Fires alerts for: stop approached, stop hit, target approached, target hit, overextended.
    """
    if signal_date is None:
        from app.screens.base import get_latest_signal_date

        signal_date = get_latest_signal_date(db, "D")

    open_positions = db.query(TradeJournal).filter_by(status="open").all()
    if not open_positions:
        return {"positions_checked": 0, "alerts_fired": 0}

    cache = OHLCVCache()
    from app.core.strategy import TechnicalStrategy

    strategy = TechnicalStrategy()
    alerts = []

    for pos in open_positions:
        # TODO: Batch these cache reads if positions grow
        df = cache.get(pos.symbol, period="1y")
        if df is None or df.empty:
            continue

        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # Calculate indicators for overextended check (RSI)
        df = strategy.calculate_indicators(df)

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

    if not alerts:
        return {"positions_checked": len(open_positions), "alerts_fired": 0}

    # Sort: critical first
    urgency_order = {"critical": 0, "high": 1, "medium": 2}
    alerts.sort(key=lambda x: urgency_order.get(x["urgency"], 3))

    subject = f"⚠️ Position Alert — {signal_date.strftime('%d %b %Y')}"
    html = build_exit_alert_email(alerts, str(signal_date))
    email_id = send_alert_email(subject, html)

    if email_id:
        for a in alerts:
            _log_alert(
                db, a["symbol"], signal_date, a["alert_type"], None, None, email_id
            )

    return {"positions_checked": len(open_positions), "alerts_fired": len(alerts)}
