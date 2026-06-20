"""
VT0 acceptance tests — value-tilt wiring + skew-aware §6.2 (09 VT0).

All offline: synthetic frames + injected seams, no network / DB / engine run
(VT0 forbids a backtest). WHY each group exists:

  config_guards   — value_tilt_lambda must be non-negative, and λ>0 must be a TILT
                    over a price-only base; a value factor in active_factors would
                    route through the closed Track-B co-equal blend (07) and
                    double-count value. The guard makes that mistake fail loud.
  lambda0_identity— THE load-bearing VT0 done-criterion: λ=0 reproduces the
                    pure-momentum base BYTE-FOR-BYTE, even when value frames are
                    supplied (they must be ignored). If λ=0 ever perturbs the
                    composite, the whole λ=0 control column (09 §5) is invalid.
  value_rank      — equal-weight cross-sectional percentile of the value block,
                    nanmean over present factors (a name with only E/P still
                    ranks); an all-NaN cell stays NaN (never zero-filled).
  tilt_combine    — λ>0 RE-ORDERS momentum-eligible names by value; names lacking
                    value data are neutral-filled (0.5) so the tilt never DROPS a
                    momentum name; momentum-NaN (warmup) stays NaN.
  skew_aware      — random-subset retention is deterministic under a fixed seed and
                    chooses drops WITHOUT consulting P&L (no-lookahead); the
                    median/p5 thresholds and contributor-rotation union are correct.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.backtest_v2 import skew_robustness as sk
from app.backtest_v2.signals_v3 import (
    _apply_value_tilt,
    build_value_rank,
    precompute_v3_signals,
)
from app.backtest_v2.v3_config import V3Config

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _full_frame(
    isins: list[str],
    start: str = "2017-01-02",
    n_days: int = 420,
    seed: int = 11,
) -> pd.DataFrame:
    """Full engine-column long frame for precompute_v3_signals (mirrors SU0)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    rows = []
    for k, isin in enumerate(isins):
        price = 100.0 + k  # distinct paths so cross-sectional ranks are non-degenerate
        for i, ts in enumerate(dates):
            price = max(price * (1.0 + rng.normal(0.0006, 0.015)), 0.01)
            rows.append(
                {
                    "isin": isin,
                    "symbol": isin,
                    "date": ts,
                    "open": price * 0.999,
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price,
                    "close_raw": price,
                    "close_tr": price * 1.0005**i,
                    "volume": 100_000,
                    "adv_20": 1e8,
                }
            )
    return pd.DataFrame(rows)


