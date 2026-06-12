import bisect
import datetime
import json
import logging
import traceback
from collections import Counter
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import pandas_ta_classic  # noqa
from sqlalchemy.orm import Session

from app.core.logging_manager import logging_manager
from app.core.strategy import TechnicalStrategy
from app.core.trading_config import UnifiedTradingConfig as BacktestConfig
from app.db.models import (
    BacktestRun,
    BacktestTrade,
    MarketBreadth,
    ScreenResult,
    Stock,
)
from app.pipeline.ohlcv_cache import OHLCVCache
from app.pipeline.utils import resample_ohlcv


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.float64, np.float32, np.float16)):
            return float(obj)
        if isinstance(obj, (np.int64, np.int32, np.int16)):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _clean(val):
    if hasattr(val, "item"):
        return val.item()
    return val


logger = logging.getLogger(__name__)
_ohlcv_cache = OHLCVCache()

# In-memory cache for cross-run optimization.
# Layer 1: Indicator cache (stable across all configs)
_INDICATOR_CACHE = {}  # {symbol: DataFrame}
_INDICATOR_META = {}  # {symbol: latest_date}

# Layer 2: Signal cache (invalidated when signal params change)
_SIGNAL_CACHE = {}  # {symbol: DataFrame}
_SIGNAL_META = {}  # {symbol: {"latest_date": date, "config_hash": int}}

# Parameters that actually affect calculate_indicators and calculate_signals.
# Changes to other params (like holding_days or risk_per_trade_pct) should not invalidate the TA cache.
_TA_RELEVANT_PARAMS = {
    "rsi_min",
    "rsi_max",
    "min_adx",
    "pullback_ema21_threshold_pct",
    "rsi_overbought_threshold",
}

# Cache for raw OHLCV data to avoid redundant Parquet reads during sequential runs.
_OHLCV_CACHE = {}  # {symbol: DataFrame}


ROUND_TRIP_COST_PCT = (
    0.25  # 0.25% per trade: reflects actual flat-fee brokerage reality
)


@dataclass
class TradeResult:
    symbol: str
    sector: str
    signal_date: datetime.date
    entry_date: datetime.date
    exit_date: datetime.date
    exit_reason: str  # 'holding_period' | 'stop_loss' | 'target'
    signal_score: float
    entry_price: float
    exit_price: float
    return_pct: float
    rsi_at_signal: float
    adx_at_signal: float
    ema_signal: str
    position_size_used: float = 0.0

    # Statistical and Regime Fields
    regime_at_signal: Optional[int] = None
    regime_at_entry: Optional[int] = None
    regime_at_exit: Optional[int] = None
    market_breadth_at_entry: Optional[float] = None
    consolidation_bars_at_signal: Optional[int] = None
    pullback_depth_pct: Optional[float] = None
    max_adverse_excursion_pct: Optional[float] = 0.0


def _get_cached_ohlcv(symbol: str, period: str = "5y") -> Optional[pd.DataFrame]:
    """
    Wraps _ohlcv_cache.get with a process-level in-memory cache to avoid
    redundant Parquet deserialization during sequential runs.
    """
    if symbol in _OHLCV_CACHE:
        return _OHLCV_CACHE[symbol]

    df = _ohlcv_cache.get(symbol, period=period)

    if df is not None and not df.empty:
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)

        _OHLCV_CACHE[symbol] = df
        return df

    return None


def build_mtf_state_map(
    df: pd.DataFrame, timeframe: str, strategy: Optional[TechnicalStrategy] = None
) -> dict:
    if df is None or df.empty:
        return {}

    if strategy is None:
        strategy = TechnicalStrategy()

    freq = "W" if timeframe == "W" else "ME"
    resampled = resample_ohlcv(df, freq=freq, drop_incomplete=True)
    if resampled.empty:
        return {}

    # NEW: Use vectorized calculation!
    resampled = strategy.calculate_indicators(resampled)
    resampled = strategy.calculate_signals(resampled, timeframe=timeframe)

    state_map = {}
    # Technical scoring needs some history (60 bars for W, 24 for M)
    min_bars = 24 if timeframe == "M" else 60

    for i in range(len(resampled)):
        if (i + 1) < min_bars:
            continue

        bar_date = resampled.index[i]
        if hasattr(bar_date, "date"):
            bar_date = bar_date.date()

        state_map[bar_date] = bool(resampled["IS_BULLISH"].iloc[i])

    return state_map


def _compute_all_indicators(
    df: pd.DataFrame, strategy: Optional[TechnicalStrategy] = None, symbol: str = None
) -> pd.DataFrame:
    """
    Computes all pandas-ta indicators and signals.
    Splits computation into two cache layers to optimize parameter sweeps:
    1. Indicator Layer: Stable across most parameter changes.
    2. Signal Layer: Recomputed when signal-specific parameters change.
    """
    if strategy is None:
        strategy = TechnicalStrategy()

    # Hash only the params that actually affect signal logic
    config_dict = vars(strategy.config)
    ta_relevant = {k: config_dict[k] for k in _TA_RELEVANT_PARAMS if k in config_dict}
    current_config_hash = hash(str(tuple(sorted(ta_relevant.items()))))
    latest_date = df.index[-1]

    # Layer 1: Indicator cache (stable across all configs)
    if (
        symbol
        and symbol in _INDICATOR_CACHE
        and _INDICATOR_META.get(symbol) == latest_date
    ):
        df_with_indicators = _INDICATOR_CACHE[symbol]
    else:
        df_with_indicators = strategy.calculate_indicators(df)
        if symbol:
            _INDICATOR_CACHE[symbol] = df_with_indicators
            _INDICATOR_META[symbol] = latest_date

    # Layer 2: Signal cache (invalidated when signal params change)
    if symbol and symbol in _SIGNAL_CACHE:
        meta = _SIGNAL_META.get(symbol, {})
        if (
            meta.get("latest_date") == latest_date
            and meta.get("config_hash") == current_config_hash
        ):
            return _SIGNAL_CACHE[symbol]

    # Compute signals. Use a copy to avoid polluting Layer 1 cache with signal columns
    df_with_signals = strategy.calculate_signals(df_with_indicators.copy())

    if symbol:
        _SIGNAL_CACHE[symbol] = df_with_signals
        _SIGNAL_META[symbol] = {
            "latest_date": latest_date,
            "config_hash": current_config_hash,
        }

    return df_with_signals


def _score_bar_from_precomputed(
    df_ind: pd.DataFrame, i: int, strategy: Optional[TechnicalStrategy] = None
) -> dict:
    """
    Wrapper for calculate_technical_score using pre-computed indicators.
    Maps results to the format expected by the backtest engine.
    """
    if strategy is None:
        strategy = TechnicalStrategy()

    res = strategy.evaluate(df_ind, timeframe="D", i=i, skip_ta=True)

    # Add backtest-specific keys for compatibility
    res["date"] = df_ind.index[i]
    res["close"] = float(df_ind["Close"].iloc[i])

    return res


