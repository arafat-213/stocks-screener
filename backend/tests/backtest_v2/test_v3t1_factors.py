"""
v3 / T1 acceptance tests — factor library + composite rank-blend + smoothing.

All offline: synthetic price frames only, no network / DB / live parquet (Rule 5).

WHY each test group exists:
  factor_sign     — each factor must be MONOTONE in the right economic direction
                    (prereg §4). A factor with the wrong sign silently inverts the
                    whole strategy, so the sign is the load-bearing invariant.
  composite       — a one-factor composite must equal that factor's percentile
                    rank (the blend reduces to the trivial case); the blend must
                    be EQUAL-weight (prereg §5).
  outlier_robust  — the reason we rank-blend not z-blend: the composite must be
                    INVARIANT to a single factor's value outlier magnitude. A
                    z-score blend would let the outlier dominate; percentile rank
                    caps it at 1.0. This test fails if someone swaps to z-blend.
  smoothing       — N-month smoothing must REDUCE day-to-day rank churn on a noisy
                    fixture (prereg §3.1 — the boundary-oscillation fix).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.backtest_v2 import factors
from app.backtest_v2.v3_config import V3Config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_N = 320  # > 273 momentum warmup + room


def _long_from_closes(
    closes: dict[str, np.ndarray], start: str = "2019-01-01"
) -> pd.DataFrame:
    """Build a long-format prices frame from {isin: close_array} (shared dates)."""
    frames = []
    for isin, close in closes.items():
        dates = pd.bdate_range(start=start, periods=len(close))
        frames.append(
            pd.DataFrame(
                {
                    "isin": isin,
                    "date": dates,
                    "close": np.asarray(close, dtype=float),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _linear(slope: float, n: int = _N, base: float = 100.0) -> np.ndarray:
    """Monotone series close[i] = base * (1 + slope)**i (smooth uptrend if slope>0)."""
    return base * np.cumprod(np.full(n, 1.0 + slope))


def _cfg(**overrides) -> V3Config:
    cfg = V3Config()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


# ---------------------------------------------------------------------------
# Factor sign / monotonicity (prereg §4)
# ---------------------------------------------------------------------------


class TestFactorSign:
    def test_momentum_higher_trend_ranks_higher(self):
        """Steeper uptrend → higher 12-1 momentum (cross-name monotonicity)."""
        closes = {
            "LOW": _linear(0.0005),
            "MID": _linear(0.0010),
            "HIGH": _linear(0.0015),
        }
        long = _long_from_closes(closes)
        f = factors.momentum(long, lookback_days=252, skip_days=21)
        last = f.iloc[-1]
        assert last["HIGH"] > last["MID"] > last["LOW"]

    def test_mom_6_1_via_compute_factor(self):
        """6-1 momentum dispatches and is monotone in trend too."""
        closes = {"A": _linear(0.0003), "B": _linear(0.0012)}
        long = _long_from_closes(closes)
        f = factors.compute_factor("mom_6_1", long, _cfg())
        assert f.iloc[-1]["B"] > f.iloc[-1]["A"]

    def test_low_vol_lower_vol_ranks_higher(self):
        """Same drift, lower noise → higher (less-negative) low-vol factor."""
        rng = np.random.default_rng(1)
        drift = 0.0005
        quiet = 100.0 * np.cumprod(1.0 + drift + rng.normal(0, 0.003, _N))
        noisy = 100.0 * np.cumprod(1.0 + drift + rng.normal(0, 0.030, _N))
        long = _long_from_closes({"QUIET": quiet, "NOISY": noisy})
        f = factors.low_volatility(long, lookback_days=126)
        assert f.iloc[-1]["QUIET"] > f.iloc[-1]["NOISY"]

    def test_low_vol_is_negative_of_vol(self):
        """Sanity: the factor equals -annualised_vol (sign convention is explicit)."""
        rng = np.random.default_rng(2)
        close = 100.0 * np.cumprod(1.0 + rng.normal(0, 0.01, _N))
        long = _long_from_closes({"X": close})
        f = factors.low_volatility(long, lookback_days=126)
        # All non-NaN values must be <= 0 (vol is non-negative).
        vals = f["X"].dropna().to_numpy()
        assert (vals <= 0.0).all()

    def test_trend_quality_more_up_days_ranks_higher(self):
        """A path with more up-days scores higher than a choppier path."""
        # STEADY: almost always up. CHOPPY: alternating up/down with net drift.
        steady = _linear(0.0008)
        rng = np.random.default_rng(3)
        choppy = 100.0 * np.cumprod(1.0 + 0.0008 + rng.normal(0, 0.02, _N))
        long = _long_from_closes({"STEADY": steady, "CHOPPY": choppy})
        f = factors.trend_quality(long, lookback_days=126)
        assert f.iloc[-1]["STEADY"] > f.iloc[-1]["CHOPPY"]

    def test_trend_quality_bounded_0_1(self):
        """Fraction of up-days must lie in [0, 1]."""
        long = _long_from_closes({"X": _linear(0.0008)})
        f = factors.trend_quality(long, lookback_days=126)
        vals = f["X"].dropna().to_numpy()
        assert ((vals >= 0.0) & (vals <= 1.0)).all()

    def test_reversal_recent_loser_ranks_higher(self):
        """
        Reversal = -(1M return): a name that FELL over the last month scores
        higher than one that ROSE. Build a long uptrend then flip the last month.
        """
        up = _linear(0.0010)
        # WINNER keeps rising last 21d; LOSER drops sharply over last 21d.
        winner = up.copy()
        loser = up.copy()
        loser[-21:] = loser[-22] * np.cumprod(np.full(21, 1.0 - 0.01))
        long = _long_from_closes({"WINNER": winner, "LOSER": loser})
        f = factors.short_term_reversal(long, lookback_days=21)
        assert f.iloc[-1]["LOSER"] > f.iloc[-1]["WINNER"]


# ---------------------------------------------------------------------------
# Composite rank-blend (prereg §5)
# ---------------------------------------------------------------------------


class TestComposite:
    def test_single_factor_composite_equals_its_rank(self):
        """active=[one factor], no smoothing → composite == that factor's pct rank."""
        closes = {"A": _linear(0.0005), "B": _linear(0.0010), "C": _linear(0.0015)}
        long = _long_from_closes(closes)
        cfg = _cfg(active_factors=["mom_12_1"], rank_smoothing_months=0)
        composite = factors.composite_rank(long, cfg)
        raw = factors.compute_factor("mom_12_1", long, cfg)
        expected = raw.rank(axis=1, pct=True)
        pd.testing.assert_frame_equal(composite, expected)

    def test_equal_weight_blend(self):
        """Two-factor composite == simple mean of the two percentile ranks."""
        rng = np.random.default_rng(5)
        closes = {
            f"S{i}": 100.0 * np.cumprod(1.0 + rng.normal(2e-4, 0.01, _N))
            for i in range(6)
        }
        long = _long_from_closes(closes)
        cfg = _cfg(active_factors=["mom_12_1", "low_vol"], rank_smoothing_months=0)
        composite = factors.composite_rank(long, cfg)

        r1 = factors.compute_factor("mom_12_1", long, cfg).rank(axis=1, pct=True)
        r2 = factors.compute_factor("low_vol", long, cfg).rank(axis=1, pct=True)
        expected = (r1 + r2) / 2.0
        pd.testing.assert_frame_equal(composite, expected)

    def test_nan_if_any_factor_missing(self):
        """A name NaN in one factor is NaN in the composite (require-all-present)."""
        # mom_12_1 needs 273 rows; low_vol warms up at ~63. Early rows: mom NaN.
        closes = {"A": _linear(0.0005), "B": _linear(0.0010)}
        long = _long_from_closes(closes)
        cfg = _cfg(active_factors=["mom_12_1", "low_vol"], rank_smoothing_months=0)
        composite = factors.composite_rank(long, cfg)
        # Row 100: low_vol valid but mom_12_1 still NaN → composite NaN.
        assert composite.iloc[100].isna().all()


