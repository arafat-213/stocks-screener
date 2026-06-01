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
from app.core.trading_config import UnifiedTradingConfig as BacktestConfig
from app.db.models import (
    BacktestRun,
    BacktestTrade,
    FundamentalCache,
    ScreenResult,
    Stock,
)
from app.pipeline.ohlcv_cache import OHLCVCache
from app.pipeline.scorer import (
    calculate_fundamental_score,
    calculate_technical_indicators,
    calculate_technical_score,
)
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
# Stores {symbol: DataFrame} where DataFrame contains all precomputed indicators.
# Metadata tracks the latest date in the cached DataFrame to ensure freshness.
_TA_CACHE = {}
_TA_METADATA = {}  # {symbol: latest_date}

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

    df = calculate_technical_indicators(df)

    if symbol:
        _TA_CACHE[symbol] = df
        _TA_METADATA[symbol] = df.index[-1]

    return df


def _score_bar_from_precomputed(df_ind: pd.DataFrame, i: int) -> dict:
    """
    Wrapper for calculate_technical_score using pre-computed indicators.
    Maps results to the format expected by the backtest engine.
    """
    res = calculate_technical_score(df_ind, timeframe="D", i=i, skip_ta=True)

    # Add backtest-specific keys for compatibility
    res["date"] = df_ind.index[i]
    res["close"] = float(df_ind["Close"].iloc[i])

    return res


def _compute_signal_tier(signal: dict, config: Optional[BacktestConfig] = None) -> int:
    ema = signal.get("ema_signal")
    vol = signal.get("volume_breakout", False)
    adx = signal.get("adx") or 0.0
    rsi = signal.get("rsi") or 0.0

    # Use config values or fall back to sensible defaults
    rsi_min = config.rsi_min if config else 40.0
    rsi_max = config.rsi_max if config else 65.0
    min_adx = config.min_adx if config else 25.0

    is_core_ema = ema in ["bullish_cross", "bullish_pullback"]
    if not is_core_ema:
        return 4

    if rsi > rsi_max:
        return 3
    if rsi < rsi_min:
        return 3

    if vol and adx >= min_adx:
        return 1
    if vol or adx >= min_adx:
        return 2

    return 3


def _lookup_mtf_state(state_map: dict, date: datetime.date) -> bool:
    if not state_map:
        return True
    if date in state_map:
        return state_map[date]
    sorted_dates = sorted(state_map.keys())
    idx = bisect.bisect_right(sorted_dates, date)
    if idx == 0:
        return False
    return state_map[sorted_dates[idx - 1]]


def _compute_position_size(
    config: BacktestConfig, entry_price: float, atr: float = None
) -> float:
    if not config.use_volatility_sizing or atr is None or atr <= 0:
        return config.position_size

    risk_amount = config.starting_capital * (config.risk_per_trade_pct / 100.0)
    stop_distance = config.atr_multiplier * atr
    if stop_distance <= 0:
        return config.position_size

    shares = risk_amount / stop_distance
    pos_size = shares * entry_price
    max_allowed = config.starting_capital * (config.max_position_pct / 100.0)
    return min(pos_size, max_allowed)


def _build_screen_driven_signals(
    symbol: str,
    screen_dates: list[datetime.date],
    df: pd.DataFrame,
    config: BacktestConfig,
) -> list[dict]:
    """
    Model B signal builder.
    Each date the stock appeared in the named screen becomes a candidate signal.
    """
    if df is None or df.empty or not screen_dates:
        return []

    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)

    df_ind = _compute_all_indicators(df, symbol=symbol)
    date_to_idx = {
        d.date() if hasattr(d, "date") else d: i for i, d in enumerate(df.index)
    }

    signals = []
    last_signal_date = None
    reentry_gap = getattr(config, "screen_reentry_gap_days", 60)

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
            bar = _score_bar_from_precomputed(df_ind, idx)
        except Exception:
            continue

        if bar.get("above_200ema") is not True:
            continue
        if bar.get("momentum_12m") is not None and bar["momentum_12m"] < 0:
            continue

        rsi_max = getattr(config, "screen_driven_rsi_max", 75.0)
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
                "ema20_level": bar["ema20_level"],
                "is_consolidating": True,
            }
        )
        last_signal_date = screen_date

    return signals