def _calculate_breadth_map(
    all_dfs: dict[str, pd.DataFrame],
) -> dict[datetime.date, float]:
    """
    Calculates the percentage of stocks above their 200 EMA per day
    using the already loaded Parquet dataframes.

    Explicitly handles EMA_200 warmup by only including symbols with
    valid (non-NaN) EMA values in the calculation for each date.
    """
    if not all_dfs:
        return {}

    # Extract Close and EMA200 for all symbols
    close_series = {}
    ema_series = {}

    for sym, df in all_dfs.items():
        if "Close" in df.columns and "EMA_200" in df.columns:
            # Ensure naive index for consistency
            idx = df.index
            if hasattr(idx, "tz") and idx.tz is not None:
                idx = idx.tz_localize(None)

            # We use the full index but only populate values where we have data
            close_series[sym] = pd.Series(df["Close"].values, index=idx)
            ema_series[sym] = pd.Series(df["EMA_200"].values, index=idx)

    if not close_series:
        return {}

    # Create DataFrames for vectorized comparison
    close_df = pd.DataFrame(close_series)
    ema_df = pd.DataFrame(ema_series)

    # Boolean matrix: True if Close > EMA200 (NaN results in False)
    above_mask = close_df > ema_df

    # Active stocks: Count only those where EMA_200 is NOT NaN (finished warmup)
    active_stocks = ema_df.notna().sum(axis=1)

    # Calculate breadth: (Sum of stocks above EMA / count of warmed-up stocks) * 100
    breadth_series = pd.Series(0.0, index=close_df.index)
    valid_mask = active_stocks > 0
    breadth_series[valid_mask] = (
        above_mask[valid_mask].sum(axis=1) / active_stocks[valid_mask]
    ) * 100

    # Convert to dict with date keys for engine lookup
    return {
        d.date() if hasattr(d, "date") else d: float(v)
        for d, v in breadth_series[valid_mask].items()
    }


def _load_breadth_map(
    db: Session, date_from: datetime.date, date_to: datetime.date
) -> dict[datetime.date, float]:
    """
    Loads pre-calculated market breadth (Nifty 500 proxy) from the database.
    """
    if not date_from or not date_to:
        return {}

    rows = (
        db.query(MarketBreadth.date, MarketBreadth.breadth_pct)
        .filter(MarketBreadth.date >= date_from, MarketBreadth.date <= date_to)
        .all()
    )

    return {r.date: float(r.breadth_pct) for r in rows}


def _check_mtf_confirmation(date: datetime.date, state_map: dict) -> bool:
    if not state_map:
        return True
    if date in state_map:
        return state_map[date]
    sorted_dates = sorted(state_map.keys())
    idx = bisect.bisect_right(sorted_dates, date)
    if idx == 0:
        return False
    return state_map[sorted_dates[idx - 1]]


def _nan_to_default(val, default):
    """Return default if val is None, NaN, or non-finite."""
    try:
        f = float(val)
        return f if pd.notna(f) else default
    except (TypeError, ValueError):
        return default


def _build_regime_map(
    bench_df: pd.DataFrame, config: BacktestConfig, breadth_map: dict = None
) -> dict[datetime.date, int]:
    """
    Pre-calculates a mapping from date to regime ID.
    Regimes:
    - BULL (2): RSI > 60 and ADX > 20 -> Full size (regime_bull_position_pct)
    - BEAR (0): RSI < 45 or Price < EMA200 -> Cash (regime_bear_position_pct)
    - NEUTRAL (1): Everything else -> Reduced size (regime_neutral_position_pct)
    """
    if bench_df is None or bench_df.empty:
        return {}

    # Ensure required indicators are present
    if "RSI_14" not in bench_df.columns:
        return {}
    if "ADX_14" not in bench_df.columns:
        bench_df.ta.adx(length=14, append=True)
    if "EMA_200" not in bench_df.columns:
        bench_df.ta.ema(length=200, append=True)

    regime_map = {}
    current_regime = 1  # Start Neutral
    confirmation_counter = 0
    target_days = config.regime_confirmation_days

    # Iterate through benchmark data
    for i in range(len(bench_df)):
        row = bench_df.iloc[i]
        date = bench_df.index[i].date()

        rsi = _nan_to_default(row.get("RSI_14"), 50.0)
        adx = _nan_to_default(row.get("ADX_14"), 0.0)
        close = _nan_to_default(row.get("Close"), 0.0)
        ema200 = _nan_to_default(row.get("EMA_200"), 0.0)

        breadth = (breadth_map or {}).get(date, 100.0)

        # Determine "Potential" Regime with SMART OVERRIDES
        if adx < config.regime_adx_floor:
            if breadth > 60.0:
                potential_regime = 2  # Hidden Bull
            elif breadth < config.min_market_breadth_pct:
                potential_regime = 0  # Dangerous Sideways
            else:
                potential_regime = 1  # Normal Neutral
        elif close < ema200 or rsi < config.regime_bear_rsi_threshold:
            potential_regime = 0  # BEAR
        elif (
            rsi > config.regime_bull_rsi_threshold and adx > config.regime_adx_threshold
        ):
            potential_regime = 2  # BULL
        else:
            potential_regime = 1  # NEUTRAL

        # Apply Hysteresis/Debounce
        if potential_regime == current_regime:
            confirmation_counter = 0
        else:
            confirmation_counter += 1
            if confirmation_counter >= target_days:
                current_regime = potential_regime
                confirmation_counter = 0

        regime_map[date] = current_regime

    return regime_map


def _compute_position_size(
    config: BacktestConfig,
    entry_price: float,
    atr: float = None,
    regime_max_pct: float = None,
) -> float:
    if not config.use_volatility_sizing or atr is None or atr <= 0:
        return config.position_size

    risk_amount = config.starting_capital * (config.risk_per_trade_pct / 100.0)
    stop_distance = config.initial_stop_atr_multiplier * atr
    if stop_distance <= 0:
        return config.position_size

    shares = risk_amount / stop_distance
    pos_size = shares * entry_price

    # Use regime-adjusted cap if provided, otherwise fall back to config
    effective_max_pct = (
        regime_max_pct if regime_max_pct is not None else config.max_position_pct
    )
    max_allowed = config.starting_capital * (effective_max_pct / 100.0)
    return min(pos_size, max_allowed)


