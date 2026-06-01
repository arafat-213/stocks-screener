import datetime
import logging

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.backtest.engine import (
    ROUND_TRIP_COST_PCT,
    _compute_position_size,
    _compute_signal_tier,
    _is_consolidating,
)
from app.backtest.sync_service import sync_paper_to_journal
from app.core.trading_config import (
    TREND_CONTINUATION,
    TREND_INITIATION,
    UnifiedTradingConfig,
)
from app.db.models import (
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    Stock,
    TechnicalSignal,
)
from app.pipeline.ohlcv_cache import OHLCVCache
from app.pipeline.utils import get_market_regime

logger = logging.getLogger(__name__)
_ohlcv_cache = OHLCVCache()


def _get_or_create_portfolio(
    db: Session, config: UnifiedTradingConfig
) -> PaperPortfolio:
    portfolio = db.query(PaperPortfolio).filter_by(is_active=True).first()
    if not portfolio:
        portfolio = PaperPortfolio(
            name="default",
            starting_capital=config.starting_capital,
            is_active=True,
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
        logger.info("Created new paper portfolio id=%d", portfolio.id)
    return portfolio


def scan_for_new_signals(db: Session, today: datetime.date) -> int:
    """
    Scans for new technical signals across multiple strategy configs and creates 'pending' paper positions.
    If a symbol qualifies for multiple strategies, they are merged into one position with multiple tags.
    """
    configs = [TREND_INITIATION, TREND_CONTINUATION]
    # Use the first config's portfolio settings
    portfolio = _get_or_create_portfolio(db, configs[0])

    # Regime Filter (common check)
    if not get_market_regime(db, today):
        logger.info("paper_trading: regime bearish on %s, skipping new signals", today)
        return 0

    # Avoid duplicate pending/open signals for same symbol
    active_positions = {
        p.symbol: p
        for p in db.query(PaperPosition)
        .filter(
            PaperPosition.portfolio_id == portfolio.id,
            PaperPosition.status.in_(["pending", "open"]),
        )
        .all()
    }
    existing_symbols = set(active_positions.keys())

    qualified_signals = {}  # symbol -> {"sig": sig, "sector": sector, "tags": [tag], "config": config}

    from sqlalchemy import func

    from app.db.models import ScreenResult

    for config in configs:
        logger.info("paper_trading: scanning for strategy '%s'", config.strategy_id)

        # Query signals from today's pipeline run that pass this config's thresholds
        query = db.query(TechnicalSignal, Stock.sector).join(
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

        signals = query.filter(
            and_(
                func.date(TechnicalSignal.date) == today,
                TechnicalSignal.timeframe == "D",
                TechnicalSignal.above_200ema,
                TechnicalSignal.rsi >= config.rsi_min,
                TechnicalSignal.rsi <= config.rsi_max,
                TechnicalSignal.entry_score >= config.effective_score_threshold,
                TechnicalSignal.ema_signal.in_(["bullish_cross", "bullish_pullback"]),
            )
        ).all()

        for sig, sector in signals:
            if sig.symbol in existing_symbols:
                # If already active, just append the tag if missing
                pos = active_positions[sig.symbol]
                if config.strategy_id not in (pos.strategy_tags or []):
                    if pos.strategy_tags is None:
                        pos.strategy_tags = []
                    pos.strategy_tags.append(config.strategy_id)
                    logger.info(
                        "paper_trading: adding tag '%s' to active position %s",
                        config.strategy_id,
                        sig.symbol,
                    )
                    sync_paper_to_journal(db, pos)
                continue

            # Reconstruct signal dict for tier and consolidation logic
            signal_dict = {
                "ema_signal": sig.ema_signal,
                "volume_breakout": sig.volume_breakout or False,
                "adx": sig.adx or 0.0,
                "rsi": sig.rsi or 0.0,
                "momentum_12m": sig.momentum_12m,
                "atr": sig.atr,
                "score": sig.entry_score,
            }

            # Tier Gate
            tier = _compute_signal_tier(signal_dict, config)
            if tier > config.min_signal_tier:
                continue

            # Consolidation Gate
            if config.require_consolidation:
                df = _ohlcv_cache.get(sig.symbol, period="5y")
                if df is None or df.empty:
                    continue
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)

                # Find signal bar index
                matching = df.index[df.index.date <= today]
                if matching.empty:
                    continue
                signal_idx = len(matching) - 1

                if not _is_consolidating(
                    df,
                    signal_idx,
                    lookback=config.consolidation_bars,
                    max_range_pct=config.consolidation_max_range_pct,
                ):
                    continue

            # If we reach here, it qualifies for this strategy
            if sig.symbol in qualified_signals:
                if config.strategy_id not in qualified_signals[sig.symbol]["tags"]:
                    qualified_signals[sig.symbol]["tags"].append(config.strategy_id)
            else:
                qualified_signals[sig.symbol] = {
                    "sig": sig,
                    "sector": sector,
                    "tags": [config.strategy_id],
                    "config": config,  # Store the first config that qualified it
                }

    new_pending = 0
    for symbol, data in qualified_signals.items():
        sig = data["sig"]
        sector = data["sector"]
        tags = data["tags"]

        # Create Pending Position
        pending = PaperPosition(
            portfolio_id=portfolio.id,
            symbol=symbol,
            sector=sector,
            signal_date=today,
            signal_score=sig.entry_score,
            ema_signal=sig.ema_signal,
            atr_at_signal=sig.atr,
            ema20_at_signal=sig.ema20_level,
            status="pending",
            wait_days_elapsed=0,
            strategy_tags=tags,
        )
        db.add(pending)
        db.flush()  # To get the ID for syncing
        sync_paper_to_journal(db, pending)
        new_pending += 1
        logger.info(
            "paper_trading: NEW PENDING %s on %s (score=%.1f) tags=%s",
            symbol,
            today,
            sig.entry_score,
            tags,
        )

    db.commit()
    return new_pending


def _get_config_for_position(pos: PaperPosition) -> UnifiedTradingConfig:
    """Returns the config associated with this position's tags. Defaults to INITIATION."""
    if pos.strategy_tags and "continuation" in pos.strategy_tags:
        return TREND_CONTINUATION
    return TREND_INITIATION


def process_pending_orders(db: Session, today: datetime.date) -> dict:
    """
    Processes 'pending' orders: checks if pullback or momentum entry criteria are met.
    """
    portfolio = _get_or_create_portfolio(db, TREND_INITIATION)
    pending_orders = (
        db.query(PaperPosition)
        .filter_by(portfolio_id=portfolio.id, status="pending")
        .all()
    )

    results = {"opened": 0, "expired": 0, "invalidated": 0, "waiting": 0}

    for pos in pending_orders:
        config = _get_config_for_position(pos)
        df = _ohlcv_cache.get(pos.symbol, period="5y")
        if df is None or df.empty:
            continue
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # Get today's bar
        rows = df[df.index.date == today]
        if rows.empty:
            continue
        row = rows.iloc[0]

        day_low = float(row["Low"])
        day_close = float(row["Close"])
        day_open = float(row["Open"])

        # We need EMA20 to check pullback
        import pandas_ta_classic  # noqa

        df_ta = df.copy()
        df_ta.ta.ema(length=20, append=True)
        ema20 = df_ta.loc[rows.index[0], "EMA_20"]

        pos.wait_days_elapsed += 1

        # Check for invalidation (Closed meaningfully below EMA20)
        # Threshold: 2.5% below EMA20
        if day_close < ema20 * 0.975:
            pos.status = "expired"
            pos.exit_reason = "invalidated"
            pos.is_invalidated = True
            pos.closed_at = datetime.datetime.now(datetime.timezone.utc)
            sync_paper_to_journal(db, pos)
            results["invalidated"] += 1
            logger.info(
                "paper_trading: INVALIDATED %s (closed below EMA20)", pos.symbol
            )
            continue

        # Path A: Pullback Entry (Price touched EMA20 and closed above)
        tol = config.pullback_tolerance_pct / 100.0
        # Check if Low touched EMA20 area (within tolerance) or High/Low bracketed it
        touched_ema = (day_low <= ema20 * (1 + tol)) and (day_close > ema20)

        closeness = abs(day_low - ema20) / ema20 * 100
        if closeness < pos.pending_highest_closeness_pct:
            pos.pending_highest_closeness_pct = closeness

        if touched_ema:
            # ENTRY Path A
            _convert_to_open(
                db, pos, entry_price=day_close, entry_type="pullback_a", today=today
            )
            results["opened"] += 1
            continue

        # Path B: Momentum continuation (Wait window expired, but price stayed above EMA20)
        if pos.wait_days_elapsed >= config.pullback_max_wait_bars:
            if (
                pos.pending_highest_closeness_pct <= 8.0
            ):  # Within 8% of EMA20 at some point
                # ENTRY Path B
                _convert_to_open(
                    db, pos, entry_price=day_open, entry_type="momentum_b", today=today
                )
                results["opened"] += 1
            else:
                pos.status = "expired"
                pos.exit_reason = "no_pullback"
                pos.closed_at = datetime.datetime.now(datetime.timezone.utc)
                sync_paper_to_journal(db, pos)
                results["expired"] += 1
                logger.info(
                    "paper_trading: EXPIRED %s (no pullback within window)", pos.symbol
                )
            continue

        results["waiting"] += 1

    db.commit()
    return results


def _convert_to_open(
    db: Session,
    pos: PaperPosition,
    entry_price: float,
    entry_type: str,
    today: datetime.date,
):
    """Transition a pending position to open."""
    config = _get_config_for_position(pos)
    pos.status = "open"
    pos.entry_date = today
    pos.entry_price = entry_price
    pos.entry_type = entry_type
    pos.highest_price = entry_price

    # Calculate Stop Loss (Re-using backtest logic)
    # Get recent low for structural stop
    df = _ohlcv_cache.get(pos.symbol, period="5y")
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    matching = df.index[df.index.date <= today]
    idx = len(matching) - 1

    consol_start = max(0, idx - config.consolidation_bars)
    consol_low = float(df.iloc[consol_start:idx]["Low"].min())
    structural_stop = consol_low * 0.98 if consol_low > 0 else None

    atr_val = pos.atr_at_signal
    atr_stop = (entry_price - config.atr_multiplier * atr_val) if atr_val else None

    if structural_stop and atr_stop:
        base_stop = min(structural_stop, atr_stop)
    elif structural_stop:
        base_stop = structural_stop
    elif atr_stop:
        base_stop = atr_stop
    else:
        base_stop = entry_price * (1 - config.stop_loss_pct / 100)

    # Allow for tighter stops if ATR/Structure permits, but ensure below entry
    pos.stop_loss_price = min(base_stop, entry_price * 0.99)

    actual_risk = max(entry_price - pos.stop_loss_price, entry_price * 0.01)
    pos.target_price = entry_price + config.risk_reward_ratio * actual_risk

    # Position Sizing
    # Note: _compute_position_size needs to be aliased to the right class if it changed
    pos.position_size = _compute_position_size(
        config, entry_price=entry_price, atr=atr_val
    )
    pos.shares = pos.position_size / entry_price
    pos.opened_at = datetime.datetime.now(datetime.timezone.utc)

    logger.info(
        "paper_trading: OPEN %s via %s at %.2f (stop=%.2f target=%.2f)",
        pos.symbol,
        entry_type,
        entry_price,
        pos.stop_loss_price,
        pos.target_price,
    )
    sync_paper_to_journal(db, pos)


def update_open_positions(db: Session, today: datetime.date) -> dict:
    """
    Checks exit conditions for open positions.
    """
    portfolio = _get_or_create_portfolio(db, TREND_INITIATION)
    open_positions = (
        db.query(PaperPosition)
        .filter_by(portfolio_id=portfolio.id, status="open")
        .all()
    )

    exit_counts = {
        "stop_loss": 0,
        "target": 0,
        "atr_trailing_stop": 0,
        "holding_period": 0,
    }

    for pos in open_positions:
        config = _get_config_for_position(pos)
        df = _ohlcv_cache.get(pos.symbol, period="5y")
        if df is None or df.empty:
            continue
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        rows = df[df.index.date == today]
        if rows.empty:
            continue
        row = rows.iloc[0]

        day_high = float(row["High"])
        day_low = float(row["Low"])
        day_open = float(row["Open"])
        day_close = float(row["Close"])

        # Update highest price
        if day_high > pos.highest_price:
            pos.highest_price = day_high

        holding_days = (today - pos.entry_date).days
        exit_price = None
        exit_reason = None

        # 1. Stop loss
        if day_low <= pos.stop_loss_price:
            exit_price = pos.stop_loss_price
            exit_reason = "stop_loss"

        # 2. Target
        elif day_high >= pos.target_price:
            exit_price = pos.target_price
            exit_reason = "target"

        # 3. ATR trailing stop
        elif config.use_atr_trailing_stop and pos.atr_at_signal:
            activation = pos.entry_price + (
                config.atr_trailing_activation * pos.atr_at_signal
            )
            if pos.highest_price >= activation:
                pos.atr_trail_active = True
                trail_stop = max(
                    pos.entry_price,
                    pos.highest_price
                    - (config.atr_trailing_multiplier * pos.atr_at_signal),
                )
                if day_low <= trail_stop:
                    exit_price = max(trail_stop, day_open)
                    exit_reason = "atr_trailing_stop"

        # 4. Holding period
        elif holding_days >= config.holding_days:
            exit_price = day_close
            exit_reason = "holding_period"

        if exit_price and exit_reason:
            gross_return = (exit_price - pos.entry_price) / pos.entry_price * 100
            net_return = gross_return - ROUND_TRIP_COST_PCT
            pnl = (net_return / 100) * pos.position_size

            trade = PaperTrade(
                portfolio_id=portfolio.id,
                symbol=pos.symbol,
                sector=pos.sector,
                signal_date=pos.signal_date,
                entry_date=pos.entry_date,
                exit_date=today,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                shares=pos.shares,
                position_size=pos.position_size,
                return_pct=net_return,
                pnl=pnl,
                exit_reason=exit_reason,
                signal_score=pos.signal_score,
                ema_signal=pos.ema_signal,
                holding_days=holding_days,
                strategy_tags=pos.strategy_tags,
            )
            db.add(trade)
            pos.status = "closed"
            pos.exit_price = exit_price
            pos.exit_reason = exit_reason
            pos.closed_at = datetime.datetime.now(datetime.timezone.utc)
            exit_counts[exit_reason] += 1
            logger.info(
                "paper_trading: CLOSE %s exit=%.2f return=%.2f%% reason=%s",
                pos.symbol,
                exit_price,
                net_return,
                exit_reason,
            )
            sync_paper_to_journal(db, pos)

    db.commit()
    return exit_counts


def run_paper_trading_cycle(db: Session) -> dict:
    """
    Daily cycle: Process Pending -> Update Open -> Scan for New Signals.
    """
    from app.screens.base import get_latest_signal_date

    today = get_latest_signal_date(
        db
    )  # Use the same date the pipeline just finished processing

    logger.info("paper_trading: starting cycle for %s", today)

    pending_res = process_pending_orders(db, today)
    closed_res = update_open_positions(db, today)
    new_signals = scan_for_new_signals(db, today)

    logger.info(
        "paper_trading: cycle complete. Pending: %s, Closed: %s, New Signals: %d",
        pending_res,
        closed_res,
        new_signals,
    )

    return {
        "date": str(today),
        "pending": pending_res,
        "closed": closed_res,
        "new_signals": new_signals,
    }
