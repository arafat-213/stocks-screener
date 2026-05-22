import logging
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from app.db.models import (
    PaperPortfolio, PaperPosition, PaperTrade, TechnicalSignal, Stock
)
from app.pipeline.ohlcv_cache import OHLCVCache
from app.backtest.engine import (
    _compute_signal_tier, _is_consolidating, _compute_position_size, 
    BacktestConfig, ROUND_TRIP_COST_PCT
)
import pandas as pd

logger = logging.getLogger(__name__)
_ohlcv_cache = OHLCVCache()

# Configuration mirrored from backtest
PAPER_CONFIG = BacktestConfig(
    score_threshold=60.0,
    holding_days=50,
    stop_loss_pct=7.0,
    atr_multiplier=2.0,
    risk_reward_ratio=1.5,
    use_atr_trailing_stop=True,
    atr_trailing_multiplier=1.0,
    atr_trailing_activation=2.5,
    min_signal_tier=2,
    require_consolidation=True,
    use_pullback_entry=True,
    pullback_max_wait_bars=8,
    pullback_tolerance_pct=3.0,
    consolidation_bars=15,
    consolidation_max_range_pct=12.0,
    use_regime_filter=True,
    risk_per_trade_pct=3.0,
    max_position_pct=20.0,
    use_volatility_sizing=True,
    starting_capital=1_000_000.0,
)