def _build_screen_driven_signals(
    symbol: str,
    screen_dates: list[datetime.date],
    df: pd.DataFrame,
    config: BacktestConfig,
    strategy: TechnicalStrategy,
) -> list[dict]:
    """
    Model B signal builder.
    Each date the stock appeared in the named screen becomes a candidate signal.
    """
    if df is None or df.empty or not screen_dates:
        return []

    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_convert(None)

    df_ind = _compute_all_indicators(df, strategy, symbol=symbol)
    date_to_idx = {
        d.date() if hasattr(d, "date") else d: i for i, d in enumerate(df.index)
    }

    signals = []
    last_signal_date = None
    reentry_gap = config.screen_reentry_gap_days

    for screen_date in sorted(screen_dates):
        if last_signal_date is not None:
            if (screen_date - last_signal_date).days < reentry_gap:
                continue

        idx = date_to_idx.get(screen_date)
        if idx is None or idx < 260:
            continue

        if config.date_from and screen_date < config.date_from:
            continue
        if config.date_to and screen_date > config.date_to:
            continue

        try:
            bar = _score_bar_from_precomputed(df_ind, idx, strategy)
        except Exception:
            continue

        if bar.get("above_200ema") is not True:
            continue
        if bar.get("momentum_12m") is not None and bar["momentum_12m"] < 0:
            continue

        rsi_max = config.screen_driven_rsi_max
        if (bar.get("rsi") or 0.0) > rsi_max:
            continue

        signals.append(
            {
                "date": df.index[idx],
                "score": 100.0,
                "is_bullish": True,
                "rsi": bar["rsi"],
                "adx": bar["adx"],
                "ema_signal": bar["ema_signal"] or "bullish",
                "volume_signal": bar.get("volume_signal", "neutral"),
                "rsi_signal": bar.get("rsi_signal", "neutral"),
                "close": float(df_ind["Close"].iloc[idx]),
                "open": float(df_ind["Open"].iloc[idx]),
                "volume_breakout": bar["volume_breakout"],
                "atr": bar["atr"],
                "above_200ema": True,
                "momentum_12m": bar["momentum_12m"],
                "momentum_3m": bar["momentum_3m"],
                "ema21_level": bar["ema21_level"],
                "is_consolidating": True,
            }
        )
        last_signal_date = screen_date

    return signals


def score_series(
    df: pd.DataFrame,
    strategy: Optional[TechnicalStrategy] = None,
    symbol: str = None,
    config: BacktestConfig = None,
) -> list[dict]:
    if df is None or df.empty:
        return []

    if strategy is None:
        strategy = TechnicalStrategy(config)

    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_convert(None)

    df_ind = _compute_all_indicators(df, strategy, symbol=symbol)

    # Precompute consolidation (vectorized) - EXCLUDE current bar to match live pipeline
    # The live pipeline calls _is_consolidating(df, idx) which uses df.iloc[idx-15:idx]
    consol_window = config.consolidation_bars if config else 15
    max_range_pct = config.consolidation_max_range_pct if config else 12.0
    rolling_max = df_ind["High"].shift(1).rolling(window=consol_window).max()
    rolling_min = df_ind["Low"].shift(1).rolling(window=consol_window).min()
    consol_range = (rolling_max / rolling_min - 1) * 100
    is_consolidating_arr = (consol_range <= max_range_pct).to_numpy(dtype=bool)

    # ── VECTORIZED PRE-FILTER ─────────────────────────────────────────────────
    # Only call evaluate() on bars with an actual EMA entry signal.
    # Reduces evaluate() calls by ~97% on a typical 5-year daily series.
    if (
        "SIGNAL_EMA_CROSS" in df_ind.columns
        and "SIGNAL_PULLBACK_21" in df_ind.columns
        and "EMA_5" in df_ind.columns
        and "EMA_13" in df_ind.columns
        and "EMA_21" in df_ind.columns
    ):
        ema_continuation = (
            (df_ind["EMA_5"] > df_ind["EMA_13"])
            & (df_ind["EMA_13"] > df_ind["EMA_21"])
            & (df_ind["Close"] > df_ind["EMA_21"])
        ).fillna(False)

        mask = (
            df_ind["SIGNAL_EMA_CROSS"].fillna(False)
            | df_ind["SIGNAL_PULLBACK_21"].fillna(False)
            | ema_continuation
        ).to_numpy(dtype=bool)
    else:
        mask = (
            df_ind.get("IS_BULLISH", pd.Series(True, index=df_ind.index))
            .fillna(False)
            .to_numpy(dtype=bool)
        )

    # Hard filters — pre-reject what simulate_trades would reject anyway
    if "EMA_200" in df_ind.columns:
        mask &= (df_ind["Close"] > df_ind["EMA_200"]).fillna(False).to_numpy(dtype=bool)
    if "MOMENTUM_12M" in df_ind.columns:
        mask &= (df_ind["MOMENTUM_12M"] > 0).fillna(False).to_numpy(dtype=bool)

    if config and config.max_pct_from_52w_high < 0 and "WEEK52_HIGH" in df_ind.columns:
        week52_high = df_ind["WEEK52_HIGH"].to_numpy(dtype=float)
        close_arr = df_ind["Close"].to_numpy(dtype=float)
        # pct_from_high is negative when below 52w high
        pct_from_high = np.where(
            week52_high > 0, (close_arr / week52_high - 1) * 100, 0.0
        )
        mask &= pct_from_high >= config.max_pct_from_52w_high
        mask &= ~np.isnan(pct_from_high)

    if config and "ADX_14" in df_ind.columns:
        adx_arr = df_ind["ADX_14"].to_numpy(dtype=float)
        mask &= (adx_arr >= config.min_adx) & ~np.isnan(adx_arr)

    if config and "RSI_14" in df_ind.columns:
        rsi_arr = df_ind["RSI_14"].to_numpy(dtype=float)
        mask &= (
            (rsi_arr >= config.rsi_min)
            & (rsi_arr <= config.rsi_max)
            & ~np.isnan(rsi_arr)
        )

    # Warmup fence
    mask[:260] = False

    # Date-range fence
    if config:
        if config.date_from:
            lo = int(np.searchsorted(df_ind.index, pd.Timestamp(config.date_from)))
            mask[:lo] = False
        if config.date_to:
            hi = int(
                np.searchsorted(
                    df_ind.index, pd.Timestamp(config.date_to), side="right"
                )
            )
            mask[hi:] = False

    # ── SCORE ONLY CANDIDATE BARS ─────────────────────────────────────────────
    scored_dates = []
    for i in np.flatnonzero(mask):
        bar_score = _score_bar_from_precomputed(df_ind, int(i), strategy)
        if bar_score.get("score", 0.0) <= 0.0:
            continue
        bar_score["is_consolidating"] = bool(is_consolidating_arr[i])
        # Soft penalty for non-consolidating entries ONLY if not using the hard gate
        # (If require_consolidation is True, simulate_trades skips the trade entirely)
        if not bar_score["is_consolidating"] and not (
            config and config.require_consolidation
        ):
            bar_score["score"] *= 0.85
        scored_dates.append(bar_score)

    return scored_dates


