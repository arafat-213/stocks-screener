"""indicators.py — textbook-frozen, pure vectorized indicators (v4/02 §2).

Every function is pure and trailing-only by construction, so no value for day D
can ever depend on a bar after D (the §5.5 no-lookahead guarantee, proven by the
future-bar-corruption test). All math consumes the **split/bonus-adjusted**
series only (never `close_raw`) — a corporate action must not be able to inflate
an MA, the MACD, or the ATR trail (01/05 adjustment discipline).

Parameters are the `00` §3.2 constants; they are passed in (not hardcoded) so
tiny hand-computed fixtures can exercise them, but default to the frozen values
in `SwingConfig`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(close: pd.Series, n: int) -> pd.Series:
    """Exponential MA: ``ewm(span=n, adjust=False)`` — recursive, trailing only."""
    return close.ewm(span=n, adjust=False).mean()


def sma(close: pd.Series, n: int) -> pd.Series:
    """Simple MA with ``min_periods=n`` — no partial-window value is ever emitted."""
    return close.rolling(n, min_periods=n).mean()


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series]:
    """MACD(fast, slow, signal): line = EMA_fast − EMA_slow; signal = EMA_signal(line).

    Returns ``(macd_line, signal_line)``. Both are trailing EMAs ⇒ no lookahead.
    """
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


def weekly_macd_line(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.Series:
    """Weekly MACD **line**, aligned back onto the daily index, completed-weeks-only.

    Steps (v4/02 §2):
      1. Resample the adjusted daily close to weekly bars (``W-FRI``), taking the
         last print of each week.
      2. Compute MACD on the weekly series — its index is each week-ending Friday.
      3. Align onto the daily index by **as-of** ffill: each daily date D carries
         the weekly value of the most recent week-end label ≤ D.

    The in-progress (un-closed) week's label is the *upcoming* Friday > D, so a
    mid-week day never sees it (the §5.6 completed-weeks-only guard). And every
    daily label ≤ D maps to a week whose constituent bars are all ≤ D, so
    corrupting bars after D cannot change any day-≤D value (§5.5 no-lookahead).
    """
    weekly_close = close.resample("W-FRI").last()
    line, _ = macd(weekly_close, fast, slow, signal)
    # method="ffill" picks the last weekly label <= each daily date (as-of).
    return line.reindex(close.index, method="ffill")


def atr_wilder(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    n: int = 20,
) -> pd.Series:
    """Wilder's ATR over ``n`` on the **adjusted** O/H/L/C.

    TR_t = max(high−low, |high−prev_close|, |low−prev_close|).
    The first TR has no prior close ⇒ TR_0 = high_0 − low_0.
    ATR is Wilder-smoothed: seed = mean(first n TR), then
    ATR_t = (ATR_{t-1}·(n−1) + TR_t) / n. Values before index n−1 are NaN
    (insufficient window). Trailing only ⇒ no lookahead.
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)  # skipna=True ⇒ TR_0 = high_0 − low_0 (prev_close NaN ignored)
    return _wilder_rma(tr, n)


def _wilder_rma(values: pd.Series, n: int) -> pd.Series:
    """Wilder's running moving average (RMA): SMA seed at n−1, then recursive."""
    arr = values.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan)
    if len(arr) >= n:
        out[n - 1] = arr[:n].mean()
        for i in range(n, len(arr)):
            out[i] = (out[i - 1] * (n - 1) + arr[i]) / n
    return pd.Series(out, index=values.index)
