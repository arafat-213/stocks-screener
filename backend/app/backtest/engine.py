import bisect
import datetime
import json
import logging
import traceback
from collections import Counter
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging_manager import logging_manager
from app.db.models import (
    BacktestRun,
    BacktestTrade,
    FundamentalCache,
    ScreenResult,
    Stock,
    TechnicalSignal,
)
from app.pipeline.ohlcv_cache import OHLCVCache
from app.pipeline.scorer import calculate_technical_score
from app.pipeline.utils import resample_ohlcv
from app.screens.registry import SCREEN_REGISTRY

logger = logging.getLogger(__name__)
_ohlcv_cache = OHLCVCache()

# In-memory cache for cross-run optimization.
# Stores {symbol: DataFrame} where DataFrame contains all precomputed indicators.
# Metadata tracks the latest date in the cached DataFrame to ensure freshness.
_TA_CACHE = {}
_TA_METADATA = {}  # {symbol: latest_date}

# Cache for raw OHLCV data to avoid redundant Parquet reads during sequential runs.
_OHLCV_CACHE = {}  # {symbol: DataFrame}

ROUND_TRIP_COST_PCT = 0.25  # 0.25% per trade: brokerage + STT + slippage


@dataclass
class BacktestConfig:
    score_threshold: float = 60.0  # ← was 50.0; effective = 60*0.70 = 42 on 70pt scale
    holding_days: int = 30
    stop_loss_pct: float = 7.0
    target_pct: float = 0.0
    trailing_stop_pct: float = 0.0
    require_volume_breakout: bool = False
    use_regime_filter: bool = True
    require_weekly_confirmation: bool = False
    require_monthly_confirmation: bool = False
    atr_multiplier: float = 2.0
    risk_reward_ratio: float = 1.5
    use_atr_stops: bool = True
    min_adx: float = 0.0
    include_fundamentals: bool = False
    timeframe: str = "D"
    date_from: datetime.date = None
    date_to: datetime.date = None
    symbol_limit: int = None
    screen_slug: Optional[str] = None
    starting_capital: float = 1000000.0
    position_size: float = 10000.0
    use_volatility_sizing: bool = True
    risk_per_trade_pct: float = 1.0
    max_position_pct: float = 10.0
    max_concurrent_positions: int = 0
    max_sector_positions: int = 0
    use_atr_trailing_stop: bool = True
    atr_trailing_multiplier: float = 1.5
    atr_trailing_activation: float = 2.5
    use_partial_exits: bool = False
    use_signal_invalidation_exit: bool = False
    invalidation_threshold_pct: float = 5.0
    screen_signal_mode: bool = False  # When True, screen dates drive signals (Model B)
    screen_membership_window_days: int = (
        7  # Model A only: how far back to look for screen membership
    )
    screen_reentry_gap_days: int = (
        60  # Model B only: min days between signals for same symbol
    )
    screen_driven_rsi_max: float = (
        75.0  # Model B only: max RSI allowed at qualification date
    )

    # ── New fields ────────────────────────────────────────────────────────────
    min_signal_tier: int = 2  # was 1; Run 5 validated Tier 2 quality
    require_consolidation: bool = True  # only enter after a consolidation period
    consolidation_bars: int = 15  # look-back window for consolidation check
    consolidation_max_range_pct: float = 12.0  # max High-Low range to qualify
    use_pullback_entry: bool = True  # wait for pullback to EMA20 after cross
    pullback_max_wait_bars: int = 8  # was 5; allow setup to develop
    pullback_tolerance_pct: float = 3.0  # was 2.0; NSE mid/smallcap needs room

    @property
    def effective_score_threshold(self) -> float:
        """
        Normalises score_threshold to the actual score scale.

        When include_fundamentals=False, calculate_technical_score returns a
        maximum of 70 (not 100). A raw threshold of 60 on a 70-pt scale is an
        85.7% bar — far too tight. We treat score_threshold as a 0-100 intention
        and scale it down to match the active score ceiling.
        """
        if not self.include_fundamentals:
            return self.score_threshold * 0.70
        return self.score_threshold


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
    position_size_used: float = (
        0.0  # actual rupee position, may differ from config.position_size
    )


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
            df.index = df.index.tz_localize(None)

        _OHLCV_CACHE[symbol] = df
        return df

    return None


def build_mtf_state_map(df: pd.DataFrame, timeframe: str) -> dict:
    """
    Resamples daily data to timeframe ('W' or 'M') and scores each bar.
    Returns {date: is_bullish} mapping.
    Ensures no look-ahead bias by scoring each bar using only previous data.
    """
    if df is None or df.empty:
        return {}

    freq = "W" if timeframe == "W" else "ME"
    resampled = resample_ohlcv(df, freq=freq, drop_incomplete=True)
    if resampled.empty:
        return {}

    state_map = {}
    # Technical scoring needs some history (60 bars for W, 24 for M)
    min_bars = 24 if timeframe == "M" else 60

    for i in range(len(resampled)):
        # Important: only use data up to bar i to avoid look-ahead bias
        bar_slice = resampled.iloc[: i + 1]
        if len(bar_slice) < min_bars:
            continue

        try:
            ta_data = calculate_technical_score(bar_slice, timeframe=timeframe)
        except Exception as e:
            logger.error(f"Error scoring MTF bar {i} for {timeframe}: {e}")
            continue

        bar_date = resampled.index[i]
        if hasattr(bar_date, "date"):
            bar_date = bar_date.date()

        state_map[bar_date] = bool(ta_data.get("is_bullish", False))

    return state_map