def simulate_trades(
    symbol: str,
    sector: str,
    df: pd.DataFrame,
    scored_dates: list[dict],
    config: BacktestConfig,
    strategy: Optional[TechnicalStrategy] = None,
    weekly_state_map: dict = None,
    monthly_state_map: dict = None,
    screen_dates: list[datetime.date] | None = None,
    is_screen_driven: bool = False,
    regime_scaling_map: dict = None,
    breadth_map: dict = None,
):
    if strategy is None:
        strategy = TechnicalStrategy(config)

    # Ensure we have vectorized signals for optimized exits
    if config.use_state_based_exits and "IS_OVEREXTENDED" not in df.columns:
        df = strategy.calculate_signals(df)

    trades = []
    last_exit_idx = -1
    _sorted_screen_dates = sorted(screen_dates) if screen_dates else None

    # Pre-sort map keys for robust and fast lookups
    sorted_scaling_keys = (
        sorted(regime_scaling_map.keys()) if regime_scaling_map else []
    )
    sorted_weekly_keys = sorted(weekly_state_map.keys()) if weekly_state_map else []
    sorted_monthly_keys = sorted(monthly_state_map.keys()) if monthly_state_map else []

    date_to_idx = {date: i for i, date in enumerate(df.index)}

    for signal in scored_dates:
        signal_date = signal["date"]
        compare_date = (
            signal_date.date() if hasattr(signal_date, "date") else signal_date
        )

        if config:
            if config.date_from and compare_date < config.date_from:
                continue
            if config.date_to and compare_date > config.date_to:
                continue

        # Market Breadth Gate (New)
        current_breadth = (breadth_map or {}).get(compare_date, 100.0)
        if current_breadth < config.min_market_breadth_pct:
            continue

        # MTF Confirmation Gates
        if config.require_weekly_confirmation and weekly_state_map:
            w_idx = bisect.bisect_right(sorted_weekly_keys, compare_date)
            if w_idx == 0 or not weekly_state_map[sorted_weekly_keys[w_idx - 1]]:
                continue

        if config.require_monthly_confirmation and monthly_state_map:
            m_idx = bisect.bisect_right(sorted_monthly_keys, compare_date)
            if m_idx == 0 or not monthly_state_map[sorted_monthly_keys[m_idx - 1]]:
                continue

        if _sorted_screen_dates is not None and not is_screen_driven:
            window_days = config.screen_membership_window_days
            window_start = compare_date - datetime.timedelta(days=window_days)
            lo = bisect.bisect_left(_sorted_screen_dates, window_start)
            hi = bisect.bisect_right(_sorted_screen_dates, compare_date)
            if lo >= hi:
                continue

        signal_idx = date_to_idx.get(signal_date)
        if signal_idx is None or signal_idx <= last_exit_idx:
            continue

        # Signal Bar Volatility Filter (Task 2)
        # Prevents entering if the signal bar itself is so large it exhausts the risk budget
        signal_bar = df.iloc[signal_idx]
        sig_high, sig_low, sig_close = (
            signal_bar["High"],
            signal_bar["Low"],
            signal_bar["Close"],
        )

        if sig_close > 0:
            sig_range_pct = (sig_high - sig_low) / sig_close * 100
            atr = signal.get("atr") or 0.0
            atr_stop_pct = (
                (config.initial_stop_atr_multiplier * atr) / sig_close * 100
                if atr > 0
                else 0.0
            )
            hard_stop_pct = config.stop_loss_pct

            # Intended stop is the tighter of ATR or Hard Stop (as used in entry logic)
            if atr_stop_pct > 0 and hard_stop_pct > 0:
                intended_stop_pct = min(atr_stop_pct, hard_stop_pct)
            else:
                intended_stop_pct = atr_stop_pct or hard_stop_pct

            if intended_stop_pct > 0 and sig_range_pct > (
                intended_stop_pct * config.max_signal_volatility_mult
            ):
                continue

        if signal.get("above_200ema") in [False, None]:
            continue
        if signal.get("momentum_12m") is not None and signal["momentum_12m"] < 0:
            continue

        if not is_screen_driven:
            # Signal Tier Filtering (Issue 1)
            adx_val = signal.get("adx") or 0.0
            vol_breakout = signal.get("volume_breakout") or False

            if vol_breakout and adx_val >= config.tier1_adx_threshold:
                signal_tier = 1
            elif vol_breakout or adx_val >= config.min_adx:
                signal_tier = 2
            else:
                signal_tier = 3

            if signal_tier > config.min_signal_tier:
                continue

            if (signal.get("rsi") or 0.0) > config.rsi_max:
                continue
            if signal["score"] < config.effective_score_threshold:
                continue
            if config.require_consolidation and not signal.get("is_consolidating"):
                continue
            # Note: volume_breakout is now handled by signal_tier

        # Entry Logic
        ema_signal_type = signal.get("ema_signal", "")
        signal_ema21 = signal.get("ema21_level")

        entry_idx = None
        entry_price = None
        entry_date = None

        use_pullback = (
            config.use_pullback_entry
            and ema_signal_type == "bullish_cross"
            and signal_ema21 is not None
            and signal_ema21 > 0
        )

        if use_pullback:
            tol = config.pullback_tolerance_pct / 100.0
            all_bars_above = True
            closest_approach = float("inf")
            signal_close = df.iloc[signal_idx]["Close"]

            for wait_k in range(
                signal_idx + 1,
                min(signal_idx + config.pullback_max_wait_bars + 1, len(df)),
            ):
                wait_compare = df.index[wait_k].date()

                current_breadth = (breadth_map or {}).get(wait_compare, 100.0)
                if current_breadth < config.min_market_breadth_pct:
                    all_bars_above = False
                    break

                low, close = df.iloc[wait_k]["Low"], df.iloc[wait_k]["Close"]
                # Fix: Use the contemporary EMA 21 value, not the signal-day reference
                # Ensure we handle NaN correctly by falling back to signal_ema21
                current_ema21 = df.iloc[wait_k].get("EMA_21")
                if pd.isna(current_ema21) or not current_ema21:
                    current_ema21 = signal_ema21

                # Bearish invalidation: price drops below threshold (linked to SL)
                # Fix: Replaced hardcoded 5% with strategy's stop loss percentage (Issue 7)
                invalidation_limit = 1.0 - (config.stop_loss_pct / 100.0)
                if close < signal_close * invalidation_limit:
                    all_bars_above = False
                    break

                if current_ema21 and current_ema21 > 0:
                    approach = (low - current_ema21) / current_ema21 * 100
                    closest_approach = min(closest_approach, approach)
                    if (
                        low <= current_ema21 * (1 + tol)
                        and close >= current_ema21 * 0.995
                    ):
                        # Fix: Entry happens on the NEXT bar Open to avoid lookahead/execution bias
                        entry_idx = wait_k + 1
                        if entry_idx < len(df):
                            entry_date = df.index[entry_idx]

                            # Verify breadth on the actual entry day
                            entry_breadth = (breadth_map or {}).get(
                                entry_date.date(), 100.0
                            )
                            if entry_breadth < config.min_market_breadth_pct:
                                entry_idx = None
                                break

                            entry_price = float(df.iloc[entry_idx]["Open"])
                            break
                        else:
                            entry_idx = None
                            break
            if (
                config.use_pullback_fallback
                and entry_idx is None
                and all_bars_above
                and closest_approach <= 8.0
            ):
                last_k = min(signal_idx + config.pullback_max_wait_bars, len(df) - 1)
                entry_idx, entry_date, entry_price = (
                    last_k,
                    df.index[last_k],
                    float(df.iloc[last_k]["Open"]),
                )
        else:
            entry_idx = signal_idx + 1
            if entry_idx < len(df):
                entry_date = df.index[entry_idx]

                current_breadth = (breadth_map or {}).get(entry_date.date(), 100.0)
                if current_breadth < config.min_market_breadth_pct:
                    continue

                entry_price = float(df.iloc[entry_idx]["Open"])

        if entry_idx is None or entry_idx >= len(df):
            continue

        if is_screen_driven and entry_idx >= 21:
            mom = df.iloc[entry_idx]["Close"] / df.iloc[entry_idx - 21]["Close"] - 1
            if mom < 0:
                continue

        # Risk Management
        raw_atr = signal.get("atr") or 0.0
        eff_atr = max(raw_atr, entry_price * 0.015)

        # ── REGIME & STATS CAPTURE ───────────────────────────────────────────
        # Determine regime IDs at critical points
        r_idx_signal = bisect.bisect_right(sorted_scaling_keys, compare_date)
        regime_id_signal = (
            regime_scaling_map[sorted_scaling_keys[r_idx_signal - 1]]
            if r_idx_signal > 0
            else 1
        )

        entry_compare_date = (
            entry_date.date() if hasattr(entry_date, "date") else entry_date
        )
        r_idx_entry = bisect.bisect_right(sorted_scaling_keys, entry_compare_date)
        regime_id_entry = (
            regime_scaling_map[sorted_scaling_keys[r_idx_entry - 1]]
            if r_idx_entry > 0
            else 1
        )

        regime_max_pct = None
        if config.use_regime_position_scaling and regime_scaling_map:
            if regime_id_entry == 0:
                regime_max_pct = config.regime_bear_position_pct
            elif regime_id_entry == 2:
                regime_max_pct = config.regime_bull_position_pct
            else:
                regime_max_pct = config.regime_neutral_position_pct

            if regime_max_pct <= 0.0:
                continue  # Skip trade entirely in Bear regime

        # Additional Stats
        breadth_at_entry = (breadth_map or {}).get(entry_compare_date, 100.0)
        consolidation_bars = signal.get("consolidation_bars")
        if consolidation_bars is None:
            # Fallback: if it was required and passed, use config value
            consolidation_bars = (
                config.consolidation_bars if signal.get("is_consolidating") else 0
            )

        # Pullback depth: depth from signal close to the lowest low before entry
        pullback_depth = 0.0
        if use_pullback:
            signal_close = df.iloc[signal_idx]["Close"]
            # Entry idx is when we actually entered. Lowest low between signal and entry.
            lowest_low = df.iloc[signal_idx : entry_idx + 1]["Low"].min()
            pullback_depth = max(0.0, (1 - lowest_low / signal_close) * 100)

        pos_size = _compute_position_size(
            config, entry_price, atr=eff_atr, regime_max_pct=regime_max_pct
        )

        # Robust Stop Anchoring (Task 3)
        # 1. Structural Stop (Tighter of pre-signal or pre-entry consolidation)
        consol_bars = signal.get("consolidation_bars") or config.consolidation_bars
        pre_signal_low = df.iloc[max(0, signal_idx - consol_bars) : signal_idx][
            "Low"
        ].min()
        pre_entry_low = df.iloc[max(0, entry_idx - consol_bars) : entry_idx][
            "Low"
        ].min()

        # Use the tighter (higher) of the two lows to reduce risk
        if pd.isna(pre_signal_low) and pd.isna(pre_entry_low):
            consol_low = np.nan
        else:
            consol_low = np.nanmax([pre_signal_low, pre_entry_low])
        struct_stop = consol_low * 0.98 if pd.notna(consol_low) else 0.0

        # 2. Volatility Stop
        vol_stop = entry_price - (config.initial_stop_atr_multiplier * eff_atr)

        # 3. Hard Cap Stop
        hard_cap_stop = (
            entry_price * (1 - config.stop_loss_pct / 100)
            if config.stop_loss_pct > 0
            else 0.0
        )

        # Final Hybrid Stop (Tighter of the three = Highest Price)
        stop_price = max(struct_stop, vol_stop, hard_cap_stop)

        # Sanity Clamp: Stop must be at least 1% below entry
        stop_price = min(stop_price, entry_price * 0.99)

        actual_risk = max(entry_price - stop_price, entry_price * 0.01)
        target_price = (
            entry_price * (1 + config.target_pct / 100)
            if config.target_pct > 0
            else entry_price + config.risk_reward_ratio * actual_risk
        )

        t1_price = entry_price + actual_risk if config.use_partial_exits else None
        exit_price, exit_date, exit_reason = None, None, "holding_period"
        t1_hit, t1_trade = False, None
        final_idx = min(entry_idx + config.holding_days - 1, len(df) - 1)
        peak_price = entry_price
        trough_price = entry_price
        bear_bars = 0
        inv_floor = entry_price * (1 - config.invalidation_threshold_pct / 100)
        trail_floor_active = False

        for k in range(entry_idx, final_idx + 1):
            low, high, close = (
                df.iloc[k]["Low"],
                df.iloc[k]["High"],
                df.iloc[k]["Close"],
            )

            peak_price = max(peak_price, high)
            trough_price = min(trough_price, low)

            # Staged De-risking Logic
            # 1. At 2.0R: Move stop to Entry (Breakeven) - Highest priority
            if high >= entry_price + 2.0 * actual_risk:
                stop_price = max(stop_price, entry_price)
            # 2. At 1.5R: Move stop to Entry - 0.5 * actual_risk (reduce risk by half)
            elif high >= entry_price + 1.5 * actual_risk:
                new_stop = entry_price - 0.5 * actual_risk
                stop_price = max(stop_price, new_stop)

            if config.trailing_stop_pct > 0:
                trail = peak_price * (1 - config.trailing_stop_pct / 100)
                if trail > stop_price:
                    stop_price = trail
                    trail_floor_active = True

            if config.use_atr_trailing_stop and eff_atr > 0:
                if peak_price >= entry_price + config.atr_trailing_activation * eff_atr:
                    trail = peak_price - config.atr_trailing_multiplier * eff_atr
                    if trail > stop_price:
                        stop_price = trail
                        trail_floor_active = True

            if config.use_signal_invalidation_exit:
                if close < inv_floor:
                    bear_bars += 1
                else:
                    bear_bars = 0
                if bear_bars >= 2:
                    exit_idx = min(k + 1, len(df) - 1)
                    exit_price, exit_date, exit_reason = (
                        df.iloc[exit_idx]["Open"],
                        df.index[exit_idx],
                        "signal_invalidated",
                    )
                    break

            if config.use_state_based_exits:
                is_overextended = df["IS_OVEREXTENDED"].iloc[k]
                if is_overextended:
                    prev_low = df.iloc[k - 1]["Low"] if k > 0 else low
                    if close < prev_low:
                        exit_idx = min(k + 1, len(df) - 1)
                        exit_price, exit_date, exit_reason = (
                            df.iloc[exit_idx]["Open"],
                            df.index[exit_idx],
                            "overextended_exit",
                        )
                        break

            if not t1_hit and t1_price and high >= t1_price:
                t1_hit = True
                t1_exit_date = (
                    df.index[k].date() if hasattr(df.index[k], "date") else df.index[k]
                )
                r_idx_exit_t1 = bisect.bisect_right(sorted_scaling_keys, t1_exit_date)
                regime_id_exit_t1 = (
                    regime_scaling_map[sorted_scaling_keys[r_idx_exit_t1 - 1]]
                    if r_idx_exit_t1 > 0
                    else 1
                )
                t1_trade = TradeResult(
                    symbol,
                    sector,
                    (
                        signal_date.date()
                        if hasattr(signal_date, "date")
                        else signal_date
                    ),
                    (entry_date.date() if hasattr(entry_date, "date") else entry_date),
                    t1_exit_date,
                    "target_partial",
                    signal.get("score", 0),
                    entry_price,
                    t1_price,
                    float((t1_price / entry_price - 1) * 100),
                    signal.get("rsi", 0),
                    signal.get("adx", 0),
                    signal.get("ema_signal", "neutral"),
                    pos_size * 0.5,
                    regime_at_signal=regime_id_signal,
                    regime_at_entry=regime_id_entry,
                    regime_at_exit=regime_id_exit_t1,
                    market_breadth_at_entry=breadth_at_entry,
                    consolidation_bars_at_signal=consolidation_bars,
                    pullback_depth_pct=pullback_depth,
                    max_adverse_excursion_pct=float(
                        max(0.0, (entry_price - trough_price) / entry_price * 100)
                    ),
                )
                stop_price, pos_size = entry_price, pos_size * 0.5

            if high >= target_price:
                exit_price, exit_date, exit_reason = target_price, df.index[k], "target"
                break
            if low <= stop_price:
                exit_price, exit_date, exit_reason = (
                    stop_price,
                    df.index[k],
                    "atr_trailing_stop" if trail_floor_active else "stop_loss",
                )
                break
            if k == final_idx:
                exit_price, exit_date = close, df.index[k]
                break

        if t1_trade:
            trades.append(t1_trade)

        exit_date_final = exit_date.date() if hasattr(exit_date, "date") else exit_date
        r_idx_exit = bisect.bisect_right(sorted_scaling_keys, exit_date_final)
        regime_id_exit = (
            regime_scaling_map[sorted_scaling_keys[r_idx_exit - 1]]
            if r_idx_exit > 0
            else 1
        )

        trades.append(
            TradeResult(
                symbol,
                sector,
                (signal_date.date() if hasattr(signal_date, "date") else signal_date),
                (entry_date.date() if hasattr(entry_date, "date") else entry_date),
                exit_date_final,
                exit_reason,
                signal["score"],
                entry_price,
                exit_price,
                float((exit_price / entry_price - 1) * 100),
                signal["rsi"],
                signal["adx"],
                signal["ema_signal"],
                pos_size,
                regime_at_signal=regime_id_signal,
                regime_at_entry=regime_id_entry,
                regime_at_exit=regime_id_exit,
                market_breadth_at_entry=breadth_at_entry,
                consolidation_bars_at_signal=consolidation_bars,
                pullback_depth_pct=pullback_depth,
                max_adverse_excursion_pct=float(
                    max(0.0, (entry_price - trough_price) / entry_price * 100)
                ),
            )
        )
        last_exit_idx = date_to_idx.get(exit_date, -1)

    return trades