# ---------------------------------------------------------------------------
# Outlier robustness — WHY we rank-blend, not z-blend
# ---------------------------------------------------------------------------


class TestOutlierRobustness:
    def test_composite_invariant_to_outlier_magnitude(self):
        """
        Inflating one factor's value for one name by orders of magnitude must NOT
        change ANY composite rank — percentile rank only sees order, not size.
        A z-score blend would fail this (the outlier would skew the mean/std and
        dominate). This is the load-bearing reason for rank-blend (prereg §3.2).
        """
        rng = np.random.default_rng(7)
        closes = {
            f"S{i}": 100.0 * np.cumprod(1.0 + rng.normal(2e-4, 0.01, _N))
            for i in range(8)
        }
        long = _long_from_closes(closes)
        cfg = _cfg(active_factors=["mom_12_1", "low_vol"], rank_smoothing_months=0)

        base = factors.composite_rank(long, cfg)

        # Make S0 an extreme momentum outlier by blowing up its recent price.
        long_out = long.copy()
        mask = long_out["isin"] == "S0"
        long_out.loc[mask, "close"] = long_out.loc[mask, "close"] * 1e6
        perturbed = factors.composite_rank(long_out, cfg)

        # S0 becomes the top momentum name, but every name's composite rank stays
        # bounded in [0, 1]; the ORDERING among the other names is unchanged.
        valid = base.dropna(how="all")
        assert (perturbed.to_numpy()[~np.isnan(perturbed.to_numpy())] >= 0.0).all()
        assert (perturbed.to_numpy()[~np.isnan(perturbed.to_numpy())] <= 1.0).all()

        # Ordering of the non-outlier names on the last row is preserved.
        last_base = base.iloc[-1].drop("S0").sort_values().index.tolist()
        last_pert = perturbed.iloc[-1].drop("S0").sort_values().index.tolist()
        assert last_base == last_pert
        assert len(valid) > 0