def _compute_all_indicators(df: pd.DataFrame, symbol: str = None) -> pd.DataFrame:
    """
    Computes all pandas-ta indicators on the full DataFrame in a single pass.
    Called once per symbol instead of once per bar.
    Returns a new DataFrame with all indicator columns appended.
    Utilizes _TA_CACHE if symbol is provided and latest date matches.
    """
    if symbol and symbol in _TA_CACHE:
        latest_date = df.index[-1]
        if _TA_METADATA.get(symbol) == latest_date:
            return _TA_CACHE[symbol]

    df = df.copy()
    # Import pandas_ta_classic locally if not global to ensure extensions are ready
    df.ta.ema(length=5, append=True)
    df.ta.ema(length=13, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=26, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.adx(length=14, append=True)
    if "Volume" in df.columns:
        df["VOL_SMA_20"] = df["Volume"].rolling(window=20).mean()
    else:
        df["VOL_SMA_20"] = pd.Series(dtype="float64")
    # EMA slope: (EMA_20[i] - EMA_20[i-5]) / 5
    ema20_col = "EMA_20"
    if ema20_col in df.columns:
        df["EMA_SLOPE_20"] = (df[ema20_col] - df[ema20_col].shift(5)) / 5.0

    if symbol:
        _TA_CACHE[symbol] = df
        _TA_METADATA[symbol] = df.index[-1]

    return df


def _score_bar_from_precomputed(df_ind: pd.DataFrame, i: int) -> dict:
    """
    Scores bar at index i using pre-computed indicator columns in df_ind.
    Mirrors the Daily timeframe scoring in calculate_technical_score without
    re-running pandas-ta. df_ind must be the output of _compute_all_indicators.
    """
    latest = df_ind.iloc[i]
    prev = df_ind.iloc[i - 1] if i > 0 else latest

    ema5 = latest.get("EMA_5")
    ema13 = latest.get("EMA_13")
    ema20 = latest.get("EMA_20")
    ema26 = latest.get("EMA_26")
    ema200 = latest.get("EMA_200")
    price = latest.get("Close")
    macd_line = latest.get("MACD_12_26_9")
    signal_line = latest.get("MACDs_12_26_9")
    rsi = latest.get("RSI_14")
    prev_rsi = prev.get("RSI_14")
    atr = latest.get("ATRr_14")
    adx = latest.get("ADX_14")
    volume = latest.get("Volume")
    sma20_vol = latest.get("VOL_SMA_20")
    ema_slope_20 = latest.get("EMA_SLOPE_20")

    prev_ema5 = prev.get("EMA_5")
    prev_ema13 = prev.get("EMA_13")
    prev_macd = prev.get("MACD_12_26_9")
    prev_sig = prev.get("MACDs_12_26_9")

    score = 0.0
    ema_signal = "neutral"
    volume_signal = "neutral"
    rsi_signal = "neutral"
    is_bullish = False

    is_green = (
        pd.notna(price) and pd.notna(latest.get("Open")) and price > latest.get("Open")
    )

    # Volume breakout flag (2× threshold, matches scorer.py)
    volume_breakout = (
        pd.notna(volume)
        and pd.notna(sma20_vol)
        and volume > 2.0 * sma20_vol
        and is_green
    )

    # Momentum (lookback from full df_ind)
    momentum_1m = (
        float((price / df_ind["Close"].iloc[i - 21] - 1) * 100) if i >= 21 else None
    )
    momentum_3m = (
        float((price / df_ind["Close"].iloc[i - 63] - 1) * 100) if i >= 63 else None
    )
    momentum_6m = (
        float((price / df_ind["Close"].iloc[i - 126] - 1) * 100) if i >= 126 else None
    )
    momentum_12m = (
        float((price / df_ind["Close"].iloc[i - 252] - 1) * 100) if i >= 252 else None
    )

    # 1. EMA Alignment (20 pts)
    fresh_ema_cross = (
        pd.notna(ema5)
        and pd.notna(ema13)
        and pd.notna(prev_ema5)
        and pd.notna(prev_ema13)
        and ema5 > ema13
        and prev_ema5 <= prev_ema13
    )
    pullback_to_ema20 = (
        pd.notna(ema20)
        and pd.notna(price)
        and pd.notna(ema5)
        and pd.notna(ema13)
        and pd.notna(ema26)
        and ema5 > ema13 > ema26
        and abs(price - ema20) / ema20 < 0.02
    )
    if fresh_ema_cross:
        score += 20
        ema_signal = "bullish_cross"
    elif pullback_to_ema20:
        score += 15
        ema_signal = "bullish_pullback"
    elif (
        pd.notna(ema5)
        and pd.notna(ema13)
        and pd.notna(ema26)
        and ema5 > ema13 > ema26
        and price > ema26
    ):
        score += 8
        ema_signal = "bullish"
    elif (
        pd.notna(ema5) and pd.notna(ema13) and pd.notna(ema26) and ema5 < ema13 < ema26
    ):
        ema_signal = "bearish"

    # 2. MACD (15 pts — decoupled from EMA cross)
    if pd.notna(macd_line) and pd.notna(signal_line):
        fresh_macd_cross = (
            pd.notna(prev_macd)
            and pd.notna(prev_sig)
            and macd_line > signal_line
            and prev_macd <= prev_sig
        )
        if fresh_macd_cross and fresh_ema_cross:
            score += 8
        elif fresh_macd_cross:
            score += 15
        elif macd_line > signal_line and macd_line > 0:
            score += 10
        elif macd_line > signal_line and macd_line < 0:
            score += 5

    # 3. RSI (15 pts)
    if pd.notna(rsi) and pd.notna(prev_rsi):
        recent_rsi = df_ind["RSI_14"].iloc[max(0, i - 4) : i + 1]
        was_oversold = any(recent_rsi < 30)
        recovering = was_oversold and rsi > 30 and pd.notna(ema20) and price > ema20
        crossing_50 = prev_rsi <= 50 and rsi > 50
        if recovering and fresh_ema_cross:
            score += 15
            rsi_signal = "bullish_recovery_confirmed"
        elif recovering:
            score += 15
            rsi_signal = "bullish_recovery"
        elif crossing_50:
            score += 10
            rsi_signal = "bullish_crossing"
        elif 50 < rsi <= 65:
            score += 5
            rsi_signal = "bullish_strong"
        elif 65 < rsi <= 68:
            score += 0  # No bonus for extended RSI
            rsi_signal = "bullish_extended"
        elif rsi > 68:
            pass

    # 4. Volume (15 pts)
    if pd.notna(volume) and pd.notna(sma20_vol):
        if volume > 2.0 * sma20_vol and is_green:
            score += 15
            volume_signal = "bullish"

    # 5. Trend Quality: ADX + 3-Month Momentum (max 5 pts)
    trend_pts = 0
    if pd.notna(adx):
        if adx >= 35:
            trend_pts += 3
        elif adx >= 25:
            trend_pts += 2
        elif adx >= 20:
            trend_pts += 1
    if momentum_3m is not None:
        if momentum_3m > 15:
            trend_pts += 2
        elif momentum_3m > 5:
            trend_pts += 1
    score += min(trend_pts, 5)

    # is_bullish definition (same as scorer.py Daily)
    is_bullish = bool(
        (
            fresh_ema_cross
            or pullback_to_ema20
            or (
                pd.notna(ema5)
                and pd.notna(ema13)
                and pd.notna(ema26)
                and ema5 > ema13 > ema26
            )
        )
        and pd.notna(macd_line)
        and pd.notna(signal_line)
        and macd_line > signal_line
        and pd.notna(rsi)
        and rsi > 45
    )

    above_200ema = bool(price > ema200) if pd.notna(ema200) else None

    return {
        "score": float(score),
        "rsi": float(rsi) if pd.notna(rsi) else 0.0,
        "macd": float(macd_line) if pd.notna(macd_line) else 0.0,
        "ema_signal": ema_signal,
        "volume_signal": volume_signal,
        "rsi_signal": rsi_signal,
        "is_bullish": is_bullish,
        "volume_breakout": bool(volume_breakout),
        "atr": float(atr) if pd.notna(atr) else None,
        "adx": float(adx) if pd.notna(adx) else None,
        "above_200ema": above_200ema,
        "ema_slope_20": float(ema_slope_20) if pd.notna(ema_slope_20) else None,
        "momentum_1m": momentum_1m,
        "momentum_3m": momentum_3m,
        "momentum_6m": momentum_6m,
        "momentum_12m": momentum_12m,
        "ema20": float(ema20) if pd.notna(ema20) else None,
    }


def _build_screen_driven_signals(
    symbol: str,
    screen_dates: list[datetime.date],
    df: pd.DataFrame,
    config: BacktestConfig,
) -> list[dict]:
    """
    Model B signal builder.
    Each date the stock appeared in the named screen becomes a candidate signal.
    Score/tier/consolidation/RSI gates are bypassed — the screen already made the
    quality decision on that date.
    Regime filter, pullback entry, sizing, and exit logic still apply downstream.
    """
    if df is None or df.empty or not screen_dates:
        return []

    # Ensure df index is naive
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)

    df_ind = _compute_all_indicators(df, symbol=symbol)
    # Map dates to indices for O(1) lookup
    date_to_idx = {
        d.date() if hasattr(d, "date") else d: i for i, d in enumerate(df.index)
    }

    signals = []
    last_signal_date = None
    reentry_gap = getattr(config, "screen_reentry_gap_days", 60)

    # Ensure screen_dates are sorted
    sorted_screen_dates = sorted(screen_dates)

    for screen_date in sorted_screen_dates:
        # Check re-entry gap
        if last_signal_date is not None:
            if (screen_date - last_signal_date).days < reentry_gap:
                continue

        idx = date_to_idx.get(screen_date)
        if (
            idx is None or idx < 260
        ):  # need enough history for indicators (200 EMA + 12m momentum)
            continue

        if config.date_from and screen_date < config.date_from:
            continue
        if config.date_to and screen_date > config.date_to:
            continue

        try:
            bar = _score_bar_from_precomputed(df_ind, idx)
        except Exception as e:
            logger.error(f"Error scoring screen date {screen_date} for {symbol}: {e}")
            continue

        # Hard structural gates — everything else is the screen's responsibility
        # We still respect the 200 EMA as a absolute minimum for long positions
        if bar.get("above_200ema") is not True:
            continue

        # We also skip stocks in structural 12m downtrends (negative momentum)
        if bar.get("momentum_12m") is not None and bar["momentum_12m"] < 0:
            continue

        # RSI ceiling — even in Model B, don't enter extremely overbought stocks.
        # Momentum stocks with RSI > 75 are statistically at elevated reversal risk.
        rsi_max = getattr(config, "screen_driven_rsi_max", 75.0)
        rsi = bar.get("rsi") or 0.0
        if rsi > rsi_max:
            continue

        signals.append(
            {
                "date": df.index[idx],
                "score": 100.0,  # screen qualification = full score
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
                "momentum_12m": bar.get("momentum_12m"),
                "momentum_3m": bar.get("momentum_3m"),
                "ema20": bar.get("ema20"),
                "is_consolidating": True,  # bypass — screen validated quality
            }
        )
        last_signal_date = screen_date

    return signals