def score_series(
    df: pd.DataFrame,
    symbol: str = None,
    fund_cache: FundamentalCache = None,
    config: BacktestConfig = None,
) -> list[dict]:
    if df is None or df.empty:
        return []

    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)

    df_ind = _compute_all_indicators(df, symbol=symbol)

    # Precompute consolidation series
    consol_window = config.consolidation_bars if config else 15
    max_range = config.consolidation_max_range_pct if config else 12.0
    rolling_max = df_ind["High"].rolling(window=consol_window).max()
    rolling_min = df_ind["Low"].rolling(window=consol_window).min()
    consol_range = (rolling_max / rolling_min - 1) * 100
    is_consolidating_series = consol_range <= max_range

    fund_score = 0
    if config and config.include_fundamentals:
        fund_score = calculate_fundamental_score({}, fund_cache=fund_cache)

    scored_dates = []
    start_idx = 260
    for i in range(start_idx, len(df_ind)):
        date = df_ind.index[i].date()
        if config:
            if config.date_from and date < config.date_from:
                continue
            if config.date_to and date > config.date_to:
                continue

        bar_score = _score_bar_from_precomputed(df_ind, i)
        bar_score["score"] += fund_score
        bar_score["is_consolidating"] = bool(is_consolidating_series.iloc[i])
        # For backtesting, we collect all signals to maintain consistent series length for tests
        scored_dates.append(bar_score)

    return scored_dates


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
    trades = []
    last_exit_idx = -1
    _sorted_screen_dates = sorted(screen_dates) if screen_dates else None
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

        # MTF Confirmation Gates
        if config.require_weekly_confirmation and weekly_state_map is not None:
            sorted_w_dates = sorted(weekly_state_map.keys())
            w_idx = bisect.bisect_right(sorted_w_dates, compare_date)
            if w_idx == 0:
                continue
            if not weekly_state_map[sorted_w_dates[w_idx - 1]]:
                continue

        if config.require_monthly_confirmation and monthly_state_map is not None:
            sorted_m_dates = sorted(monthly_state_map.keys())
            m_idx = bisect.bisect_right(sorted_m_dates, compare_date)
            if m_idx == 0:
                continue
            if not monthly_state_map[sorted_m_dates[m_idx - 1]]:
                continue

        if _sorted_screen_dates is not None and not is_screen_driven:
            window_days = getattr(config, "screen_membership_window_days", 7)
            window_start = compare_date - datetime.timedelta(days=window_days)
            lo = bisect.bisect_left(_sorted_screen_dates, window_start)
            hi = bisect.bisect_right(_sorted_screen_dates, compare_date)
            if lo >= hi:
                continue

        signal_idx = date_to_idx.get(signal_date)
        if signal_idx is None or signal_idx <= last_exit_idx:
            continue

        if signal.get("above_200ema") in [False, None]:
            continue
        if signal.get("momentum_12m") is not None and signal["momentum_12m"] < 0:
            continue

        if not is_screen_driven:
            if config.min_adx > 0:
                adx_val = signal.get("adx")
                if adx_val is None or adx_val < config.min_adx:
                    continue

            if _compute_signal_tier(signal, config) > config.min_signal_tier:
                continue
            if (signal.get("rsi") or 0.0) > config.rsi_max:
                continue
            if signal["score"] < config.effective_score_threshold:
                continue
            if config.require_consolidation and not signal.get("is_consolidating"):
                continue
            if config.require_volume_breakout and not signal.get("volume_breakout"):
                continue

        # Entry Logic
        ema_signal_type = signal.get("ema_signal", "")
        signal_ema20 = signal.get("ema20_level")

        entry_idx = None
        entry_price = None
        entry_date = None

        use_pullback = (
            config.use_pullback_entry
            and ema_signal_type == "bullish_cross"
            and signal_ema20 is not None
            and signal_ema20 > 0
        )

        if use_pullback:
            tol = config.pullback_tolerance_pct / 100.0
            all_bars_above = True
            closest_approach = float("inf")
            for wait_k in range(
                signal_idx + 1,
                min(signal_idx + config.pullback_max_wait_bars + 1, len(df)),
            ):
                wait_compare = df.index[wait_k].date()
                if config.use_regime_filter and regime_dict:
                    if not regime_dict.get(wait_compare, False):
                        all_bars_above = False
                        break
                low, close = df.iloc[wait_k]["Low"], df.iloc[wait_k]["Close"]
                if close < signal_ema20 * 0.975:
                    all_bars_above = False
                    break
                approach = (low - signal_ema20) / signal_ema20 * 100
                closest_approach = min(closest_approach, approach)
                if low <= signal_ema20 * (1 + tol) and close >= signal_ema20 * 0.995:
                    entry_idx, entry_date, entry_price = (
                        wait_k,
                        df.index[wait_k],
                        float(close),
                    )
                    break
            if entry_idx is None and all_bars_above and closest_approach <= 8.0:
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
                if config.use_regime_filter and regime_dict:
                    if not regime_dict.get(entry_date.date(), False):
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
        pos_size = _compute_position_size(config, entry_price, atr=eff_atr)

        atr_val = signal.get("atr")
        if is_screen_driven:
            base_stop = (
                entry_price - config.atr_multiplier * eff_atr
                if eff_atr > 0
                else entry_price * 0.93
            )
        else:
            consol_low = df.iloc[
                max(0, signal_idx - config.consolidation_bars) : signal_idx
            ]["Low"].min()
            struct_stop = consol_low * 0.98 if pd.notna(consol_low) else None
            atr_stop = (
                entry_price - config.atr_multiplier * atr_val if atr_val else None
            )
            base_stop = (
                min(struct_stop, atr_stop)
                if struct_stop and atr_stop
                else (struct_stop or atr_stop or entry_price * 0.93)
            )

        # Use base_stop directly to allow for volatility-based stops (e.g. 10%+ for midcaps)
        # Cap at 99% of entry to ensure it's always a sell-below stop.
        stop_price = min(base_stop, entry_price * 0.99)
        actual_risk = max(entry_price - stop_price, entry_price * 0.02)
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

            if high >= entry_price + actual_risk:
                stop_price = max(stop_price, entry_price)

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

            if not t1_hit and t1_price and high >= t1_price:
                t1_hit = True
                t1_trade = TradeResult(
                    symbol,
                    sector,
                    (
                        signal_date.date()
                        if hasattr(signal_date, "date")
                        else signal_date
                    ),
                    (entry_date.date() if hasattr(entry_date, "date") else entry_date),
                    (
                        df.index[k].date()
                        if hasattr(df.index[k], "date")
                        else df.index[k]
                    ),
                    "target_partial",
                    signal.get("score", 0),
                    entry_price,
                    t1_price,
                    float((t1_price / entry_price - 1) * 100),
                    signal.get("rsi", 0),
                    signal.get("adx", 0),
                    signal.get("ema_signal", "neutral"),
                    pos_size * 0.5,
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
            )
        )
        last_exit_idx = date_to_idx.get(exit_date, -1)

    return trades


