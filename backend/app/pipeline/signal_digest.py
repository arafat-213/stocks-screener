import json
import datetime
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.db.models import TechnicalSignal, Stock
from app.backtest.engine import BacktestConfig, _compute_signal_tier, _is_consolidating
from app.pipeline.ohlcv_cache import OHLCVCache

logger = logging.getLogger(__name__)
_ohlcv_cache = OHLCVCache()

# Mirror your best-performing backtest config here — single source of truth
LIVE_CONFIG = BacktestConfig(
    score_threshold=60.0,
    holding_days=45,
    min_signal_tier=2,
    require_consolidation=True,
    use_pullback_entry=True,
    pullback_max_wait_bars=8,
    pullback_tolerance_pct=3.0,
    consolidation_bars=15,
    consolidation_max_range_pct=12.0,
    use_regime_filter=True,
    use_volatility_sizing=True,
    risk_per_trade_pct=1.0,
    max_position_pct=10.0,
    starting_capital=1_000_000.0,
)

def generate_signal_digest(db: Session, config: BacktestConfig = None) -> str | None:
    """
    Emits a daily JSON digest of signals that would trigger today under the live config.
    Stored in reports/digest_YYYY-MM-DD.json.
    This is forward validation without a stateful position engine:
    - Confirms the pipeline is producing signals
    - Lets you manually track whether signals play out
    - Catches parameter drift between backtest and live
    """
    if config is None:
        config = LIVE_CONFIG
    
    # Derive the latest date from the database to ensure we are digesting the right day
    max_date = db.query(func.max(TechnicalSignal.date)).scalar()
    if not max_date:
        logger.warning("No technical signals found to digest.")
        return None
    
    # max_date could be a datetime, we need the date part
    if isinstance(max_date, str):
        # Handle SQLite date strings if necessary, though SQLAlchemy should handle it
        today = datetime.datetime.strptime(max_date.split(' ')[0], "%Y-%m-%d").date()
    else:
        today = max_date.date()
    
    # Get regime state
    regime_bullish = _get_regime_state()
    
    # Fetch today's signals passing base filters
    signals = (
        db.query(TechnicalSignal, Stock.sector, Stock.name)
        .join(Stock, TechnicalSignal.symbol == Stock.symbol)
        .filter(
            and_(
                func.date(TechnicalSignal.date) == today,
                TechnicalSignal.timeframe == 'D',
                TechnicalSignal.above_200ema == True,
                TechnicalSignal.entry_score >= config.effective_score_threshold,
                TechnicalSignal.ema_signal.in_(['bullish_cross', 'bullish_pullback']),
            )
        )
        .all()
    )
    
    actionable = []
    watchlist = [] # passed score/EMA but failed tier or consolidation
    
    for sig, sector, name in signals:
        signal_dict = {
            'ema_signal': sig.ema_signal,
            'volume_breakout': sig.volume_breakout or False,
            'adx': sig.adx or 0.0,
            'rsi': sig.rsi or 0.0,
            'momentum_12m': sig.momentum_12m,
            'atr': sig.atr,
            'score': sig.entry_score,
        }
        
        tier = _compute_signal_tier(signal_dict)
        passes_tier = tier <= config.min_signal_tier
        
        # Consolidation check
        passes_consolidation = False
        if config.require_consolidation:
            df = _ohlcv_cache.get(sig.symbol, period='5y')
            if df is not None and not df.empty:
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                matching = df.index[df.index.date <= today]
                if not matching.empty:
                    idx = len(matching) - 1
                    passes_consolidation = _is_consolidating(
                        df, idx, lookback=config.consolidation_bars,
                        max_range_pct=config.consolidation_max_range_pct,
                    )
        else:
            passes_consolidation = True
            
        entry = {
            'symbol': sig.symbol,
            'name': name,
            'sector': sector,
            'score': sig.entry_score,
            'rsi': sig.rsi,
            'adx': sig.adx,
            'atr': sig.atr,
            'ema_signal': sig.ema_signal,
            'volume_breakout': sig.volume_breakout,
            'momentum_12m': sig.momentum_12m,
            'ema20': sig.ema20_level,
            'close': sig.close_price,
            'tier': tier,
            'passes_consolidation': passes_consolidation,
            # Pre-compute entry zone so you can act without re-running logic
            'pullback_entry_zone': (
                {
                    'target': round(sig.ema20_level, 2),
                    'tolerance_high': round(sig.ema20_level * (1 + config.pullback_tolerance_pct / 100), 2),
                } if sig.ema20_level and sig.ema_signal == 'bullish_cross' else None
            ),
            'stop_reference': (
                round(sig.close_price - config.atr_multiplier * sig.atr, 2) if sig.close_price and sig.atr else None
            ),
        }
        
        if passes_tier and passes_consolidation:
            actionable.append(entry)
        else:
            entry['skip_reason'] = (
                f"tier={tier}" if not passes_tier else "no_consolidation"
            )
            watchlist.append(entry)
            
    digest = {
        'date': today.isoformat(),
        'regime_bullish': regime_bullish,
        'config_snapshot': {
            'score_threshold': config.score_threshold,
            'effective_threshold': config.effective_score_threshold,
            'min_signal_tier': config.min_signal_tier,
            'require_consolidation': config.require_consolidation,
            'use_pullback_entry': config.use_pullback_entry,
        },
        'summary': {
            'total_candidates': len(signals),
            'actionable': len(actionable),
            'watchlist': len(watchlist),
        },
        'actionable': sorted(actionable, key=lambda x: x['score'], reverse=True),
        'watchlist': sorted(watchlist, key=lambda x: x['score'], reverse=True)[:20],
    }
    
    # Persist
    reports_dir = Path(__file__).resolve().parent.parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    out_path = reports_dir / f"digest_{today.isoformat()}.json"
    out_path.write_text(json.dumps(digest, indent=2, default=str))
    logger.info("Signal digest written: %s (%d actionable)", out_path, len(actionable))
    return str(out_path)

def _get_regime_state() -> bool:
    """Returns True if Nifty is in a bull regime (above 50 & 200 EMA, golden cross)."""
    try:
        df = _ohlcv_cache.get("^NSEI", append_ns=False, period='5y')
        if df is None or df.empty:
            return True
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        import pandas_ta_classic # noqa
        df.ta.ema(length=50, append=True)
        df.ta.ema(length=200, append=True)
        r = df.iloc[-1]
        return bool(
            r['Close'] > r.get('EMA_50', 0) and 
            r['Close'] > r.get('EMA_200', 0) and 
            r.get('EMA_50', 0) > r.get('EMA_200', 0)
        )
    except Exception:
        return True