def _get_or_create_portfolio(db: Session) -> PaperPortfolio:
    portfolio = db.query(PaperPortfolio).filter_by(is_active=True).first()
    if not portfolio:
        portfolio = PaperPortfolio(
            name="default",
            starting_capital=PAPER_CONFIG.starting_capital,
            is_active=True,
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
        logger.info("Created new paper portfolio id=%d", portfolio.id)
    return portfolio

def _get_regime(db: Session, date: datetime.date) -> bool:
    import pandas_ta # noqa
    df = _ohlcv_cache.get("^NSEI", append_ns=False, period='5y')
    if df is None or df.empty:
        return True
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    
    row = df[df.index.date <= date].tail(1)
    if row.empty:
        return True
    r = row.iloc[-1]
    return (
        r['Close'] > r.get('EMA_50', 0) and 
        r['Close'] > r.get('EMA_200', 0) and 
        r.get('EMA_50', 0) > r.get('EMA_200', 0)
    )

def scan_for_new_signals(db: Session, today: datetime.date) -> int:
    """
    Scans for new technical signals and creates 'pending' paper positions.
    """
    portfolio = _get_or_create_portfolio(db)
    
    # Regime Filter
    if not _get_regime(db, today):
        logger.info("paper_trading: regime bearish on %s, skipping new signals", today)
        return 0

    # Avoid duplicate pending/open signals for same symbol
    existing_symbols = {
        p.symbol for p in db.query(PaperPosition.symbol)
        .filter(PaperPosition.portfolio_id == portfolio.id, PaperPosition.status.in_(['pending', 'open']))
        .all()
    }

    # Query signals from today's pipeline run
    signals = (
        db.query(TechnicalSignal, Stock.sector)
        .join(Stock, TechnicalSignal.symbol == Stock.symbol)
        .filter(
            and_(
                TechnicalSignal.date >= datetime.datetime.combine(today, datetime.time.min),
                TechnicalSignal.date < datetime.datetime.combine(today + datetime.timedelta(days=1), datetime.time.min),
                TechnicalSignal.timeframe == 'D',
                TechnicalSignal.above_200ema == True,
                TechnicalSignal.entry_score >= PAPER_CONFIG.effective_score_threshold,
                TechnicalSignal.ema_signal.in_(['bullish_cross', 'bullish_pullback']),
            )
        ).all()
    )

    new_pending = 0
    for sig, sector in signals:
        if sig.symbol in existing_symbols:
            continue
            
        # Reconstruct signal dict for tier and consolidation logic
        signal_dict = {
            'ema_signal': sig.ema_signal,
            'volume_breakout': sig.volume_breakout or False,
            'adx': sig.adx or 0.0,
            'rsi': sig.rsi or 0.0,
            'momentum_12m': sig.momentum_12m,
            'atr': sig.atr,
            'score': sig.entry_score,
        }

        # Tier Gate
        tier = _compute_signal_tier(signal_dict)
        if tier > PAPER_CONFIG.min_signal_tier:
            continue

        # Consolidation Gate
        df = _ohlcv_cache.get(sig.symbol, period='5y')
        if df is None or df.empty:
            continue
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        
        # Find signal bar index
        matching = df.index[df.index.date <= today]
        if matching.empty:
            continue
        signal_idx = len(matching) - 1

        if PAPER_CONFIG.require_consolidation:
            if not _is_consolidating(
                df, signal_idx, 
                lookback=PAPER_CONFIG.consolidation_bars,
                max_range_pct=PAPER_CONFIG.consolidation_max_range_pct
            ):
                continue

        # Create Pending Position
        pending = PaperPosition(
            portfolio_id=portfolio.id,
            symbol=sig.symbol,
            sector=sector,
            signal_date=today,
            signal_score=sig.entry_score,
            ema_signal=sig.ema_signal,
            atr_at_signal=sig.atr,
            ema20_at_signal=sig.ema20_level,
            status='pending',
            wait_days_elapsed=0
        )
        db.add(pending)
        new_pending += 1
        logger.info("paper_trading: NEW PENDING %s on %s (score=%.1f)", sig.symbol, today, sig.entry_score)

    db.commit()
    return new_pending

def process_pending_orders(db: Session, today: datetime.date) -> dict:
    """
    Processes 'pending' orders: checks if pullback or momentum entry criteria are met.
    """
    portfolio = _get_or_create_portfolio(db)
    pending_orders = db.query(PaperPosition).filter_by(portfolio_id=portfolio.id, status='pending').all()
    
    results = {'opened': 0, 'expired': 0, 'invalidated': 0, 'waiting': 0}
    
    for pos in pending_orders:
        df = _ohlcv_cache.get(pos.symbol, period='5y')
        if df is None or df.empty:
            continue
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
            
        # Get today's bar
        rows = df[df.index.date == today]
        if rows.empty:
            continue
        row = rows.iloc[0]
        
        day_high = float(row['High'])
        day_low = float(row['Low'])
        day_close = float(row['Close'])
        day_open = float(row['Open'])
        
        # We need EMA20 to check pullback
        import pandas_ta # noqa
        df_ta = df.copy()
        df_ta.ta.ema(length=20, append=True)
        ema20 = df_ta.loc[rows.index[0], 'EMA_20']
        
        pos.wait_days_elapsed += 1
        
        # Check for invalidation (Closed meaningfully below EMA20)
        # Threshold: 2.5% below EMA20
        if day_close < ema20 * 0.975:
            pos.status = 'expired'
            pos.exit_reason = 'invalidated'
            pos.is_invalidated = True
            pos.closed_at = datetime.datetime.utcnow()
            results['invalidated'] += 1
            logger.info("paper_trading: INVALIDATED %s (closed below EMA20)", pos.symbol)
            continue

        # Path A: Pullback Entry (Price touched EMA20 and closed above)
        tol = PAPER_CONFIG.pullback_tolerance_pct / 100.0
        # Check if Low touched EMA20 area (within tolerance) or High/Low bracketed it
        touched_ema = (day_low <= ema20 * (1 + tol)) and (day_close > ema20)
        
        closeness = abs(day_low - ema20) / ema20 * 100
        if closeness < pos.pending_highest_closeness_pct:
            pos.pending_highest_closeness_pct = closeness

        if touched_ema:
            # ENTRY Path A
            _convert_to_open(pos, entry_price=day_close, entry_type='pullback_a', today=today)
            results['opened'] += 1
            continue

        # Path B: Momentum continuation (Wait window expired, but price stayed above EMA20)
        if pos.wait_days_elapsed >= PAPER_CONFIG.pullback_max_wait_bars:
            if pos.pending_highest_closeness_pct <= 8.0: # Within 8% of EMA20 at some point
                # ENTRY Path B
                _convert_to_open(pos, entry_price=day_open, entry_type='momentum_b', today=today)
                results['opened'] += 1
            else:
                pos.status = 'expired'
                pos.exit_reason = 'no_pullback'
                pos.closed_at = datetime.datetime.utcnow()
                results['expired'] += 1
                logger.info("paper_trading: EXPIRED %s (no pullback within window)", pos.symbol)
            continue
            
        results['waiting'] += 1

    db.commit()
    return results

def _convert_to_open(pos: PaperPosition, entry_price: float, entry_type: str, today: datetime.date):
    """Transition a pending position to open."""
    pos.status = 'open'
    pos.entry_date = today
    pos.entry_price = entry_price
    pos.entry_type = entry_type
    pos.highest_price = entry_price
    
    # Calculate Stop Loss (Re-using backtest logic)
    # Get recent low for structural stop
    df = _ohlcv_cache.get(pos.symbol, period='5y')
    if df.index.tz is not None: df.index = df.index.tz_localize(None)
    
    matching = df.index[df.index.date <= today]
    idx = len(matching) - 1
    
    consol_start = max(0, idx - PAPER_CONFIG.consolidation_bars)
    consol_low = float(df.iloc[consol_start:idx]['Low'].min())
    structural_stop = consol_low * 0.98 if consol_low > 0 else None
    
    atr_val = pos.atr_at_signal
    atr_stop = (entry_price - PAPER_CONFIG.atr_multiplier * atr_val) if atr_val else None
    
    if structural_stop and atr_stop:
        base_stop = min(structural_stop, atr_stop)
    elif structural_stop:
        base_stop = structural_stop
    elif atr_stop:
        base_stop = atr_stop
    else:
        base_stop = entry_price * (1 - PAPER_CONFIG.stop_loss_pct / 100)
    
    pos.stop_loss_price = min(base_stop, entry_price * 0.95)
    
    actual_risk = max(entry_price - pos.stop_loss_price, entry_price * 0.02)
    pos.target_price = entry_price + PAPER_CONFIG.risk_reward_ratio * actual_risk
    
    # Position Sizing
    pos.position_size = _compute_position_size(
        PAPER_CONFIG, entry_price=entry_price, atr=atr_val
    )
    pos.shares = pos.position_size / entry_price
    pos.opened_at = datetime.datetime.utcnow()
    
    logger.info("paper_trading: OPEN %s via %s at %.2f (stop=%.2f target=%.2f)", 
                pos.symbol, entry_type, entry_price, pos.stop_loss_price, pos.target_price)

def update_open_positions(db: Session, today: datetime.date) -> dict:
    """
    Checks exit conditions for open positions.
    """
    portfolio = _get_or_create_portfolio(db)
    open_positions = db.query(PaperPosition).filter_by(portfolio_id=portfolio.id, status='open').all()
    
    exit_counts = {'stop_loss': 0, 'target': 0, 'atr_trailing_stop': 0, 'holding_period': 0}
    
    for pos in open_positions:
        df = _ohlcv_cache.get(pos.symbol, period='5y')
        if df is None or df.empty:
            continue
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
            
        rows = df[df.index.date == today]
        if rows.empty:
            continue
        row = rows.iloc[0]
        
        day_high = float(row['High'])
        day_low = float(row['Low'])
        day_open = float(row['Open'])
        day_close = float(row['Close'])
        
        # Update highest price
        if day_high > pos.highest_price:
            pos.highest_price = day_high
            
        holding_days = (today - pos.entry_date).days
        exit_price = None
        exit_reason = None
        
        # 1. Stop loss
        if day_low <= pos.stop_loss_price:
            exit_price = pos.stop_loss_price
            exit_reason = 'stop_loss'
            
        # 2. Target
        elif day_high >= pos.target_price:
            exit_price = pos.target_price
            exit_reason = 'target'
            
        # 3. ATR trailing stop
        elif PAPER_CONFIG.use_atr_trailing_stop and pos.atr_at_signal:
            activation = pos.entry_price + (PAPER_CONFIG.atr_trailing_activation * pos.atr_at_signal)
            if pos.highest_price >= activation:
                pos.atr_trail_active = True
                trail_stop = max(
                    pos.entry_price,
                    pos.highest_price - (PAPER_CONFIG.atr_trailing_multiplier * pos.atr_at_signal)
                )
                if day_low <= trail_stop:
                    exit_price = max(trail_stop, day_open)
                    exit_reason = 'atr_trailing_stop'
                    
        # 4. Holding period
        elif holding_days >= PAPER_CONFIG.holding_days:
            exit_price = day_close
            exit_reason = 'holding_period'
            
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
            )
            db.add(trade)
            pos.status = 'closed'
            pos.exit_reason = exit_reason
            pos.closed_at = datetime.datetime.utcnow()
            exit_counts[exit_reason] += 1
            logger.info("paper_trading: CLOSE %s exit=%.2f return=%.2f%% reason=%s", 
                        pos.symbol, exit_price, net_return, exit_reason)

    db.commit()
    return exit_counts

def run_paper_trading_cycle(db: Session) -> dict:
    """
    Daily cycle: Process Pending -> Update Open -> Scan for New Signals.
    """
    from app.screens.base import get_latest_signal_date
    today = get_latest_signal_date(db) # Use the same date the pipeline just finished processing
    
    logger.info("paper_trading: starting cycle for %s", today)
    
    pending_res = process_pending_orders(db, today)
    closed_res = update_open_positions(db, today)
    new_signals = scan_for_new_signals(db, today)
    
    logger.info("paper_trading: cycle complete. Pending: %s, Closed: %s, New Signals: %d", 
                pending_res, closed_res, new_signals)
                
    return {
        "date": str(today),
        "pending": pending_res,
        "closed": closed_res,
        "new_signals": new_signals
    }