def score_series(
    df: pd.DataFrame, symbol: str = None, fund_cache=None, config: BacktestConfig = None
):
    """
    Computes per-bar scores for all bars in df using a single indicator pass (O(n)).

    Previously O(n²) because calculate_technical_score was called on a growing
    slice at every bar, recomputing all indicators from scratch each time.
    Now: compute indicators once, score each bar from the precomputed columns.
    """
    if df is None or len(df) < 210:
        return []

    fund_score = 0.0
    if config and config.include_fundamentals and fund_cache:
        from app.pipeline.scorer import calculate_fundamental_score

        fund_score = calculate_fundamental_score(None, fund_cache=fund_cache)

    # Single indicator computation pass — O(n)
    df_ind = _compute_all_indicators(df, symbol=symbol)

    lookback = config.consolidation_bars if config else 15
    max_range = config.consolidation_max_range_pct if config else 12.0
    rolling_high = df_ind["High"].rolling(lookback).max().shift(1)
    rolling_low = df_ind["Low"].rolling(lookback).min().shift(1)
    range_pct = (rolling_high - rolling_low) / rolling_low * 100
    is_consolidating_series = range_pct <= max_range

    results = []
    MIN_BARS = 260

    for i in range(MIN_BARS, len(df_ind)):
        try:
            bar_data = _score_bar_from_precomputed(df_ind, i)
        except Exception as e:
            logger.error("score_series bar %d error: %s", i, e)
            continue

        total_score = bar_data["score"] + fund_score

        if bar_data.get("above_200ema") is not True:
            total_score = 0.0

        if bar_data.get("rsi", 0) > 80:
            total_score = 0.0

        # Consolidation check uses pre-computed series
        is_consolidating = bool(is_consolidating_series.iloc[i])

        results.append(
            {
                "date": df_ind.index[i],
                "score": float(total_score),
                "is_bullish": bar_data["is_bullish"],
                "rsi": bar_data["rsi"],
                "adx": bar_data["adx"],
                "ema_signal": bar_data["ema_signal"],
                "volume_signal": bar_data["volume_signal"],
                "rsi_signal": bar_data["rsi_signal"],
                "close": float(df_ind["Close"].iloc[i]),
                "open": float(df_ind["Open"].iloc[i]),
                "volume_breakout": bar_data["volume_breakout"],
                "atr": bar_data["atr"],
                "above_200ema": bar_data["above_200ema"],
                "momentum_12m": bar_data.get("momentum_12m"),
                "momentum_3m": bar_data.get("momentum_3m"),
                "ema20": bar_data.get("ema20"),
                "is_consolidating": is_consolidating,
            }
        )

    return results


def _lookup_mtf_state(state_map: dict, signal_date: datetime.date) -> bool:
    """
    Looks up the most recent state in state_map for a date <= signal_date.
    Uses binary search for efficiency.
    Returns False if no bar predates the signal (fail-closed).
    """
    if not state_map:
        return False

    sorted_dates = sorted(state_map.keys())
    idx = bisect.bisect_right(sorted_dates, signal_date)

    if idx == 0:
        return False

    match_date = sorted_dates[idx - 1]
    return state_map[match_date]


def _compute_position_size(
    config: BacktestConfig,
    entry_price: float,
    atr: float | None,
) -> float:
    """
    Returns the rupee position size for a trade.

    Flat mode (use_volatility_sizing=False):
        Always returns config.position_size.

    Volatility mode (use_volatility_sizing=True):
        Sizes position so that a stop-loss hit (atr_multiplier × ATR away)
        loses exactly risk_per_trade_pct% of starting_capital.
        Capped at max_position_pct% of starting_capital.
        Falls back to flat size when ATR is None or zero.
    """
    if not config.use_volatility_sizing or atr is None or atr <= 0 or entry_price <= 0:
        return config.position_size

    risk_amount = config.starting_capital * (config.risk_per_trade_pct / 100.0)
    stop_distance_per_share = config.atr_multiplier * atr
    shares = risk_amount / stop_distance_per_share
    position_value = shares * entry_price
    max_position = config.starting_capital * (config.max_position_pct / 100.0)
    return min(position_value, max_position)


def _compute_signal_tier(signal: dict) -> int:
    """
    Computes the signal quality tier (1-4).
    Tier 1/2 are considered high-quality and allowed to enter trades.
    Tier 3/4 are filtered out.
    """
    ema = signal.get("ema_signal")
    vol = signal.get("volume_breakout", False)
    adx = signal.get("adx") or 0.0
    rsi = signal.get("rsi") or 0.0

    is_core_ema = ema in ["bullish_cross", "bullish_pullback"]

    if not is_core_ema:
        return 4

    if rsi > 65.0:
        return 3

    # Tier 1 & 2 require 40 <= RSI <= 65
    if rsi < 40.0:
        return 3

    if vol and adx >= 25.0:
        return 1

    if vol or adx >= 25.0:
        return 2

    return 3  # missing both volume breakout and strong ADX


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