def simulate_portfolio(
    all_signals: dict[str, list[dict]],
    all_dfs: dict[str, pd.DataFrame],
    stocks_info: dict[str, str],
    config: BacktestConfig,
    regime_dict: dict = None,
    weekly_state_maps: dict = None,
    monthly_state_maps: dict = None,
    screen_dates_map: dict = None,
    is_screen_driven: bool = False,
):
    timeline = []
    for sym, signals in all_signals.items():
        for sig in signals:
            sig_date = sig["date"]
            date_only = sig_date.date() if hasattr(sig_date, "date") else sig_date
            timeline.append((date_only, sym, sig))
    timeline.sort(key=lambda x: x[0])

    all_trades, open_pos = [], {}
    for date, sym, sig in timeline:
        if sym in open_pos and open_pos[sym] > date:
            continue

        if config.max_concurrent_positions:
            active_count = sum(1 for d in open_pos.values() if d > date)
            if active_count >= config.max_concurrent_positions:
                continue

        if config.max_sector_positions:
            sector = stocks_info.get(sym, "Unknown")
            sector_active = sum(
                1
                for other_sym, exit_d in open_pos.items()
                if stocks_info.get(other_sym) == sector and exit_d > date
            )
            if sector_active >= config.max_sector_positions:
                continue

        df = all_dfs.get(sym)
        if df is None:
            continue
        trades = simulate_trades(
            sym,
            stocks_info.get(sym, "Unknown"),
            df,
            [sig],
            config,
            regime_dict,
            (weekly_state_maps or {}).get(sym),
            (monthly_state_maps or {}).get(sym),
            (screen_dates_map or {}).get(sym),
            is_screen_driven,
        )
        if trades:
            open_pos[sym] = trades[-1].exit_date
            all_trades.extend(trades)
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
            "sharpe_ratio": 0.0,
            "benchmark_return_pct": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "equity_curve": [],
            "exit_breakdown": {},
        }

    rets = [t.return_pct - ROUND_TRIP_COST_PCT for t in trades]
    psizes = [t.position_size_used or config.position_size for t in trades]
    total_deployed = sum(psizes)
    win_mask = [r > 0 for r in rets]
    win_weight = sum(p for r, p in zip(rets, psizes) if r > 0)
    win_rate = win_weight / total_deployed if total_deployed > 0 else 0.0

    avg_win = (
        sum(r * p for r, p in zip(rets, psizes) if r > 0) / win_weight
        if win_weight > 0
        else 0.0
    )
    loss_weight = sum(p for r, p in zip(rets, psizes) if r <= 0)
    avg_loss = (
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
    sharpe = 0.0
    bench_ret = 0.0

    if benchmark_data is not None and not benchmark_data.empty:
        strat_by_date = {}
        for t, p in zip(trades, psizes):
            strat_by_date[t.exit_date] = strat_by_date.get(t.exit_date, 0.0) + (
                (t.return_pct - ROUND_TRIP_COST_PCT) / 100.0 * p
            )

        cum_pl, first_p = 0.0, benchmark_data.iloc[0]["Close"]
        max_equity = config.starting_capital
        daily_returns = []
        prev_equity = config.starting_capital

        for d, row in benchmark_data.iterrows():
            date_only = d.date() if hasattr(d, "date") else d
            cum_pl += strat_by_date.get(date_only, 0.0)
            current_equity = config.starting_capital + cum_pl

            # Stats
            max_equity = max(max_equity, current_equity)
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
        "profit_factor": (win_weight * avg_win) / (abs(loss_weight * avg_loss))
        if loss_weight and avg_loss != 0
        else 0.0,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "benchmark_return_pct": bench_ret,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "equity_curve": equity_curve,
        "exit_breakdown": dict(Counter(t.exit_reason for t in trades)),
    }


