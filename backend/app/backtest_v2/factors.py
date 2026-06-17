"""
factors.py — Track-A cross-sectional factor library for v3 (prereg §4, §5).

Pure factor primitives only — no engine wiring (that is T2). Each factor is a
pure function over the long-format prices frame and returns a **wide** DataFrame
(index = trading date, columns = isin) of raw factor values, oriented so that
HIGHER = BETTER. Cross-sectional percentile-ranking and the equal-weight blend
happen in `composite_rank` (prereg §5).

Sign conventions (all oriented higher-is-better so ranking is uniform):
  - momentum (12-1 / 6-1) : raw lookback return — higher trend = better.
  - low volatility         : NEGATED annualised vol — for *ranking* this is
                             order-equivalent to the prereg's "inverse vol"
                             but avoids the 1/0 singularity at vol→0.
  - trend quality          : fraction of up-days over the window — smoother path.
  - short-term reversal    : NEGATED 1-month return — fades recent overextension.

Indicator math consumes `close` (split+bonus-adjusted, ex-dividend) only — never
`close_tr` (MTM/P&L territory, portfolio.py only), mirroring signals.py.

Momentum reuses signals._momentum_12_1 (integer-position indexing, calendar-gap
safe) rather than re-implementing it (Rule 3).
"""

from __future__ import annotations

import math

import pandas as pd

from app.backtest_v2.signals import _momentum_12_1
from app.backtest_v2.v3_config import V3Config

# Track-A factor names (must match V3Config.active_factors vocabulary).
FACTOR_NAMES: frozenset[str] = frozenset(
    {"mom_12_1", "mom_6_1", "low_vol", "trend_quality", "reversal"}
)

# Calendar-month approximation for the rank-smoothing window (prereg §3.1).
_TRADING_DAYS_PER_MONTH = 21


# ---------------------------------------------------------------------------
# Per-ISIN → wide assembly
# ---------------------------------------------------------------------------


def _per_isin_wide(
    prices: pd.DataFrame,
    fn,
) -> pd.DataFrame:
    """
    Apply a per-ISIN time-series function `fn(close: Series) -> Series` to every
    ISIN in the long-format `prices` frame and assemble a wide DataFrame
    (index = date, columns = isin).

    `prices` columns required: isin, date, close. Each ISIN is sorted by date so
    integer-position lookbacks are calendar-gap safe (signals.py contract).
    """
    cols: dict[str, pd.Series] = {}
    for isin, group in prices.groupby("isin"):
        g = group.sort_values("date")
        close = pd.Series(
            g["close"].to_numpy(dtype=float),
            index=pd.to_datetime(g["date"].to_numpy()),
        )
        cols[str(isin)] = fn(close)
    return pd.DataFrame(cols).sort_index()


# ---------------------------------------------------------------------------
# Pure factor functions (each returns wide raw values, higher = better)
# ---------------------------------------------------------------------------


def _mom_series(close: pd.Series, lookback_days: int, skip_days: int) -> pd.Series:
    """ret over `lookback_days` skipping the last `skip_days` (integer positions)."""
    total = lookback_days + skip_days
    vals = _momentum_12_1(close.to_numpy(dtype=float), skip_days, total)
    return pd.Series(vals, index=close.index)


def momentum(prices: pd.DataFrame, lookback_days: int, skip_days: int) -> pd.DataFrame:
    """Cross-name momentum: ret(lookback skip skip_days). Higher = better."""
    return _per_isin_wide(prices, lambda c: _mom_series(c, lookback_days, skip_days))