def _is_portfolio_valid(
    candidate_trades: list[TradeResult],
    existing_trades: list[TradeResult],
    config: BacktestConfig,
    stocks_info: dict[str, str],
) -> bool:
    """
    Robustly validates portfolio-level constraints (capital, concurrency, sector)
    across the entire lifespan of the candidate trade to prevent race conditions
    caused by delayed entries (pullbacks).
    """
    if not candidate_trades:
        return True

    start_date = candidate_trades[0].entry_date
    end_date = candidate_trades[-1].exit_date

    # Event dates: points in time where utilization changes
    check_dates = {start_date}
    for t in existing_trades + candidate_trades:
        if start_date <= t.entry_date <= end_date:
            check_dates.add(t.entry_date)
        if start_date <= t.exit_date <= end_date:
            check_dates.add(t.exit_date)

    for d in sorted(check_dates):
        # A trade is active if d is within [entry, exit]
        active_existing = [
            t for t in existing_trades if t.entry_date <= d <= t.exit_date
        ]
        active_candidate = [
            t for t in candidate_trades if t.entry_date <= d <= t.exit_date
        ]

        if not active_candidate:
            continue

        # 1. Capital utilization (Hard Cap)
        total_used = sum(t.position_size_used for t in active_existing) + sum(
            t.position_size_used for t in active_candidate
        )
        if total_used > config.starting_capital + 0.01:
            return False

        # 2. Max Concurrent Positions
        if config.max_concurrent_positions > 0:
            active_syms = {t.symbol for t in active_existing} | {
                t.symbol for t in active_candidate
            }
            if len(active_syms) > config.max_concurrent_positions:
                return False

        # 3. Max Sector Positions
        if config.max_sector_positions > 0:
            sector_counts = Counter()
            for t in active_existing:
                s = stocks_info.get(t.symbol, "Unknown")
                sector_counts[s] += 1
            for t in active_candidate:
                s = stocks_info.get(t.symbol, "Unknown")
                sector_counts[s] += 1

            if any(
                count > config.max_sector_positions for count in sector_counts.values()
            ):
                return False

    return True