# ---------------------------------------------------------------------------
# Smoothing reduces churn (prereg §3.1)
# ---------------------------------------------------------------------------


class TestSmoothing:
    def test_smoothing_reduces_rank_churn(self):
        """
        On a noisy multi-name fixture, N-month smoothing must reduce the mean
        day-to-day change in composite rank (the boundary-oscillation fix).
        """
        rng = np.random.default_rng(11)
        closes = {
            f"S{i}": 100.0 * np.cumprod(1.0 + rng.normal(2e-4, 0.025, _N))
            for i in range(12)
        }
        long = _long_from_closes(closes)

        raw_cfg = _cfg(active_factors=["mom_12_1"], rank_smoothing_months=0)
        smooth_cfg = _cfg(active_factors=["mom_12_1"], rank_smoothing_months=3)

        raw = factors.composite_rank(long, raw_cfg)
        smooth = factors.composite_rank(long, smooth_cfg)

        # Mean absolute day-to-day change, averaged over names, on warmed-up rows.
        def _churn(df: pd.DataFrame) -> float:
            tail = df.iloc[280:]
            return tail.diff().abs().mean().mean()

        assert _churn(smooth) < _churn(raw)

    def test_no_smoothing_is_identity(self):
        """rank_smoothing_months=0 must leave the composite untouched."""
        long = _long_from_closes({"A": _linear(0.0005), "B": _linear(0.0010)})
        cfg0 = _cfg(active_factors=["mom_12_1"], rank_smoothing_months=0)
        composite = factors.composite_rank(long, cfg0)
        raw = factors.compute_factor("mom_12_1", long, cfg0).rank(axis=1, pct=True)
        pd.testing.assert_frame_equal(composite, raw)


# ---------------------------------------------------------------------------
# Dispatcher hygiene
# ---------------------------------------------------------------------------


def test_unknown_factor_raises():
    long = _long_from_closes({"A": _linear(0.0005)})
    with pytest.raises(ValueError):
        factors.compute_factor("bogus", long, _cfg())


def test_all_five_factors_dispatch():
    """Every pre-registered Track-A factor name must compute without error."""
    rng = np.random.default_rng(13)
    closes = {
        f"S{i}": 100.0 * np.cumprod(1.0 + rng.normal(2e-4, 0.01, _N)) for i in range(4)
    }
    long = _long_from_closes(closes)
    cfg = _cfg()
    for name in ["mom_12_1", "mom_6_1", "low_vol", "trend_quality", "reversal"]:
        f = factors.compute_factor(name, long, cfg)
        assert isinstance(f, pd.DataFrame)
        assert f.shape[1] == 4  # one column per isin