def simulate_trades(
    symbol: str,
    sector: str,
    df: pd.DataFrame,
    scored_dates: list[dict],
    config: BacktestConfig,
    regime_dict: dict = None,
    weekly_state_map: dict = None,
    monthly_state_map: dict = None,
    screen_dates: list[datetime.date] | None = None,
    is_screen_driven: bool = False,
):
    """
    Simulates trades based on scored signals.
    Entry: Next day's Open.
    Exit: SL, Target, or Holding Period.

    screen_dates: if provided, a signal is only acted on if the symbol was in the
    screen within config.screen_membership_window_days before the signal date.

    is_screen_driven: if True (Model B), bypasses quality/tier gates since the
    screen already validated the entry quality on that exact date.
    """
    trades = []
    last_exit_idx = -1

    # Pre-sort screen_dates for efficient binary search
    _sorted_screen_dates = sorted(screen_dates) if screen_dates else None

    # Pre-map dates to indices for faster lookup
    date_to_idx = {date: i for i, date in enumerate(df.index)}

    for signal in scored_dates:
        signal_date = signal["date"]
        # Convert signal_date to datetime.date if it's a Timestamp or string
        compare_date = (
            signal_date.date() if hasattr(signal_date, "date") else signal_date
        )
        if isinstance(compare_date, str):
            compare_date = datetime.datetime.strptime(compare_date, "%Y-%m-%d").date()

        # ── Screen membership gate (Model A only) ─────────────────────────────
        # If in Model A (is_screen_driven=False) but a screen is provided,
        # we only enter if the symbol was in the named screen recently.
        if _sorted_screen_dates is not None and not is_screen_driven:
            window_days = getattr(config, "screen_membership_window_days", 7)
            window_start = compare_date - datetime.timedelta(days=window_days)
            # bisect to find dates in [window_start, compare_date]
            lo = bisect.bisect_left(_sorted_screen_dates, window_start)
            hi = bisect.bisect_right(_sorted_screen_dates, compare_date)
            if lo >= hi:
                continue  # symbol not in screen near this signal date — skip

        # Date Filtering
        if config.date_from and compare_date < config.date_from:
            continue
        if config.date_to and compare_date > config.date_to:
            continue

        signal_idx = date_to_idx.get(signal_date)

        if signal_idx is None or signal_idx <= last_exit_idx:
            continue

        # 200 EMA null-safety gate (belt-and-suspenders; also enforced in score_series)
        if signal.get("above_200ema") is not True:
            continue

        # Relative strength gate: require positive 12m momentum.
        # EMA crosses on stocks that are down year-over-year are almost always
        # failed bounces in a structural downtrend, not new uptrends.
        momentum_12m = signal.get("momentum_12m")
        if momentum_12m is not None and momentum_12m < 0:
            continue

        # ADX trend-strength gate (min_adx=0 disables)
        if config.min_adx > 0:
            adx_val = signal.get("adx")
            if adx_val is None or adx_val < config.min_adx:
                continue

        # Weekly confirmation gate
        if config.require_weekly_confirmation and weekly_state_map is not None:
            if not _lookup_mtf_state(weekly_state_map, compare_date):
                continue

        # Monthly confirmation gate
        if config.require_monthly_confirmation and monthly_state_map is not None:
            if not _lookup_mtf_state(monthly_state_map, compare_date):
                continue

        # Signal Quality Tier & Score Gate
        # Bypassed in Model B — screen already validated entry quality.
        if not is_screen_driven:
            signal_tier = _compute_signal_tier(signal)
            if signal_tier > config.min_signal_tier:
                continue

            rsi_at_signal = signal.get("rsi", 0.0) or 0.0
            if rsi_at_signal > 65.0:
                continue

            if signal["score"] < config.effective_score_threshold:
                continue

            # Volume Breakout Filter
            if config.require_volume_breakout:
                if not signal.get("volume_breakout", False):
                    continue

            # ── Consolidation gate ────────────────────────────────────────────
            if config.require_consolidation and not signal.get(
                "is_consolidating", False
            ):
                continue

        # ── Entry Logic (Pullback vs Immediate) ───────────────────────────────
        signal_ema20 = signal.get("ema20")
        ema_signal_type = signal.get("ema_signal", "")

        entry_idx = None
        entry_price = None
        entry_date = None

        use_pullback = (
            config.use_pullback_entry
            and ema_signal_type == "bullish_cross"
            and signal_ema20 is not None
            and signal_ema20 > 0
        )

        entry_path = "immediate"  # Track which path was used for stop logic

        if use_pullback:
            # Wait up to pullback_max_wait_bars for price to touch EMA20
            tol = config.pullback_tolerance_pct / 100.0

            # Track whether price held above EMA20 throughout the wait
            all_bars_above_ema20 = True
            closest_approach_pct = float("inf")  # How close price got to EMA20 (%)

            for wait_k in range(
                signal_idx + 1,
                min(signal_idx + config.pullback_max_wait_bars + 1, len(df)),
            ):
                wait_date = df.index[wait_k]
                wait_compare = (
                    wait_date.date() if hasattr(wait_date, "date") else wait_date
                )

                # Abort if regime turns bearish during the wait
                if config.use_regime_filter and regime_dict is not None:
                    if not regime_dict.get(wait_compare, False):
                        all_bars_above_ema20 = False
                        break

                day_low = df.iloc[wait_k]["Low"]
                day_close = df.iloc[wait_k]["Close"]
                day_open = df.iloc[wait_k]["Open"]

                # Invalidation: closed meaningfully below EMA20
                if day_close < signal_ema20 * (1 - 0.025):
                    all_bars_above_ema20 = False
                    break

                # Track closest approach to EMA20 from above
                approach_pct = (day_low - signal_ema20) / signal_ema20 * 100
                closest_approach_pct = min(closest_approach_pct, approach_pct)

                # Path A: Price pulled back to within tol% above EMA20 AND held
                touched_ema = day_low <= signal_ema20 * (1 + tol)
                # TIGHTENED: close must be AT or within 0.5% above EMA20 (was 1.5% below)
                # — confirms support held before we commit capital
                held_above = day_close >= signal_ema20 * 0.995

                if touched_ema and held_above:
                    # Path A: price bounced from EMA20 and closed above it.
                    # Enter at this bar's close — the close confirms support held.
                    # Using next-bar open risks entering after a gap-up with the same
                    # structural stop, making the effective risk distance tighter.
                    entry_path = "pullback_a"
                    entry_idx = wait_k
                    entry_date = wait_date
                    entry_price = float(df.iloc[wait_k]["Close"])
                    break

            # Path B: Momentum continuation — price never pulled back but
            # consolidated above EMA20 throughout the wait window.
            if (
                entry_idx is None
                and all_bars_above_ema20
                and closest_approach_pct != float("inf")
            ):
                if closest_approach_pct <= 8.0:
                    last_wait_k = min(
                        signal_idx + config.pullback_max_wait_bars, len(df) - 1
                    )
                    entry_path = "momentum_b"
                    entry_idx = last_wait_k
                    entry_date = df.index[last_wait_k]
                    entry_price = float(df.iloc[last_wait_k]["Open"])

            if entry_idx is None:
                continue

        else:
            entry_idx = signal_idx + 1
            if entry_idx >= len(df):
                break

            entry_date = df.index[entry_idx]
            entry_compare_date = (
                entry_date.date() if hasattr(entry_date, "date") else entry_date
            )

            if config.use_regime_filter and regime_dict is not None:
                if not regime_dict.get(entry_compare_date, False):
                    continue

            entry_price = float(df.iloc[entry_idx]["Open"])

        # Model B momentum guard: verify stock is still trending at entry.
        # A momentum stock that has lost 1-month momentum since screen qualification
        # is a failed setup — the thesis has already broken down before entry.
        if is_screen_driven and entry_idx >= 21:
            entry_momentum_1m = (
                df.iloc[entry_idx]["Close"] / df.iloc[entry_idx - 21]["Close"] - 1
            ) * 100
            if entry_momentum_1m < 0:
                continue

        pos_size = _compute_position_size(
            config,
            entry_price=entry_price,
            atr=signal.get("atr"),
        )

        # ── Stop and Target ────────────────────────────────────────────────────
        # The ATR at signal time is measured DURING consolidation — it's compressed
        # by design. Using it for stops creates levels that normal post-breakout
        # noise blows through. The consolidation period LOW is the correct structural
        # stop: if price returns below where it consolidated, the breakout thesis
        # is invalid. This is path-agnostic (applies to both pullback and momentum).
        MIN_STOP_PCT = 0.05  # 5% minimum: hard floor against compressed ATR
        atr_val = signal.get("atr")

        if is_screen_driven:
            # Model B: momentum/trending stocks are NOT consolidating.
            # The structural stop (15-bar low) is meaningless — it just captures
            # a slice of the uptrend and creates absurdly wide stops (20-35%).
            # Use pure ATR-based stop. If ATR is unavailable, fall back to
            # config.stop_loss_pct which the user explicitly set.
            if atr_val and atr_val > 0:
                base_stop = entry_price - config.atr_multiplier * atr_val
            elif config.stop_loss_pct > 0:
                base_stop = entry_price * (1 - config.stop_loss_pct / 100)
            else:
                base_stop = entry_price * 0.93
        else:
            # Model A: stock entered after consolidation — structural stop is valid.
            consol_start = max(0, signal_idx - config.consolidation_bars)
            consol_window = df.iloc[consol_start:signal_idx]
            consol_low = (
                float(consol_window["Low"].min()) if len(consol_window) > 0 else None
            )

            # 2% buffer below consolidation low — allows for wick through without
            # invalidation, but a close below means the structure has broken
            structural_stop = (
                (consol_low * 0.98) if (consol_low and consol_low > 0) else None
            )

            # ATR stop as secondary reference
            atr_stop = (
                (entry_price - config.atr_multiplier * atr_val) if atr_val else None
            )

            # Use the WIDER stop (lower price) — gives the trade room to breathe
            if structural_stop and atr_stop:
                base_stop = min(structural_stop, atr_stop)
            elif structural_stop:
                base_stop = structural_stop
            elif atr_stop:
                base_stop = atr_stop
            else:
                base_stop = (
                    entry_price * (1 - config.stop_loss_pct / 100)
                    if config.stop_loss_pct > 0
                    else entry_price * 0.93
                )

        # Enforce 5% minimum — if consolidation was very tight, base_stop
        # can be only 2-3% away, which is noise on NSE stocks
        min_stop_price = entry_price * (1 - MIN_STOP_PCT)
        stop_loss_price = min(
            base_stop, min_stop_price
        )  # min = lower price = wider stop

        actual_risk = max(entry_price - stop_loss_price, entry_price * 0.02)
        if config.target_pct > 0:
            target_price = entry_price * (1 + config.target_pct / 100)
        else:
            target_price = entry_price + config.risk_reward_ratio * actual_risk

        # Partial exits: recalculate around actual_risk
        if config.use_partial_exits:
            t1_price = entry_price + 1.0 * actual_risk
            t2_price = target_price
        else:
            t1_price = None
            t2_price = None

        # Exit conditions
        exit_price = None
        exit_date = None
        exit_reason = "holding_period"

        t1_hit = False
        t1_exit_trade = None

        # Walk forward up to config.holding_days
        final_idx = min(entry_idx + config.holding_days - 1, len(df) - 1)

        highest_price_since_entry = entry_price

        consecutive_bearish_bars = 0
        invalidation_floor = entry_price * (1 - config.invalidation_threshold_pct / 100)

        for k in range(entry_idx, final_idx + 1):
            day_low = df.iloc[k]["Low"]
            day_high = df.iloc[k]["High"]
            day_open = df.iloc[k]["Open"]

            highest_price_since_entry = max(highest_price_since_entry, day_high)

            # Signal Invalidation Exit
            if config.use_signal_invalidation_exit:
                day_close = df.iloc[k]["Close"]
                if day_close < invalidation_floor:
                    consecutive_bearish_bars += 1
                else:
                    consecutive_bearish_bars = 0

                if consecutive_bearish_bars >= 2:
                    next_k = k + 1
                    if next_k < len(df):
                        exit_price = df.iloc[next_k]["Open"]
                        exit_date = df.index[next_k]
                    else:
                        exit_price = df.iloc[k]["Close"]
                        exit_date = df.index[k]
                    exit_reason = "signal_invalidated"
                    last_exit_idx = next_k if next_k < len(df) else k
                    break

            # Check Stop Loss first (conservative)
            if day_low <= stop_loss_price:
                exit_price = stop_loss_price
                exit_date = df.index[k]
                exit_reason = "stop_loss"
                last_exit_idx = k
                break

            # Partial exit T1
            if not t1_hit and t1_price is not None and day_high >= t1_price:
                t1_hit = True
                t1_exit_trade = TradeResult(
                    symbol=symbol,
                    sector=sector,
                    signal_date=signal_date.date()
                    if hasattr(signal_date, "date")
                    else signal_date,
                    entry_date=entry_date.date()
                    if hasattr(entry_date, "date")
                    else entry_date,
                    exit_date=df.index[k].date()
                    if hasattr(df.index[k], "date")
                    else df.index[k],
                    exit_reason="target_partial",
                    signal_score=signal["score"],
                    entry_price=float(entry_price),
                    exit_price=float(t1_price),
                    return_pct=float(((t1_price - entry_price) / entry_price) * 100),
                    rsi_at_signal=signal["rsi"],
                    adx_at_signal=signal["adx"],
                    ema_signal=signal["ema_signal"],
                    position_size_used=pos_size * 0.5,
                )
                # Move stop to breakeven for the remainder
                stop_loss_price = entry_price
                # Update target to T2
                target_price = t2_price

            # Check Profit Target — evaluated before trailing stops.
            # A bar that touches the target high and the trailing-stop low on the
            # same candle should record a target exit: price reached the objective
            # first, then pulled back. Checking target before trailing stops prevents
            # the trailing stop from stealing a target hit.
            if day_high >= target_price:
                exit_price = target_price
                exit_date = df.index[k]
                exit_reason = "target"
                last_exit_idx = k
                break

            # Check Trailing Stop (% based)
            if config.trailing_stop_pct > 0:
                trailing_stop_price = highest_price_since_entry * (
                    1 - config.trailing_stop_pct / 100
                )
                if day_low <= trailing_stop_price:
                    exit_price = min(trailing_stop_price, day_open)
                    exit_date = df.index[k]
                    exit_reason = "trailing_stop"
                    last_exit_idx = k
                    break

            # ATR Trailing Stop
            if config.use_atr_trailing_stop and signal.get("atr"):
                atr_val = signal["atr"]
                activation_threshold = entry_price + (
                    config.atr_trailing_activation * atr_val
                )
                if highest_price_since_entry >= activation_threshold:
                    # Floor at entry_price: trailing stop must never fire below breakeven.
                    # Without this floor, if activation=1.0 and multiplier=1.5,
                    # the stop = peak - 1.5 ATR = entry + 1.0 ATR - 1.5 ATR = entry - 0.5 ATR
                    # which causes losses on trailing stop exits.
                    atr_trail_stop = max(
                        entry_price,
                        highest_price_since_entry
                        - (config.atr_trailing_multiplier * atr_val),
                    )
                    if day_low <= atr_trail_stop:
                        exit_price = max(atr_trail_stop, day_open)
                        exit_date = df.index[k]
                        exit_reason = "atr_trailing_stop"
                        last_exit_idx = k
                        break

        if exit_price is None:
            # Exit on last day's Close
            exit_idx = final_idx
            exit_price = df.iloc[exit_idx]["Close"]
            exit_date = df.index[exit_idx]
            exit_reason = "holding_period"
            last_exit_idx = exit_idx

        if t1_exit_trade is not None:
            trades.append(t1_exit_trade)
            # The main TradeResult for the remainder uses half position size
            pos_size = pos_size * 0.5

        return_pct = ((exit_price - entry_price) / entry_price) * 100

        trades.append(
            TradeResult(
                symbol=symbol,
                sector=sector,
                signal_date=signal_date.date()
                if hasattr(signal_date, "date")
                else signal_date,
                entry_date=entry_date.date()
                if hasattr(entry_date, "date")
                else entry_date,
                exit_date=exit_date.date() if hasattr(exit_date, "date") else exit_date,
                exit_reason=exit_reason,
                signal_score=signal["score"],
                entry_price=float(entry_price),
                exit_price=float(exit_price),
                return_pct=float(return_pct),
                rsi_at_signal=signal["rsi"],
                adx_at_signal=signal["adx"],
                ema_signal=signal["ema_signal"],
                position_size_used=pos_size,
            )
        )

    return trades