def simulate_portfolio(
    all_signals: dict[str, list[dict]],
    all_dfs: dict[str, pd.DataFrame],
    stocks_info: dict[str, str],
    config: BacktestConfig,
    strategy: Optional[TechnicalStrategy] = None,
    weekly_state_maps: dict = None,
    monthly_state_maps: dict = None,
    screen_dates_map: dict = None,
    is_screen_driven: bool = False,
    regime_scaling_map: dict = None,
    breadth_map: dict = None,
) -> list[TradeResult]:
    if strategy is None:
        strategy = TechnicalStrategy(config)

    timeline = []
    for sym, signals in all_signals.items():
        for sig in signals:
            sig_date = sig["date"]
            date_only = sig_date.date() if hasattr(sig_date, "date") else sig_date
            timeline.append((date_only, sym, sig))
    timeline.sort(key=lambda x: x[0])

    all_trades, open_pos = [], {}
    for date, sym, sig in timeline:
        # Fast Filter 1: Don't allow overlapping trades in the same symbol
        if sym in open_pos and open_pos[sym] >= date:
            continue

        # Fast Filter 2: Heuristic check for concurrency at signal date
        if config.max_concurrent_positions > 0:
            active_count = sum(1 for d in open_pos.values() if d >= date)
            if active_count >= config.max_concurrent_positions:
                continue

        # Fast Filter 3: Heuristic check for sector limits at signal date
        if config.max_sector_positions > 0:
            sector = stocks_info.get(sym, "Unknown")
            sector_active = sum(
                1
                for other_sym, exit_d in open_pos.items()
                if stocks_info.get(other_sym) == sector and exit_d >= date
            )
            if sector_active >= config.max_sector_positions:
                continue

        df = all_dfs.get(sym)
        if df is None:
            continue

        candidate_trades = simulate_trades(
            sym,
            stocks_info.get(sym, "Unknown"),
            df,
            [sig],
            config,
            strategy,
            (weekly_state_maps or {}).get(sym),
            (monthly_state_maps or {}).get(sym),
            (screen_dates_map or {}).get(sym),
            is_screen_driven,
            regime_scaling_map=regime_scaling_map,
            breadth_map=breadth_map,
        )

        if candidate_trades:
            # Robust Check: Validate entire lifespan (fixes race condition)
            if _is_portfolio_valid(candidate_trades, all_trades, config, stocks_info):
                open_pos[sym] = candidate_trades[-1].exit_date
                all_trades.extend(candidate_trades)

    return all_trades