def low_volatility(prices: pd.DataFrame, lookback_days: int) -> pd.DataFrame:
    """
    Negated annualised volatility (daily pct_change stdev × √252) over the window.
    Negated so HIGHER = lower vol = better; order-equivalent to inverse-vol but
    singularity-free. Same vol formula as signals.precompute_signals.
    """
    min_p = max(lookback_days // 2, 1)

    def _fn(close: pd.Series) -> pd.Series:
        vol = (
            close.pct_change()
            .rolling(lookback_days, min_periods=min_p)
            .std()
            .mul(math.sqrt(252))
        )
        return -vol

    return _per_isin_wide(prices, _fn)


def trend_quality(prices: pd.DataFrame, lookback_days: int) -> pd.DataFrame:
    """
    Fraction of up-days over the window (path smoothness proxy, prereg §4).
    Higher = steadier ascent = better. Days with undefined return are excluded
    from the fraction rather than counted as down-days.
    """
    min_p = max(lookback_days // 2, 1)

    def _fn(close: pd.Series) -> pd.Series:
        ret = close.pct_change()
        up = ret.gt(0.0).where(ret.notna())  # NaN where return undefined
        return up.rolling(lookback_days, min_periods=min_p).mean()

    return _per_isin_wide(prices, _fn)


def short_term_reversal(prices: pd.DataFrame, lookback_days: int) -> pd.DataFrame:
    """
    Negated ~1-month return (prereg §4). Higher = fell more recently = better
    (we expect a bounce / avoid chasing recent over-extension).
    """
    return _per_isin_wide(prices, lambda c: -_mom_series(c, lookback_days, skip_days=0))


# ---------------------------------------------------------------------------
# Dispatcher + composite blend (prereg §5)
# ---------------------------------------------------------------------------


def compute_factor(name: str, prices: pd.DataFrame, cfg: V3Config) -> pd.DataFrame:
    """Compute one named factor's raw wide frame using cfg's lookback params."""
    if name == "mom_12_1":
        return momentum(prices, cfg.momentum_lookback_days, cfg.momentum_skip_days)
    if name == "mom_6_1":
        return momentum(prices, cfg.mom6_lookback_days, cfg.mom6_skip_days)
    if name == "low_vol":
        return low_volatility(prices, cfg.vol_lookback_days)
    if name == "trend_quality":
        return trend_quality(prices, cfg.trend_quality_lookback_days)
    if name == "reversal":
        return short_term_reversal(prices, cfg.reversal_lookback_days)
    raise ValueError(f"unknown factor: {name!r} (known: {sorted(FACTOR_NAMES)})")


def _resolve_weights(
    active: list[str],
    factor_weights: dict[str, float] | None,
) -> list[float]:
    """Equal-weight by default; otherwise normalise the pre-registered weights."""
    if factor_weights is None:
        return [1.0 / len(active)] * len(active)
    # Fail loud if a weight is missing for an active factor (Rule 12).
    raw = [factor_weights[name] for name in active]
    total = sum(raw)
    if total <= 0.0:
        raise ValueError("factor_weights must sum to a positive number")
    return [w / total for w in raw]


def composite_rank(prices: pd.DataFrame, cfg: V3Config) -> pd.DataFrame:
    """
    Equal-weight rank-blended composite (prereg §5):

      composite(name, day) = Σ_w  percentile_rank_cross_section(factor_value)

    Each active factor is percentile-ranked *cross-sectionally* (across names on
    each day, `rank(axis=1, pct=True)`), then weight-averaged. A name is NaN on a
    day if ANY active factor is NaN there (require-all-present, deterministic).
    Higher composite = better. Rank-blend (not z-blend) makes the score immune to
    a single factor's value outliers — an extreme value just maps to rank 1.0.

    If `cfg.rank_smoothing_months > 0`, the composite is smoothed with an
    N-month rolling mean (N × 21 trading days) so names don't oscillate across
    the rank boundary on one noisy month (prereg §3.1).
    """
    active = list(cfg.active_factors)
    if not active:
        raise ValueError("V3Config.active_factors is empty")

    weights = _resolve_weights(active, cfg.factor_weights)

    composite: pd.DataFrame | None = None
    for name, w in zip(active, weights):
        raw = compute_factor(name, prices, cfg)
        ranked = raw.rank(axis=1, pct=True) * w
        # `+` aligns on index/columns and propagates NaN (require-all-present).
        composite = ranked if composite is None else composite + ranked

    assert composite is not None  # active is non-empty

    months = cfg.rank_smoothing_months
    if months and months > 0:
        window = months * _TRADING_DAYS_PER_MONTH
        composite = composite.rolling(window, min_periods=1).mean()

    return composite
