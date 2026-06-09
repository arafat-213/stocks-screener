import datetime
import json
import logging
from pathlib import Path

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.backtest.engine import _is_consolidating
from app.core.trading_config import (
    TREND_CONTINUATION,
    TREND_INITIATION,
    UnifiedTradingConfig,
)
from app.db.models import Stock, TechnicalSignal
from app.pipeline.ohlcv_cache import OHLCVCache

logger = logging.getLogger(__name__)
_ohlcv_cache = OHLCVCache()

# Mirror your best-performing backtest config here — single source of truth
LIVE_CONFIG = TREND_INITIATION


def generate_signal_digest(
    db: Session, configs: list[UnifiedTradingConfig] = None
) -> str | None:
    """
    Emits a daily JSON digest of signals that would trigger today under the live configs.
    Stored in reports/digest_YYYY-MM-DD.json.
    """
    if configs is None:
        configs = [TREND_INITIATION, TREND_CONTINUATION]

    # Derive the latest date from the database to ensure we are digesting the right day
    max_date = db.query(func.max(TechnicalSignal.date)).scalar()
    if not max_date:
        logger.warning("No technical signals found to digest.")
        return None

    # max_date could be a datetime, we need the date part
    if isinstance(max_date, str):
        today = datetime.datetime.strptime(max_date.split(" ")[0], "%Y-%m-%d").date()
    else:
        today = max_date.date()

    # Get regime state
    regime_bullish = _get_regime_state()

    qualified_signals = {}  # symbol -> {data, tags}

    for config in configs:
        # Fetch today's signals passing base filters for this config
        signals = (
            db.query(TechnicalSignal, Stock.sector, Stock.name)
            .join(Stock, TechnicalSignal.symbol == Stock.symbol)
            .filter(
                and_(
                    func.date(TechnicalSignal.date) == today,
                    TechnicalSignal.timeframe == "D",
                    TechnicalSignal.above_200ema,
                    TechnicalSignal.rsi >= config.rsi_min,
                    TechnicalSignal.rsi <= config.rsi_max,
                    TechnicalSignal.entry_score >= config.effective_score_threshold,
                    TechnicalSignal.ema_signal.in_(
                        ["bullish_cross", "bullish_pullback"]
                    ),
                )
            )
            .all()
        )

        for sig, sector, name in signals:
            # Consolidation check
            passes_consolidation = True
            if config.require_consolidation:
                df = _ohlcv_cache.get(sig.symbol, period="5y")
                if df is not None and not df.empty:
                    if df.index.tz is not None:
                        df.index = df.index.tz_convert(None)
                    matching = df.index[df.index.date <= today]
                    if not matching.empty:
                        idx = len(matching) - 1
                        passes_consolidation = _is_consolidating(
                            df,
                            idx,
                            lookback=config.consolidation_bars,
                            max_range_pct=config.consolidation_max_range_pct,
                        )
                    else:
                        passes_consolidation = False
                else:
                    passes_consolidation = False

            if not passes_consolidation:
                continue

            # Qualifies
            if sig.symbol in qualified_signals:
                if (
                    config.strategy_id
                    not in qualified_signals[sig.symbol]["strategy_tags"]
                ):
                    qualified_signals[sig.symbol]["strategy_tags"].append(
                        config.strategy_id
                    )
            else:
                tier = (
                    1
                    if (sig.volume_breakout and (sig.adx or 0.0) >= config.min_adx)
                    else 2
                )
                qualified_signals[sig.symbol] = {
                    "symbol": sig.symbol,
                    "name": name,
                    "sector": sector,
                    "score": sig.entry_score,
                    "rsi": sig.rsi,
                    "adx": sig.adx,
                    "atr": sig.atr,
                    "ema_signal": sig.ema_signal,
                    "volume_breakout": sig.volume_breakout,
                    "momentum_12m": sig.momentum_12m,
                    "ema21": sig.ema21_level,
                    "close": sig.close_price,
                    "tier": tier,
                    "strategy_tags": [config.strategy_id],
                }

    actionable = list(qualified_signals.values())

    digest = {
        "date": today.isoformat(),
        "regime_bullish": regime_bullish,
        "summary": {
            "total_actionable": len(actionable),
        },
        "actionable": sorted(actionable, key=lambda x: x["score"], reverse=True),
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
        df = _ohlcv_cache.get("^NSEI", append_ns=False, period="5y")
        if df is None or df.empty:
            return True
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)
        import pandas_ta_classic  # noqa

        df.ta.ema(length=50, append=True)
        df.ta.ema(length=200, append=True)
        r = df.iloc[-1]
        return bool(
            r["Close"] > r.get("EMA_50", 0)
            and r["Close"] > r.get("EMA_200", 0)
            and r.get("EMA_50", 0) > r.get("EMA_200", 0)
        )
    except Exception:
        return True