def compute_metrics(
    trades: list[TradeResult], benchmark_data: pd.DataFrame, config: BacktestConfig
):
    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "median_return_pct": 0.0,
            "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
            "total_return_pct": 0.0,
            "gross_return_pct": 0.0,
            "total_cost_drag_pct": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_duration": 0,
            "sharpe_ratio": 0.0,
            "benchmark_return_pct": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "avg_mae_pct": 0.0,
            "equity_curve": [],
            "exit_breakdown": {},
        }

    rets = [t.return_pct - ROUND_TRIP_COST_PCT for t in trades]
    psizes = [t.position_size_used or config.position_size for t in trades]
    maes = [t.max_adverse_excursion_pct or 0.0 for t in trades]
    # total_deployed = sum(psizes)
    win_mask = [r > 0 for r in rets]
    win_count = sum(win_mask)
    win_rate = win_count / len(trades) if trades else 0.0

    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]

    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    avg_mae = sum(maes) / len(maes) if maes else 0.0

    # Weighted versions for financial metrics like Profit Factor
    win_weight = sum(p for r, p in zip(rets, psizes) if r > 0)
    loss_weight = sum(p for r, p in zip(rets, psizes) if r <= 0)

    weighted_avg_win = (
        sum(r * p for r, p in zip(rets, psizes) if r > 0) / win_weight
        if win_weight > 0
        else 0.0
    )
    weighted_avg_loss = (
        sum(r * p for r, p in zip(rets, psizes) if r <= 0) / loss_weight
        if loss_weight > 0
        else 0.0
    )

    total_pnl = sum(r / 100.0 * p for r, p in zip(rets, psizes))
    total_ret = total_pnl / config.starting_capital * 100
    gross_ret = (
        sum(t.return_pct / 100.0 * p for t, p in zip(trades, psizes))
        / config.starting_capital
        * 100
    )

    equity_curve = []
    max_dd = 0.0
    max_dd_duration = 0
    sharpe = 0.0
    bench_ret = 0.0

    if benchmark_data is not None and not benchmark_data.empty:
        # Slice benchmark to exact backtest range to avoid Sharpe dilution
        # (run_backtest fetches extra lookback for indicators which we must exclude here)
        if config.date_from:
            benchmark_data = benchmark_data[
                benchmark_data.index >= pd.Timestamp(config.date_from)
            ]
        if config.date_to:
            benchmark_data = benchmark_data[
                benchmark_data.index <= pd.Timestamp(config.date_to)
            ]

        if not benchmark_data.empty:
            bench_dates = benchmark_data.index.normalize().date
            strat_by_date = {}
            for t, p in zip(trades, psizes):
                # Map exit_date to next available benchmark date (handles weekends/holidays)
                exit_d = t.exit_date
                idx = bisect.bisect_left(bench_dates, exit_d)
                mapped_date = (
                    bench_dates[idx] if idx < len(bench_dates) else bench_dates[-1]
                )

                strat_by_date[mapped_date] = strat_by_date.get(mapped_date, 0.0) + (
                    (t.return_pct - ROUND_TRIP_COST_PCT) / 100.0 * p
                )

            cum_pl, first_p = 0.0, benchmark_data.iloc[0]["Close"]
            max_equity = config.starting_capital
            daily_returns = []
            prev_equity = config.starting_capital
            current_dd_duration = 0

            for d, row in benchmark_data.iterrows():
                date_only = d.date() if hasattr(d, "date") else d
                cum_pl += strat_by_date.get(date_only, 0.0)
                current_equity = config.starting_capital + cum_pl

                # Stats
                if current_equity > max_equity:
                    max_equity = current_equity
                    current_dd_duration = 0
                else:
                    current_dd_duration += 1

                max_dd_duration = max(max_dd_duration, current_dd_duration)

                dd = (max_equity - current_equity) / max_equity * 100
                max_dd = max(max_dd, dd)

                if prev_equity > 0:
                    daily_returns.append(current_equity / prev_equity - 1)
                prev_equity = current_equity

                equity_curve.append(
                    {
                        "date": date_only.isoformat(),
                        "equity": current_equity,
                        "benchmark_equity": (row["Close"] / first_p)
                        * config.starting_capital,
                    }
                )

            if len(daily_returns) > 1:
                std_ret = np.std(daily_returns)
                if std_ret > 0:
                    sharpe = np.mean(daily_returns) / std_ret * np.sqrt(252)

            bench_ret = (benchmark_data.iloc[-1]["Close"] / first_p - 1) * 100

    return {
        "total_trades": len(trades),
        "winning_trades": sum(win_mask),
        "win_rate": win_rate * 100,
        "avg_return_pct": sum(rets) / len(rets),
        "median_return_pct": float(np.median(rets)),
        "best_trade_pct": float(max(rets)),
        "worst_trade_pct": float(min(rets)),
        "total_return_pct": total_ret,
        "gross_return_pct": gross_ret,
        "total_cost_drag_pct": gross_ret - total_ret,
        "expectancy": (win_rate * avg_win) + ((1 - win_rate) * avg_loss),
        "profit_factor": (
            round(
                (win_weight * weighted_avg_win) / abs(loss_weight * weighted_avg_loss),
                4,
            )
            if loss_weight > 0 and weighted_avg_loss != 0
            else (99.0 if win_weight > 0 else 0.0)
        ),
        "max_drawdown_pct": max_dd,
        "max_drawdown_duration": max_dd_duration,
        "sharpe_ratio": sharpe,
        "benchmark_return_pct": bench_ret,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "avg_mae_pct": avg_mae,
        "equity_curve": equity_curve,
        "exit_breakdown": dict(Counter(t.exit_reason for t in trades)),
    }