def _value_frames(
    isins: list[str],
    dates: list[str],
) -> dict[str, pd.DataFrame]:
    """Two raw value frames (E/P, B/P) on `dates` × `isins` with distinct values."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    ep = pd.DataFrame(
        {isin: [0.10 - 0.01 * j for _ in dates] for j, isin in enumerate(isins)},
        index=idx,
    )
    bp = pd.DataFrame(
        {isin: [0.5 + 0.1 * j for _ in dates] for j, isin in enumerate(isins)},
        index=idx,
    )
    return {"earnings_yield": ep, "book_to_price": bp}


# ---------------------------------------------------------------------------
# config_guards
# ---------------------------------------------------------------------------


def test_default_lambda_is_zero():
    assert V3Config().value_tilt_lambda == 0.0


def test_negative_lambda_fails_loud():
    with pytest.raises(ValueError, match="value_tilt_lambda must be >= 0"):
        V3Config(value_tilt_lambda=-0.1)


def test_lambda_positive_with_value_factor_in_active_fails_loud():
    # A fundamental factor in active_factors would route through the Track-B blend.
    with pytest.raises(ValueError, match="price-only momentum base"):
        V3Config(
            active_factors=["mom_12_1", "earnings_yield"],
            value_tilt_lambda=0.3,
        )


def test_lambda_positive_price_only_base_is_allowed():
    cfg = V3Config(active_factors=["mom_12_1", "low_vol"], value_tilt_lambda=0.3)
    assert cfg.value_tilt_lambda == 0.3


# ---------------------------------------------------------------------------
# lambda0_identity — the VT0 done-criterion
# ---------------------------------------------------------------------------


def test_lambda0_byte_identical_even_with_value_frames():
    isins = ["A", "B", "C", "D", "E"]
    prices = _full_frame(isins)
    base_cfg = V3Config(active_factors=["mom_12_1", "low_vol"])
    lam0_cfg = V3Config(active_factors=["mom_12_1", "low_vol"], value_tilt_lambda=0.0)
    vframes = _value_frames(isins, ["2017-06-01", "2018-01-02"])

    base = precompute_v3_signals(prices, base_cfg)
    lam0 = precompute_v3_signals(prices, lam0_cfg, value_frames=vframes)

    # λ=0 must ignore the value frames entirely → composite byte-for-byte equal.
    pd.testing.assert_frame_equal(base._composite, lam0._composite)


def test_lambda_positive_without_value_frames_fails_loud():
    isins = ["A", "B", "C"]
    prices = _full_frame(isins)
    cfg = V3Config(active_factors=["mom_12_1", "low_vol"], value_tilt_lambda=0.3)
    with pytest.raises(ValueError, match="requires value_frames"):
        precompute_v3_signals(prices, cfg)


# ---------------------------------------------------------------------------
# value_rank
# ---------------------------------------------------------------------------


def test_value_rank_equal_weight_percentile():
    idx = pd.DatetimeIndex([pd.Timestamp("2020-01-31")])
    # E/P ascending A<B<C<D ; B/P descending A>B>C>D → equal-weight ⇒ all tie at 0.5.
    ep = pd.DataFrame({"A": [1.0], "B": [2.0], "C": [3.0], "D": [4.0]}, index=idx)
    bp = pd.DataFrame({"A": [4.0], "B": [3.0], "C": [2.0], "D": [1.0]}, index=idx)
    vr = build_value_rank({"earnings_yield": ep, "book_to_price": bp})
    # rank(pct) of [1,2,3,4] = [.25,.5,.75,1]; of [4,3,2,1] = [1,.75,.5,.25];
    # mean = [.625,.625,.625,.625].
    assert np.allclose(vr.loc[idx[0]].values, 0.625)


def test_value_rank_nanmean_partial_coverage():
    idx = pd.DatetimeIndex([pd.Timestamp("2020-01-31")])
    ep = pd.DataFrame({"A": [1.0], "B": [2.0], "C": [np.nan]}, index=idx)
    bp = pd.DataFrame({"A": [np.nan], "B": [2.0], "C": [1.0]}, index=idx)
    vr = build_value_rank({"earnings_yield": ep, "book_to_price": bp})
    # A: only E/P present (rank among {1,2}=0.5) → 0.5
    # C: only B/P present (rank among {1,2}=0.5) → 0.5
    assert vr.loc[idx[0], "A"] == 0.5
    assert vr.loc[idx[0], "C"] == 0.5


def test_value_rank_all_nan_cell_stays_nan():
    idx = pd.DatetimeIndex([pd.Timestamp("2020-01-31")])
    ep = pd.DataFrame({"A": [1.0], "Z": [np.nan]}, index=idx)
    bp = pd.DataFrame({"A": [2.0], "Z": [np.nan]}, index=idx)
    vr = build_value_rank({"earnings_yield": ep, "book_to_price": bp})
    assert np.isnan(vr.loc[idx[0], "Z"])


# ---------------------------------------------------------------------------
# tilt_combine
# ---------------------------------------------------------------------------


def test_apply_tilt_lambda0_returns_same_object():
    mom = pd.DataFrame({"A": [0.3], "B": [0.7]}, index=[pd.Timestamp("2020-01-31")])
    out = _apply_value_tilt(mom, None, 0.0)
    assert out is mom


def test_apply_tilt_reorders_and_neutral_fills():
    days = pd.DatetimeIndex(pd.bdate_range("2020-01-31", periods=3))
    # momentum: A and B tie at 0.5 every day; C is momentum-NaN (warmup).
    mom = pd.DataFrame(
        {"A": [0.5, 0.5, 0.5], "B": [0.5, 0.5, 0.5], "C": [np.nan, np.nan, np.nan]},
        index=days,
    )
    # value_rank only on the first date: A cheap (0.9), B rich (0.1), D has no momentum.
    vr = pd.DataFrame({"A": [0.9], "B": [0.1]}, index=pd.DatetimeIndex([days[0]]))
    out = _apply_value_tilt(mom, vr, lam=0.5)
    # Date 0: A = 0.5 + 0.5*0.9 = 0.95 ; B = 0.5 + 0.5*0.1 = 0.55 → A now ranks above B.
    assert out.loc[days[0], "A"] == pytest.approx(0.95)
    assert out.loc[days[0], "B"] == pytest.approx(0.55)
    # Date 1: value ffilled from date 0 (sparse → carried forward).
    assert out.loc[days[1], "A"] == pytest.approx(0.95)
    # C has NaN momentum → stays NaN regardless of the tilt (warmup preserved).
    assert np.isnan(out.loc[days[0], "C"])


def test_apply_tilt_neutral_fill_for_missing_value_name():
    day = pd.DatetimeIndex([pd.Timestamp("2020-01-31")])
    mom = pd.DataFrame({"A": [0.6], "NOVAL": [0.6]}, index=day)
    vr = pd.DataFrame({"A": [1.0]}, index=day)  # NOVAL absent from value frame
    out = _apply_value_tilt(mom, vr, lam=0.4)
    # A gets the value bump; NOVAL gets the neutral 0.5 fill → not dropped.
    assert out.loc[day[0], "A"] == pytest.approx(0.6 + 0.4 * 1.0)
    assert out.loc[day[0], "NOVAL"] == pytest.approx(0.6 + 0.4 * 0.5)
    assert not np.isnan(out.loc[day[0], "NOVAL"])


# ---------------------------------------------------------------------------
# skew_aware §6.2
# ---------------------------------------------------------------------------


def _const_runner(value: float):
    """run_perturbed seam that ignores the drop set and returns a fixed Calmar."""
    return lambda drop_set: value


def test_random_subset_determinism_same_seed():
    held = [f"N{i}" for i in range(40)]
    seen: list[list[frozenset[str]]] = []

    def make_recording_runner():
        calls: list[frozenset[str]] = []
        seen.append(calls)

        def run(drop_set):
            calls.append(drop_set)
            return 0.8  # constant Calmar → retention 1.0 each draw

        return run

    r1 = sk.random_subset_retention(
        held, 1.0, make_recording_runner(), n_draws=20, seed=7
    )
    r2 = sk.random_subset_retention(
        held, 1.0, make_recording_runner(), n_draws=20, seed=7
    )
    # Identical seed ⇒ identical sequence of drop sets ⇒ identical retentions.
    assert seen[0] == seen[1]
    assert r1.retentions == r2.retentions


def test_random_subset_different_seed_changes_draws():
    held = [f"N{i}" for i in range(40)]
    drops_a: list[frozenset[str]] = []
    drops_b: list[frozenset[str]] = []
    sk.random_subset_retention(
        held, 1.0, lambda d: (drops_a.append(d) or 0.8), n_draws=20, seed=1
    )
    sk.random_subset_retention(
        held, 1.0, lambda d: (drops_b.append(d) or 0.8), n_draws=20, seed=2
    )
    assert drops_a != drops_b  # different seed ⇒ different random subsets


def test_random_subset_no_lookahead_drops_independent_of_pnl():
    # If drops were chosen by P&L, the dropped union would be a fixed small set.
    # Random drops over 200 draws of 10/40 should cover (nearly) ALL held names.
    held = [f"N{i}" for i in range(40)]
    dropped_union: set[str] = set()

    def run(drop_set):
        dropped_union.update(drop_set)
        return 0.9

    sk.random_subset_retention(held, 1.0, run, n_draws=200, seed=3)
    assert len(dropped_union) == 40  # every name eventually dropped → not P&L-driven


def test_random_subset_median_p5_thresholds():
    held = [f"N{i}" for i in range(40)]
    # Constant retention 0.6: median=0.6 < 0.70 ⇒ FAIL even though p5 (0.6) > 0.50.
    r = sk.random_subset_retention(held, 1.0, _const_runner(0.6), n_draws=50, seed=5)
    assert r.median_retention == pytest.approx(0.6)
    assert not r.passed
    # Constant retention 0.8: median=p5=0.8 ⇒ PASS both bars.
    r2 = sk.random_subset_retention(held, 1.0, _const_runner(0.8), n_draws=50, seed=5)
    assert r2.passed


def test_random_subset_nonpositive_base_fails_loud():
    held = [f"N{i}" for i in range(40)]
    with pytest.raises(ValueError, match="positive base Calmar"):
        sk.random_subset_retention(held, 0.0, _const_runner(0.8))
    with pytest.raises(ValueError, match="positive base Calmar"):
        sk.random_subset_retention(held, float("nan"), _const_runner(0.8))


def test_random_subset_too_few_names_fails_loud():
    with pytest.raises(ValueError, match="cannot draw subsets"):
        sk.random_subset_retention(["A", "B"], 1.0, _const_runner(0.8), drop_k=10)


def test_contributor_rotation_union_and_threshold():
    per_year = {
        2018: [f"S{i}" for i in range(10)],
        2019: [f"S{i}" for i in range(5, 15)],  # 5 overlap, 5 new
        2020: [f"S{i}" for i in range(15, 25)],  # 10 new
    }
    res = sk.contributor_rotation(per_year, min_distinct=25)
    assert res.n_distinct == 25
    assert res.passed
    # Same names every year ⇒ only 10 distinct ⇒ FAIL (no rotation).
    static = {y: [f"S{i}" for i in range(10)] for y in (2018, 2019, 2020)}
    res2 = sk.contributor_rotation(static, min_distinct=25)
    assert res2.n_distinct == 10
    assert not res2.passed


def test_skew_aware_combined_requires_both():
    held = [f"N{i}" for i in range(40)]
    rotating = {y: [f"S{i + 10 * y}" for i in range(10)] for y in range(3)}
    # random-subset PASS (0.8) + rotation PASS (30 distinct) ⇒ overall PASS.
    res = sk.skew_aware_universe_perturbation(
        held, 1.0, _const_runner(0.8), rotating, n_draws=30
    )
    assert res.passed
    # random-subset FAIL (0.4) drags the combined verdict down even if rotation passes.
    res2 = sk.skew_aware_universe_perturbation(
        held, 1.0, _const_runner(0.4), rotating, n_draws=30
    )
    assert not res2.passed
    assert res2.rotation.passed
