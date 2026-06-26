"""RO0 unit tests (v5/00 §12) — the overlay simulator + comparators + defensive loader.

Synthetic only — NO live API (CLAUDE.md §5), NO DISCOVERY/FINAL_OOS return measured.
Each test encodes WHY the mechanic matters (Rule 9): causality (no look-ahead), exact
switch cost on a known Δexposure, correct ``w*``, defensive-leg accrual, fail-loud gaps.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.backtest_v2.costs import CostConfig, fill_cost
from app.regime_overlay import overlay as ov
from app.regime_overlay import short_rate as sr

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


class _StubRegime:
    """Minimal RegimeScore stand-in: explicit per-day fraction + integer score."""

    def __init__(self, frac: dict, score: dict | None = None) -> None:
        self._f = {pd.Timestamp(k): v for k, v in frac.items()}
        self._s = {pd.Timestamp(k): v for k, v in (score or {}).items()}

    def deployable_fraction(self, day) -> float:
        return float(self._f.get(pd.Timestamp(day), 0.0))

    def score(self, day) -> int:
        return int(self._s.get(pd.Timestamp(day), 0))


def _cal(n: int):
    return list(pd.bdate_range("2020-01-01", periods=n))


def _flat(cal, value=100.0):
    return pd.Series(value, index=pd.DatetimeIndex(cal), dtype=float)


# ---------------------------------------------------------------------------
# Defensive-asset loader (short_rate.py) — injectable fetch, cache, fail-loud
# ---------------------------------------------------------------------------


def _price_rows(dates_vals):
    return [
        {"HistoricalDate": d, "CLOSE": str(v), "OPEN": "-", "HIGH": "-", "LOW": "-"}
        for d, v in dates_vals
    ]


def test_short_rate_loader_parses_caches_and_fails_loud(tmp_path):
    calls = {"n": 0}

    def stub(index_name, start, end):
        calls["n"] += 1
        assert index_name == sr.DEFENSIVE_INDEX_NAME
        return _price_rows([("01 Jan 2020", 1000.0), ("02 Jan 2020", 1000.5)])

    s = sr.load_defensive_index(
        "2020-01-01", "2020-01-02", cache_dir=tmp_path, _fetch_fn=stub
    )
    assert list(s.values) == [1000.0, 1000.5]
    assert s.index[0] == pd.Timestamp("2020-01-01")
    # Second call must hit the parquet cache — stub NOT called again.
    s2 = sr.load_defensive_index(
        "2020-01-01", "2020-01-02", cache_dir=tmp_path, _fetch_fn=stub
    )
    assert calls["n"] == 1
    pd.testing.assert_series_equal(s, s2)

    # Empty fetch must raise, never poison the cache (mirrors benchmark.load_tri).
    with pytest.raises(ValueError, match="zero rows"):
        sr.load_defensive_index(
            "2021-01-01", "2021-01-02", cache_dir=tmp_path, _fetch_fn=lambda *a: []
        )


# ---------------------------------------------------------------------------
# Fraction-path builders
# ---------------------------------------------------------------------------


def test_overlay_fraction_reads_frozen_buckets():
    cal = _cal(3)
    reg = _StubRegime({cal[0]: 0.0, cal[1]: 0.5, cal[2]: 1.0})
    f = ov.overlay_fraction(reg, cal)
    assert list(f.values) == [0.0, 0.5, 1.0]


def test_linear_ramp_is_score_over_five():
    cal = _cal(3)
    reg = _StubRegime(frac={}, score={cal[0]: 0, cal[1]: 3, cal[2]: 5})
    f = ov.linear_ramp_fraction(reg, cal)
    assert list(f.values) == [0.0, 0.6, 1.0]


def test_faber_fraction_crosses_dma():
    # Price below its own SMA early, climbs above it later.
    cal = _cal(260)
    idx = pd.DatetimeIndex(cal)
    # Flat then a sustained rise — after warmup the close clears the trailing SMA.
    vals = np.concatenate([np.full(200, 100.0), np.linspace(100.0, 140.0, 60)])
    price = pd.Series(vals, index=idx)
    f = ov.faber_fraction(price, cal, window=200)
    assert f.iloc[50] == 0.0  # warmup: DMA NaN → conservative 0
    assert f.iloc[-1] == 1.0  # well above the rising trailing SMA


# ---------------------------------------------------------------------------
# Simulator — causality, costs, accrual, w*
# ---------------------------------------------------------------------------


def test_causality_signal_is_lagged_one_day():
    # Signal flips ON at the close of day index 3; the trade must fire on day 4.
    cal = _cal(7)
    frac = pd.Series(
        [0, 0, 0, 1.0, 1.0, 1.0, 1.0], index=pd.DatetimeIndex(cal), dtype=float
    )
    res = ov.simulate(frac, _flat(cal), _flat(cal), CostConfig.base())
    a = res.applied_fraction
    assert a.iloc[3] == 0.0  # still flat ON the signal day (no look-ahead)
    assert a.iloc[4] == 1.0  # deployed the NEXT day
    assert res.n_rebalances == 1


def test_exact_switch_cost_on_known_delta():
    # 2-day flat world; deploy 0→100% on day 1. Cost must equal the project model
    # on the full traded notional (= starting capital).
    cal = _cal(2)
    cap = 350_000.0
    frac = pd.Series([1.0, 1.0], index=pd.DatetimeIndex(cal), dtype=float)
    cfg = CostConfig.base()
    res = ov.simulate(
        frac, _flat(cal), _flat(cal), cfg, ov.OverlayConfig(starting_capital=cap)
    )

    expected_cost = fill_cost("buy", cap, 1.0, 0.0, cfg) + cap * cfg.base_slippage_pct
    assert res.total_switch_cost == pytest.approx(expected_cost)
    # NAV day1 = (cap − cost) grown one flat day, net the ETF daily expense.
    etf_daily = ov.OverlayConfig().etf_expense_annual / 252
    assert res.nav.iloc[-1] == pytest.approx((cap - expected_cost) * (1 - etf_daily))


def test_defensive_leg_accrues_short_rate_when_undeployed():
    # f=0 throughout ⇒ never touch equity; NAV tracks the defensive index growth.
    cal = _cal(5)
    cap = 100_000.0
    frac = _flat(cal, 0.0)
    # Defensive rises 0.02%/day (≈5%/yr overnight); equity TRI irrelevant (never held).
    defensive = pd.Series(100.0 * (1.0002 ** np.arange(5)), index=pd.DatetimeIndex(cal))
    res = ov.simulate(
        frac,
        _flat(cal, 50.0),
        defensive,
        CostConfig.base(),
        ov.OverlayConfig(starting_capital=cap),
    )
    assert res.n_rebalances == 0
    liq_daily = ov.OverlayConfig().liquid_expense_annual / 252
    # 4 growth steps from day0→day4.
    expected = cap * (1.0002**4) * (1 - liq_daily) ** 4
    assert res.nav.iloc[-1] == pytest.approx(expected, rel=1e-9)


def test_w_star_is_mean_applied_fraction():
    cal = _cal(5)
    # applied path becomes [0, 0, 0.5, 0.5, 1.0] (signal lagged): build it directly.
    frac = pd.Series([0.0, 0.5, 0.5, 1.0, 1.0], index=pd.DatetimeIndex(cal))
    res = ov.simulate(frac, _flat(cal), _flat(cal), CostConfig.base())
    assert res.realized_avg_fraction == pytest.approx(
        float(res.applied_fraction.mean())
    )


def test_full_deploy_tracks_tri():
    # f=1 constant ⇒ overlay ≈ buy-and-hold the TRI (minus entry cost + ETF expense).
    cal = _cal(30)
    idx = pd.DatetimeIndex(cal)
    tri = pd.Series(100.0 * (1.001 ** np.arange(30)), index=idx)  # +0.1%/day
    frac = _flat(cal, 1.0)
    res = ov.simulate(frac, tri, _flat(cal), CostConfig.base())
    gross = res.nav.iloc[-1] / res.nav.iloc[0]
    tri_gross = tri.iloc[-1] / tri.iloc[0]
    # Within a few percent of raw TRI (entry cost + expense are the only gaps).
    assert gross == pytest.approx(tri_gross, rel=0.02)
    assert gross < tri_gross  # costs/expense strictly drag


def test_static_monthly_rebalances_each_month():
    # Constant w*=0.5 with a rising TRI ⇒ drift ⇒ a trade on the first day + each new month.
    cal = list(pd.bdate_range("2020-01-01", "2020-03-31"))  # spans Jan, Feb, Mar
    idx = pd.DatetimeIndex(cal)
    tri = pd.Series(100.0 * (1.002 ** np.arange(len(cal))), index=idx)
    frac = ov.static_fraction(0.5, cal)
    res = ov.simulate(frac, tri, _flat(cal), CostConfig.base(), rebalance="monthly")
    # First signal day is in Jan; then Feb + Mar month-turns ⇒ 3 rebalances.
    assert res.n_rebalances == 3


def test_metrics_from_nav_drawdown_and_calmar():
    # Up 1yr then a clean 20% dip and partial recovery.
    idx = pd.bdate_range("2020-01-01", periods=300)
    up = np.linspace(100.0, 200.0, 200)
    down = np.linspace(200.0, 160.0, 100)  # 20% drawdown off the 200 peak
    nav = pd.Series(np.concatenate([up, down]), index=idx)
    m = ov.metrics_from_nav(nav)
    assert m["max_dd"] == pytest.approx(0.20, abs=1e-6)
    assert m["cagr"] > 0
    assert m["calmar"] == pytest.approx(m["cagr"] / m["max_dd"])

    mono = pd.Series(
        np.linspace(100.0, 150.0, 260), index=pd.bdate_range("2020-01-01", periods=260)
    )
    assert ov.metrics_from_nav(mono)["max_dd"] == 0.0
    assert np.isnan(ov.metrics_from_nav(mono)["calmar"])


def test_simulate_fails_loud_on_tri_gap():
    # A hole in the authoritative equity (TRI) calendar must fail loud, not be papered
    # over. (The defensive leg is allowed to be sparser — it ffills onto this calendar.)
    cal = _cal(4)
    tri = _flat(cal)
    tri.iloc[2] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        ov.simulate(_flat(cal, 1.0), tri, _flat(cal), CostConfig.base())


def test_defensive_leg_ffills_onto_sparser_calendar():
    # Defensive index missing some trading days ⇒ ffilled onto the TRI calendar
    # (level carried, 0 accrual that day) — never a silent calendar shrink.
    cal = _cal(5)
    sparse = _flat(cal, 100.0).drop(pd.DatetimeIndex(cal)[2])  # drop one publish day
    res = ov.simulate(_flat(cal, 0.0), _flat(cal), sparse, CostConfig.base())
    assert len(res.nav) == 5  # full TRI calendar preserved, not 4