def simulate_portfolio(
    all_signals: dict[str, list[dict]],
    all_dfs: dict[str, pd.DataFrame],
    stocks_info: dict[str, str],
    config: BacktestConfig,
    regime_dict: dict = None,
    weekly_state_maps: dict | None = None,
    monthly_state_maps: dict | None = None,
    screen_dates_map: dict[str, list[datetime.date]] | None = None,
    is_screen_driven: bool = False,
) -> list[TradeResult]:
    """
    Portfolio-level chronological simulation.

    Aggregates signals from all symbols, sorts them by date, and processes
    them in order — enforcing max_concurrent_positions and max_sector_positions
    before allowing each entry.

    Falls back to per-symbol simulate_trades for each accepted signal to
    reuse the exact same exit logic (SL, target, holding period).
    """
    # Build flat chronological timeline of (date, symbol, signal)
    timeline: list[tuple] = []
    for symbol, signals in all_signals.items():
        for sig in signals:
            sig_date = sig["date"]
            compare = sig_date.date() if hasattr(sig_date, "date") else sig_date
            timeline.append((compare, symbol, sig))

    timeline.sort(key=lambda x: x[0])

    all_trades: list[TradeResult] = []
    # symbol -> exit_date (datetime.date)
    open_positions: dict[str, datetime.date] = {}

    for compare_date, symbol, signal in timeline:
        # Skip if already holding this exact symbol
        if symbol in open_positions and open_positions[symbol] > compare_date:
            continue

        sector = stocks_info.get(symbol, "Unknown")

        # Enforce max_concurrent_positions
        if config.max_concurrent_positions > 0:
            active_count = sum(
                1 for exit_d in open_positions.values() if exit_d > compare_date
            )
            if active_count >= config.max_concurrent_positions:
                continue

        # Enforce max_sector_positions
        if config.max_sector_positions > 0:
            sector_active = sum(
                1
                for sym, exit_d in open_positions.items()
                if stocks_info.get(sym) == sector and exit_d > compare_date
            )
            if sector_active >= config.max_sector_positions:
                continue

        df = all_dfs.get(symbol)
        if df is None:
            continue

        trades = simulate_trades(
            symbol,
            sector,
            df,
            [signal],
            config,
            regime_dict=regime_dict,
            weekly_state_map=(weekly_state_maps or {}).get(symbol),
            monthly_state_map=(monthly_state_maps or {}).get(symbol),
            screen_dates=(
                screen_dates_map.get(symbol, [])
                if screen_dates_map is not None
                else None
            ),
            is_screen_driven=is_screen_driven,
        )

        if trades:
            trade = trades[0]
            open_positions[symbol] = trade.exit_date
            all_trades.append(trade)

    return all_trades