def run_backtest(db: Session, run_id: str, config: BacktestConfig):
    logging_manager.setup_run_logging(run_id)
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
        regime_dict = {}
        if bench_df is not None:
            bench_df.ta.ema(length=50, append=True)
            bench_df.ta.ema(length=200, append=True)
            v = bench_df.dropna(subset=["EMA_50", "EMA_200"])
            regime_dict = dict(
                zip(
                    v.index.date,
                    (v["Close"] > v["EMA_50"])
                    & (v["Close"] > v["EMA_200"])
                    & (v["EMA_50"] > v["EMA_200"]),
                )
            )

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
            symbols = [
                s.symbol
                for s in db.query(Stock).filter(Stock.is_active).limit(500).all()
            ]

        if config.symbol_limit:
            symbols = symbols[: config.symbol_limit]

        run.symbols_total = len(symbols)
        db.commit()

        all_trades = []
        all_signals, all_dfs = {}, {}
        symbols_processed = 0

        stocks_info = {s.symbol: s.sector for s in db.query(Stock).all()}
        fund_caches = {}
        if config.include_fundamentals:
            fund_caches = {c.symbol: c for c in db.query(FundamentalCache).all()}

        for sym in symbols:
            try:
                df = _get_cached_ohlcv(sym, period=lookback_period)
                if df is None or df.empty:
                    continue
                all_dfs[sym] = df
                if config.screen_signal_mode and is_filtered:
                    sigs = _build_screen_driven_signals(
                        sym, screen_dates_map.get(sym, []), df, config
                    )
                else:
                    sigs = score_series(
                        df,
                        symbol=sym,
                        fund_cache=fund_caches.get(sym),
                        config=config,
                    )
                all_signals[sym] = sigs
                symbols_processed += 1
                if symbols_processed % 10 == 0:
                    run.symbols_done = symbols_processed
                    db.commit()
            except Exception as e:
                logger.error(f"Error processing {sym}: {e}")
                continue

        all_trades = simulate_portfolio(
            all_signals,
            all_dfs,
            stocks_info,
            config,
            regime_dict,
            screen_dates_map=screen_dates_map,
            is_screen_driven=config.screen_signal_mode,
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
        run.sharpe_ratio = float(_clean(metrics["sharpe_ratio"]))
        run.benchmark_return_pct = float(_clean(metrics["benchmark_return_pct"]))
        run.avg_win_pct = float(_clean(metrics["avg_win_pct"]))
        run.avg_loss_pct = float(_clean(metrics["avg_loss_pct"]))
        run.exit_breakdown_json = json.dumps(
            metrics["exit_breakdown"], cls=NumpyEncoder
        )
        run.equity_curve_json = json.dumps(metrics["equity_curve"], cls=NumpyEncoder)

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