def run_backtest(db: Session, run_id: str, config: BacktestConfig):
    logging_manager.setup_run_logging(run_id)
    strategy = TechnicalStrategy(config)
    try:
        run = db.query(BacktestRun).filter_by(run_id=run_id).first()
        if not run:
            return
        run.status = "running"
        db.commit()

        # Dynamic period to ensure warm indicators
        lookback_period = "5y"
        if config.date_from:
            years_diff = (datetime.date.today() - config.date_from).days / 365
            lookback_period = f"{int(years_diff + 2)}y"

        bench_df = _get_cached_ohlcv("^NSEI", period=lookback_period)
        breadth_map = _load_breadth_map(db, config.date_from, config.date_to)

        is_filtered = config.screen_slug and config.screen_slug != "all"
        screen_dates_map = {}
        if is_filtered:
            rows = (
                db.query(ScreenResult.symbol, ScreenResult.computed_at)
                .filter(
                    ScreenResult.screen_slug == config.screen_slug,
                    ScreenResult.computed_at >= config.date_from,
                    ScreenResult.computed_at <= config.date_to,
                )
                .all()
            )
            for sym, dt in rows:
                screen_dates_map.setdefault(sym, []).append(
                    dt.date() if hasattr(dt, "date") else dt
                )
            symbols = list(screen_dates_map.keys())
        else:
            symbols = [s.symbol for s in db.query(Stock).limit(2500).all()]

        if config.symbol_limit:
            symbols = symbols[: config.symbol_limit]

        run.symbols_total = len(symbols)
        db.commit()

        all_dfs, all_signals = {}, {}
        weekly_state_maps, monthly_state_maps = {}, {}
        symbols_processed = 0
        stocks_info = {s.symbol: s.sector for s in db.query(Stock).all()}

        for sym in symbols:
            try:
                df = _get_cached_ohlcv(sym, period=lookback_period)
                if df is None or df.empty:
                    continue
                df = _compute_all_indicators(df, strategy, symbol=sym)
                all_dfs[sym] = df
                if config.require_weekly_confirmation:
                    weekly_state_maps[sym] = build_mtf_state_map(df, "W", strategy)
                if config.require_monthly_confirmation:
                    monthly_state_maps[sym] = build_mtf_state_map(df, "M", strategy)
                if config.screen_signal_mode and is_filtered:
                    sigs = _build_screen_driven_signals(
                        sym, screen_dates_map.get(sym, []), df, config, strategy
                    )
                else:
                    sigs = score_series(
                        df, strategy=strategy, symbol=sym, config=config
                    )
                all_signals[sym] = sigs
                symbols_processed += 1
                if symbols_processed % 10 == 0:
                    run.symbols_done = symbols_processed
                    db.commit()
            except Exception as e:
                logger.error(f"Error processing {sym}: {e}")
                continue

        regime_scaling_map = {}
        if bench_df is not None:
            # We always calculate this for statistical analysis even if use_regime_position_scaling is False
            regime_scaling_map = _build_regime_map(
                bench_df, config, breadth_map=breadth_map
            )

        all_trades = simulate_portfolio(
            all_signals,
            all_dfs,
            stocks_info,
            config,
            strategy,
            weekly_state_maps=weekly_state_maps,
            monthly_state_maps=monthly_state_maps,
            screen_dates_map=screen_dates_map,
            is_screen_driven=config.screen_signal_mode,
            regime_scaling_map=regime_scaling_map,
            breadth_map=breadth_map,
        )

        metrics = compute_metrics(all_trades, bench_df, config)

        # Map metrics to DB columns
        run.total_trades = int(_clean(metrics["total_trades"]))
        run.winning_trades = int(_clean(metrics["winning_trades"]))
        run.win_rate = float(_clean(metrics["win_rate"]))
        run.avg_return_pct = float(_clean(metrics["avg_return_pct"]))
        run.median_return_pct = float(_clean(metrics["median_return_pct"]))
        run.best_trade_pct = float(_clean(metrics["best_trade_pct"]))
        run.worst_trade_pct = float(_clean(metrics["worst_trade_pct"]))
        run.total_return_pct = float(_clean(metrics["total_return_pct"]))
        run.gross_return_pct = float(_clean(metrics["gross_return_pct"]))
        run.total_cost_drag_pct = float(_clean(metrics["total_cost_drag_pct"]))
        run.expectancy = float(_clean(metrics["expectancy"]))
        run.profit_factor = float(_clean(metrics["profit_factor"]))
        run.max_drawdown_pct = float(_clean(metrics["max_drawdown_pct"]))
        run.max_drawdown_duration = int(_clean(metrics["max_drawdown_duration"]))
        run.sharpe_ratio = float(_clean(metrics["sharpe_ratio"]))
        run.benchmark_return_pct = float(_clean(metrics["benchmark_return_pct"]))
        run.avg_win_pct = float(_clean(metrics["avg_win_pct"]))
        run.avg_loss_pct = float(_clean(metrics["avg_loss_pct"]))
        run.exit_breakdown_json = json.dumps(
            metrics["exit_breakdown"], cls=NumpyEncoder
        )
        run.equity_curve_json = json.dumps(metrics["equity_curve"], cls=NumpyEncoder)
        run.regime_map_json = json.dumps(
            {str(k): v for k, v in regime_scaling_map.items()}, cls=NumpyEncoder
        )

        # Save individual trades
        db_trades = []
        for t in all_trades:
            db_trades.append(
                {
                    "run_id": run_id,
                    "symbol": t.symbol,
                    "sector": t.sector,
                    "signal_date": t.signal_date,
                    "entry_date": t.entry_date,
                    "exit_date": t.exit_date,
                    "exit_reason": t.exit_reason,
                    "signal_score": float(_clean(t.signal_score))
                    if t.signal_score is not None
                    else None,
                    "entry_price": float(_clean(t.entry_price))
                    if t.entry_price is not None
                    else None,
                    "exit_price": float(_clean(t.exit_price))
                    if t.exit_price is not None
                    else None,
                    "return_pct": float(_clean(t.return_pct))
                    if t.return_pct is not None
                    else None,
                    "rsi_at_signal": float(_clean(t.rsi_at_signal))
                    if t.rsi_at_signal is not None
                    else None,
                    "adx_at_signal": float(_clean(t.adx_at_signal))
                    if t.adx_at_signal is not None
                    else None,
                    "ema_signal": t.ema_signal,
                    "position_size": float(_clean(t.position_size_used))
                    if t.position_size_used is not None
                    else None,
                    "regime_at_signal": t.regime_at_signal,
                    "regime_at_entry": t.regime_at_entry,
                    "regime_at_exit": t.regime_at_exit,
                    "market_breadth_at_entry": float(_clean(t.market_breadth_at_entry))
                    if t.market_breadth_at_entry is not None
                    else None,
                    "consolidation_bars_at_signal": t.consolidation_bars_at_signal,
                    "pullback_depth_pct": float(_clean(t.pullback_depth_pct))
                    if t.pullback_depth_pct is not None
                    else None,
                }
            )
        if db_trades:
            db.bulk_insert_mappings(BacktestTrade, db_trades)

        run.symbols_done = len(symbols)
        run.status = "complete"
        db.commit()

    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        logger.error(traceback.format_exc())
        run.status = "failed"
        run.error_message = str(e)
        db.commit()


def _is_consolidating(
    df: pd.DataFrame,
    signal_idx: int,
    lookback: int = 15,
    max_range_pct: float = 12.0,
) -> bool:
    """
    Returns True if the stock was in a tight trading range before the signal.

    Prevents chasing EMA crosses on stocks that have already moved significantly.
    A stock that consolidates (compresses) before a breakout has a much higher
    probability of following through than one that crosses after a large move.

    lookback: number of bars before signal_idx to examine
    max_range_pct: (High - Low) / Low * 100 ceiling for the window
    """
    if signal_idx < lookback + 1:
        return False

    window = df.iloc[signal_idx - lookback : signal_idx]
    period_high = window["High"].max()
    period_low = window["Low"].min()

    if period_low <= 0 or pd.isna(period_high) or pd.isna(period_low):
        return False

    range_pct = (period_high - period_low) / period_low * 100
    return range_pct <= max_range_pct