def compute_metrics(
    trades: list[TradeResult], benchmark_data: pd.DataFrame, config: BacktestConfig
):
    """
    Calculates aggregate metrics and equity curve.
    Uses starting_capital and position_size from config.
    """
    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "median_return_pct": 0.0,
            "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "total_return_pct": 0.0,
            "benchmark_return_pct": 0.0,
            "equity_curve": [],
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "gross_return_pct": 0.0,
            "total_cost_drag_pct": 0.0,
            "exit_breakdown": {
                "stop_loss": 0,
                "target": 0,
                "target_partial": 0,
                "trailing_stop": 0,
                "signal_invalidated": 0,
                "holding_period": 0,
                "atr_trailing_stop": 0,
            },
        }

    # Apply round-trip transaction costs to every trade's return.
    # This models brokerage, STT, exchange fees, and slippage.
    # At 0.5% per trade, 152 trades = ~7.6% total drag on capital — real and material.
    cost_adjusted_returns = [t.return_pct - ROUND_TRIP_COST_PCT for t in trades]

    returns = cost_adjusted_returns  # use cost-adjusted throughout
    total_trades = len(trades)
    winning_trades = [r for r in returns if r > 0]
    win_rate = len(winning_trades) / total_trades
    losing_returns = [r for r in returns if r <= 0]
    avg_win_pct = sum(winning_trades) / len(winning_trades) if winning_trades else 0.0
    avg_loss_pct = sum(losing_returns) / len(losing_returns) if losing_returns else 0.0
    expectancy = (win_rate * avg_win_pct) + ((1 - win_rate) * avg_loss_pct)
    profit_factor = (
        (win_rate * avg_win_pct) / ((1 - win_rate) * abs(avg_loss_pct))
        if losing_returns and avg_loss_pct != 0
        else 0.0
    )

    reason_counts = Counter(t.exit_reason for t in trades)
    exit_breakdown = {
        "stop_loss": reason_counts.get("stop_loss", 0),
        "target": reason_counts.get("target", 0),
        "target_partial": reason_counts.get("target_partial", 0),
        "trailing_stop": reason_counts.get("trailing_stop", 0),
        "atr_trailing_stop": reason_counts.get("atr_trailing_stop", 0),
        "signal_invalidated": reason_counts.get("signal_invalidated", 0),
        "holding_period": reason_counts.get("holding_period", 0),
    }

    avg_return_pct = sum(returns) / total_trades
    median_return_pct = float(pd.Series(returns).median())
    best_trade_pct = max(returns)
    worst_trade_pct = min(returns)

    # Cost-adjusted PnL: cost already baked into cost_adjusted_returns
    total_pnl = sum(
        (t.return_pct - ROUND_TRIP_COST_PCT)
        / 100.0
        * (t.position_size_used or config.position_size)
        for t in trades
    )
    total_return_pct = (
        (total_pnl / config.starting_capital) * 100
        if config.starting_capital > 0
        else 0.0
    )

    # Benchmark return
    benchmark_return_pct = 0.0
    if benchmark_data is not None and len(benchmark_data) > 1:
        start_price = benchmark_data.iloc[0]["Close"]
        end_price = benchmark_data.iloc[-1]["Close"]
        benchmark_return_pct = ((end_price - start_price) / start_price) * 100

    # Equity Curve Construction
    strat_returns_by_date = {}
    for t in trades:
        d = t.exit_date
        # Cost-adjusted P&L
        pl = (
            (t.return_pct - ROUND_TRIP_COST_PCT)
            / 100.0
            * (t.position_size_used or config.position_size)
        )
        strat_returns_by_date[d] = strat_returns_by_date.get(d, 0) + pl

    equity_curve = []
    cumulative_pl = 0.0

    if benchmark_data is not None:
        first_bench_price = benchmark_data.iloc[0]["Close"]

        for date, row in benchmark_data.iterrows():
            d = date.date()
            cumulative_pl += strat_returns_by_date.get(d, 0.0)

            # Scaled benchmark: (Price / StartPrice) * config.starting_capital
            bench_equity = (row["Close"] / first_bench_price) * config.starting_capital

            equity_curve.append(
                {
                    "date": d.isoformat(),
                    "equity": float(config.starting_capital + cumulative_pl),
                    "benchmark_equity": float(bench_equity),
                }
            )

    # Updated Sharpe Ratio using trade returns instead of flat equity curve returns
    sharpe_ratio = 0.0
    if len(returns) > 1:
        r_series = pd.Series(returns)
        if r_series.std() > 0:
            # Annualise assuming average 20 trades/year per symbol universe
            # Use trades per year ratio relative to a 252-day year
            date_range_days = max(
                (
                    max(t.exit_date for t in trades) - min(t.entry_date for t in trades)
                ).days,
                1,
            )
            trades_per_year = len(returns) / (date_range_days / 252)
            sharpe_ratio = (r_series.mean() / r_series.std()) * (trades_per_year**0.5)

    # Max Drawdown from equity curve
    max_drawdown_pct = 0.0
    if equity_curve:
        equities = [pt["equity"] for pt in equity_curve]
        peak = equities[0]
        for e in equities:
            if e > peak:
                peak = e
            dd = (peak - e) / peak * 100 if peak > 0 else 0
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd

    return {
        "total_trades": total_trades,
        "winning_trades": len(winning_trades),
        "win_rate": float(win_rate * 100),
        "avg_return_pct": float(avg_return_pct),
        "median_return_pct": float(median_return_pct),
        "best_trade_pct": float(best_trade_pct),
        "worst_trade_pct": float(worst_trade_pct),
        "max_drawdown_pct": float(max_drawdown_pct),
        "sharpe_ratio": float(sharpe_ratio),
        "total_return_pct": float(total_return_pct),
        "gross_return_pct": float(  # New: pre-cost return
            sum(
                t.return_pct / 100.0 * (t.position_size_used or config.position_size)
                for t in trades
            )
            / config.starting_capital
            * 100
        ),
        "total_cost_drag_pct": float(  # New: explicit cost drag
            len(trades)
            * (ROUND_TRIP_COST_PCT / 100.0)  # pct → decimal
            * (
                sum(t.position_size_used or config.position_size for t in trades)
                / len(trades)
            )
            / config.starting_capital
            * 100
            if trades
            else 0.0
        ),
        "benchmark_return_pct": float(benchmark_return_pct),
        "equity_curve": equity_curve,
        "expectancy": float(expectancy),
        "profit_factor": float(profit_factor),
        "avg_win_pct": float(avg_win_pct),
        "avg_loss_pct": float(avg_loss_pct),
        "exit_breakdown": exit_breakdown,
    }


def run_backtest(db: Session, run_id: str, config: BacktestConfig):
    """
    Main orchestrator for the backtest.
    """
    log_handler = logging_manager.setup_run_logging(run_id)
    try:
        logger.info(f"Starting backtest {run_id}")
        run = db.query(BacktestRun).filter(BacktestRun.run_id == run_id).first()
        if not run:
            logger.error(f"BacktestRun {run_id} not found")
            return

        try:
            # Update status to running
            run.status = "running"
            db.commit()

            # 1. Fetch benchmark data (^NSEI)
            logger.info("Fetching benchmark data (^NSEI)")
            benchmark_df = _get_cached_ohlcv("^NSEI", period="5y")

            regime_dict = {}
            if benchmark_df is not None and not benchmark_df.empty:
                # pandas-ta extensions need to be available
                benchmark_df.ta.ema(length=50, append=True)
                benchmark_df.ta.ema(length=200, append=True)
                # Require price above BOTH 50 EMA (short-term trend) and 200 EMA (macro trend).
                # Nifty above 50 EMA alone allows entries during corrections; the 200 EMA
                # confirms the macro bull market is intact before taking any long position.
                valid = benchmark_df[
                    benchmark_df["EMA_50"].notna() & benchmark_df["EMA_200"].notna()
                ]
                regime_dict = dict(
                    zip(
                        valid.index.date,
                        (valid["Close"] > valid["EMA_50"])
                        & (valid["Close"] > valid["EMA_200"])
                        & (
                            valid["EMA_50"] > valid["EMA_200"]
                        ),  # Golden cross: 50 EMA above 200 EMA confirms
                        # structural bull market, not just a bounce.
                        # Blocks entries when index recovered above EMAs
                        # but the trend hasn't structurally reversed yet.
                    )
                )

            # 2. Select symbols
            screen_dates_map: dict[str, list[datetime.date]] = {}
            is_screen_filtered = bool(
                config.screen_slug and config.screen_slug != "all"
            )

            if is_screen_filtered:
                if config.screen_slug not in SCREEN_REGISTRY:
                    raise ValueError(f"Invalid screen slug: {config.screen_slug}")

                logger.info(
                    f"Filtering symbols using historical screen data: {config.screen_slug}"
                )
                # Fetch symbols that passed this screen at any point during the backtest window
                raw_screen_rows = (
                    db.query(ScreenResult.symbol, ScreenResult.computed_at)
                    .filter(
                        ScreenResult.screen_slug == config.screen_slug,
                        ScreenResult.computed_at >= config.date_from,
                        ScreenResult.computed_at <= config.date_to,
                    )
                    .all()
                )

                if not raw_screen_rows:
                    logger.warning(
                        "Selected screen '%s' returned no historical data for the period %s to %s.",
                        config.screen_slug,
                        config.date_from,
                        config.date_to,
                    )

                for symbol, computed_at in raw_screen_rows:
                    # computed_at may be datetime.date or datetime.datetime
                    d = (
                        computed_at
                        if isinstance(computed_at, datetime.date)
                        else computed_at.date()
                    )
                    screen_dates_map.setdefault(symbol, []).append(d)

                # Sort each symbol's screen dates for bisect lookup in simulate_trades
                for sym in screen_dates_map:
                    screen_dates_map[sym].sort()

                symbols = list(screen_dates_map.keys())
            else:
                symbol_query = (
                    db.query(TechnicalSignal.symbol)
                    .group_by(TechnicalSignal.symbol)
                    .order_by(func.max(TechnicalSignal.date).desc())
                    .all()
                )
                symbols = [row[0] for row in symbol_query]

            if config.symbol_limit:
                symbols = symbols[: config.symbol_limit]

            run.symbols_total = len(symbols)
            db.commit()

            all_trades = []
            symbols_processed = 0

            # Pre-fetch sector info if needed
            stocks_info = {s.symbol: s.sector for s in db.query(Stock).all()}
            # Pre-fetch fundamental cache if needed
            fund_caches = {}
            if config.include_fundamentals:
                fund_caches = {c.symbol: c for c in db.query(FundamentalCache).all()}

            # Collect scored signals and DataFrames for potential portfolio simulation
            all_signals_map: dict[str, list[dict]] = {}
            all_dfs_map: dict[str, pd.DataFrame] = {}
            weekly_maps: dict[str, dict] = {}
            monthly_maps: dict[str, dict] = {}
            use_portfolio_sim = (
                config.max_concurrent_positions > 0 or config.max_sector_positions > 0
            )

            for symbol in symbols:
                try:
                    # Fetch historical OHLCV via optimized cache
                    df = _get_cached_ohlcv(symbol, period="5y")
                    if df is None or df.empty:
                        continue

                    fund_cache = fund_caches.get(symbol)

                    # ── Signal generation: screen-driven (Model B) vs. score_series (Model A) ──
                    # If screen_signal_mode is True and we have a screen, use screen dates.
                    if config.screen_signal_mode and is_screen_filtered:
                        scored_dates = _build_screen_driven_signals(
                            symbol, screen_dates_map.get(symbol, []), df, config
                        )
                    else:
                        scored_dates = score_series(
                            df, symbol=symbol, fund_cache=fund_cache, config=config
                        )

                    # Multi-Timeframe Confirmation
                    weekly_state_map = None
                    monthly_state_map = None
                    if config.require_weekly_confirmation:
                        weekly_state_map = build_mtf_state_map(df, "W")
                    if config.require_monthly_confirmation:
                        monthly_state_map = build_mtf_state_map(df, "M")

                    # Run simulation
                    sector = stocks_info.get(symbol, "Unknown")

                    if use_portfolio_sim:
                        # Accumulate for cross-symbol chronological simulation
                        all_signals_map[symbol] = scored_dates
                        all_dfs_map[symbol] = df
                        if weekly_state_map is not None:
                            weekly_maps[symbol] = weekly_state_map
                        if monthly_state_map is not None:
                            monthly_maps[symbol] = monthly_state_map
                    else:
                        # Original per-symbol path (no portfolio limits)
                        trades = simulate_trades(
                            symbol,
                            sector,
                            df,
                            scored_dates,
                            config,
                            regime_dict=regime_dict,
                            weekly_state_map=weekly_state_map,
                            monthly_state_map=monthly_state_map,
                            screen_dates=screen_dates_map.get(symbol, [])
                            if is_screen_filtered
                            else None,
                            is_screen_driven=config.screen_signal_mode
                            and is_screen_filtered,
                        )

                        # Save trades to DB
                        db_trades = []
                        for t in trades:
                            db_trade = {
                                "run_id": run_id,
                                "symbol": t.symbol,
                                "sector": t.sector,
                                "signal_date": t.signal_date,
                                "entry_date": t.entry_date,
                                "exit_date": t.exit_date,
                                "exit_reason": t.exit_reason,
                                "signal_score": t.signal_score,
                                "entry_price": t.entry_price,
                                "exit_price": t.exit_price,
                                "return_pct": t.return_pct,
                                "rsi_at_signal": t.rsi_at_signal,
                                "adx_at_signal": t.adx_at_signal,
                                "ema_signal": t.ema_signal,
                            }
                            db_trades.append(db_trade)
                            all_trades.append(t)

                        if db_trades:
                            db.bulk_insert_mappings(BacktestTrade, db_trades)

                    symbols_processed += 1

                    # Periodic commits
                    if symbols_processed % 10 == 0:
                        db.commit()

                    if symbols_processed % 5 == 0:
                        run.symbols_done = symbols_processed
                        db.commit()

                except Exception as e:
                    logger.error(f"Error processing {symbol}: {e}")
                    logger.error(traceback.format_exc())
                    continue

            # Portfolio simulation path — runs after all signals are collected
            if use_portfolio_sim and all_signals_map:
                logger.info(
                    "Running portfolio simulation with max_concurrent=%d, max_sector=%d",
                    config.max_concurrent_positions,
                    config.max_sector_positions,
                )
                all_trades = simulate_portfolio(
                    all_signals_map,
                    all_dfs_map,
                    stocks_info,
                    config,
                    regime_dict=regime_dict,
                    weekly_state_maps=weekly_maps
                    if config.require_weekly_confirmation
                    else None,
                    monthly_state_maps=monthly_maps
                    if config.require_monthly_confirmation
                    else None,
                    screen_dates_map=screen_dates_map if is_screen_filtered else None,
                    is_screen_driven=config.screen_signal_mode and is_screen_filtered,
                )
                db_trades = []
                for t in all_trades:
                    db_trade = {
                        "run_id": run_id,
                        "symbol": t.symbol,
                        "sector": t.sector,
                        "signal_date": t.signal_date,
                        "entry_date": t.entry_date,
                        "exit_date": t.exit_date,
                        "exit_reason": t.exit_reason,
                        "signal_score": t.signal_score,
                        "entry_price": t.entry_price,
                        "exit_price": t.exit_price,
                        "return_pct": t.return_pct,
                        "rsi_at_signal": t.rsi_at_signal,
                        "adx_at_signal": t.adx_at_signal,
                        "ema_signal": t.ema_signal,
                    }
                    db_trades.append(db_trade)
                if db_trades:
                    db.bulk_insert_mappings(BacktestTrade, db_trades)
                    db.commit()

            # 3. Finalize
            logger.info(f"Computing final metrics for {len(all_trades)} trades")

            # Slice benchmark data to match backtest range
            if all_trades and benchmark_df is not None:
                first_entry = min(t.entry_date for t in all_trades)
                effective_from = config.date_from or first_entry
                effective_to = config.date_to or datetime.date.today()

                benchmark_df = benchmark_df[
                    (benchmark_df.index.normalize() >= pd.Timestamp(effective_from))
                    & (benchmark_df.index.normalize() <= pd.Timestamp(effective_to))
                ]

            metrics = compute_metrics(all_trades, benchmark_df, config)

            # Update run with results
            run.total_trades = metrics["total_trades"]
            run.winning_trades = metrics["winning_trades"]
            run.win_rate = metrics["win_rate"]
            run.avg_return_pct = metrics["avg_return_pct"]
            run.median_return_pct = metrics["median_return_pct"]
            run.best_trade_pct = metrics["best_trade_pct"]
            run.worst_trade_pct = metrics["worst_trade_pct"]
            run.max_drawdown_pct = metrics["max_drawdown_pct"]
            run.sharpe_ratio = metrics["sharpe_ratio"]
            run.total_return_pct = metrics["total_return_pct"]
            run.gross_return_pct = metrics["gross_return_pct"]
            run.total_cost_drag_pct = metrics["total_cost_drag_pct"]
            run.benchmark_return_pct = metrics["benchmark_return_pct"]
            run.expectancy = metrics["expectancy"]
            run.profit_factor = metrics["profit_factor"]
            run.avg_win_pct = metrics["avg_win_pct"]
            run.avg_loss_pct = metrics["avg_loss_pct"]
            run.exit_breakdown_json = json.dumps(metrics["exit_breakdown"])
            run.equity_curve_json = json.dumps(metrics["equity_curve"])

            run.symbols_done = len(symbols)
            run.status = "complete"
            db.commit()
            logger.info(f"Backtest {run_id} completed successfully")

        except Exception as e:
            db.rollback()
            logger.error(f"Backtest {run_id} failed: {e}")
            logger.error(traceback.format_exc())
            run.status = "failed"
            run.error_message = str(e)
            db.commit()
    finally:
        logging_manager.cleanup_run_logging(log_handler)
