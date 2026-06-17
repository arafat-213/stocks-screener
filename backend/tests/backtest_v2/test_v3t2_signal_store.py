"""
v3 / T2 acceptance tests — composite signal store through the engine seam.

All offline: synthetic price frames only, no network / DB / live parquet (Rule 5).

WHY each test group exists:
  engine_seam   — the multi-factor signal must run through the UNCHANGED v2 engine
                  via the `signal_store` param (01 §What-this-reuses). If the engine
                  needed editing for the ranker, the pluggable-seam claim is false.
  parity        — THE load-bearing test (prereg Erratum T1→T2). With momentum the
                  only active factor, the v3 store must select and ORDER exactly the
                  names a raw-momentum-driven v2 reference ranker would — NOT the
                  vol-adjusted `mom/vol` candidate. The composite score is a
                  percentile (a monotone transform of raw momentum), so the ranker
                  scores differ but the ORDER the engine consumes must be identical.
  gate          — the absolute-momentum filter (mom>0) must apply ONLY while
                  momentum is active; a non-momentum composite must not inherit it
                  (prereg Erratum). Eligibility otherwise matches v2's gate.
  determinism   — same config + data → identical selection (no hidden state).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.engine import EngineResult, _month_end_dates, run
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import precompute_v3_signals
from app.backtest_v2.v3_config import V3Config

# ---------------------------------------------------------------------------
# Synthetic data builders
# ---------------------------------------------------------------------------


def _make_prices(
    isins: list[str],
    start: str = "2021-01-04",
    n_days: int = 420,
    seed: int = 7,
    base_price: float = 100.0,
    drift: float = 0.0006,
    vol: float = 0.015,
) -> pd.DataFrame:
    """
    Long-format prices frame with all engine-required columns
    (symbol, open, close, close_tr, adv_20). adv_20 fixed at ₹10cr so the
    liquidity floor never gates anything out — isolating the momentum gate.
    n_days > 273 so the 12-1 momentum warms up before the late rebalances.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    rows = []
    for k, isin in enumerate(isins):
        # Give each name a distinct drift so momentum ordering is unambiguous
        # (no ties) — makes the parity equality exact rather than tie-fragile.
        name_drift = drift + k * 0.0002
        price = base_price
        series = []
        for _ in dates:
            price = max(price * (1.0 + rng.normal(name_drift, vol)), 0.01)
            series.append(price)
        for i, (d, p) in enumerate(zip(dates, series)):
            rows.append(
                {
                    "isin": isin,
                    "symbol": isin,
                    "date": d,
                    "open": p * rng.uniform(0.995, 1.005),
                    "high": p * 1.01,
                    "low": p * 0.99,
                    "close": p,
                    "close_tr": p * 1.0005**i,
                    "volume": 100_000,
                    "adv_20": 1e8,  # ₹10 crore — always liquid
                }
            )
    return pd.DataFrame(rows)


def _v3_cfg(**overrides) -> V3Config:
    base = dict(
        target_positions=3,
        sell_rank_buffer=5,
        liquidity_floor_cr=1.0,
        vol_lookback_days=60,
        use_regime_overlay=False,
        catastrophic_stop_pct=25.0,
    )
    base.update(overrides)
    cfg = V3Config()
    for k, v in base.items():
        setattr(cfg, k, v)
    return cfg


def _engine_cfg(cfg: V3Config) -> MomentumConfig:
    """The MomentumConfig the engine consumes for selection/sizing (T2: monthly)."""
    return MomentumConfig(
        target_positions=cfg.target_positions,
        sell_rank_buffer=cfg.sell_rank_buffer,
        liquidity_floor_cr=cfg.liquidity_floor_cr,
        momentum_lookback_days=cfg.momentum_lookback_days,
        momentum_skip_days=cfg.momentum_skip_days,
        vol_lookback_days=cfg.vol_lookback_days,
        max_position_pct=cfg.max_position_pct,
        starting_capital=cfg.starting_capital,
        use_regime_overlay=cfg.use_regime_overlay,
        catastrophic_stop_pct=cfg.catastrophic_stop_pct,
        rebalance="monthly",
    )


def _last_rebalance_day(prices: pd.DataFrame) -> pd.Timestamp:
    """The latest month-end trading day — warmed up, so the gate has real names."""
    cal = sorted(pd.to_datetime(prices["date"].unique()))
    return max(_month_end_dates(cal))


def _raw_momentum_v2_reference(
    v2_store, day: pd.Timestamp, universe: list[str]
) -> list[str]:
    """
    The prereg Erratum (T1→T2) parity target: a v2 engine driven by RAW
    momentum_12_1 (NOT the deployed `mom/vol` candidate). Eligibility is v2's own
    entry_gate; ordering is by the raw 12-1 momentum value descending. Returns the
    ordered ISIN list — what the engine actually consumes for top-N selection.
    """
    scored = [
        (isin, v2_store._get_row(day, isin)["momentum_12_1"])
        for isin in universe
        if v2_store.entry_gate(day, isin)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [isin for isin, _ in scored]


# ---------------------------------------------------------------------------
# Engine seam — runs through the UNCHANGED engine via signal_store
# ---------------------------------------------------------------------------


class TestEngineSeam:
    def test_engine_runs_with_v3_store_no_engine_edit(self):
        """End-to-end run with the composite store passed as `signal_store`."""
        isins = [f"ISIN{i:02d}" for i in range(8)]
        prices = _make_prices(isins)
        cfg = _v3_cfg()
        store = precompute_v3_signals(prices, cfg)

        result = run(prices, _engine_cfg(cfg), signal_store=store)

        assert isinstance(result, EngineResult)
        assert len(result.snapshots) > 0
        # The store actually drove selection: at least one rebalance executed fills.
        assert len(result.rebalance_dates_used) > 0
        assert len(result.fills_log) > 0

    def test_store_exposes_engine_interface(self):
        """The store must answer the exact two calls the engine makes."""
        prices = _make_prices([f"ISIN{i:02d}" for i in range(4)])
        store = precompute_v3_signals(prices, _v3_cfg())
        day = _last_rebalance_day(prices)
        universe = [f"ISIN{i:02d}" for i in range(4)]

        assert isinstance(store.entry_gate(day, "ISIN00"), bool)
        ranked = store.eligible_ranked(day, universe)
        assert isinstance(ranked, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in ranked)


# ---------------------------------------------------------------------------
# Parity — momentum-only composite == raw-momentum v2 reference (Erratum T1→T2)
# ---------------------------------------------------------------------------


class TestRawMomentumParity:
    def test_floor_ordering_matches_raw_momentum_reference(self):
        """
        Momentum-only v3 floor must produce the SAME ordered eligible list as a
        raw-momentum v2 reference ranker (prereg Erratum T1→T2) — NOT the
        vol-adjusted `mom/vol` candidate. The composite percentile is a monotone
        transform of raw momentum, so the order is identical though scores differ.
        """
        isins = [f"ISIN{i:02d}" for i in range(10)]
        prices = _make_prices(isins)
        cfg = _v3_cfg()  # floor: active_factors=["mom_12_1"]

        v3_store = precompute_v3_signals(prices, cfg)
        v2_store = precompute_signals(prices, _engine_cfg(cfg))

        day = _last_rebalance_day(prices)
        v3_order = [isin for isin, _ in v3_store.eligible_ranked(day, isins)]
        ref_order = _raw_momentum_v2_reference(v2_store, day, isins)

        assert v3_order == ref_order
        assert len(v3_order) > 0  # the fixture actually exercises the gate

    def test_floor_eligibility_matches_v2_gate(self):
        """
        With momentum active, the v3 gate is byte-identical to v2's gate (same
        close>EMA200, adv floor, mom>0 inputs reused verbatim). The set of
        eligible names must match on every warmed-up rebalance day.
        """
        isins = [f"ISIN{i:02d}" for i in range(10)]
        prices = _make_prices(isins)
        cfg = _v3_cfg()
        v3_store = precompute_v3_signals(prices, cfg)
        v2_store = precompute_signals(prices, _engine_cfg(cfg))

        cal = sorted(pd.to_datetime(prices["date"].unique()))
        for day in sorted(_month_end_dates(cal))[-3:]:
            v3_elig = {i for i in isins if v3_store.entry_gate(day, i)}
            v2_elig = {i for i in isins if v2_store.entry_gate(day, i)}
            assert v3_elig == v2_elig

    def test_floor_scores_are_percentile_not_raw(self):
        """
        Guard the Erratum's own claim: the floor's SCORES are percentile ranks in
        [0, 1], not the raw `mom/vol` candidate scores. Order matches the
        reference; magnitude deliberately does not.
        """
        isins = [f"ISIN{i:02d}" for i in range(6)]
        prices = _make_prices(isins)
        v3_store = precompute_v3_signals(prices, _v3_cfg())
        day = _last_rebalance_day(prices)
        ranked = v3_store.eligible_ranked(day, isins)
        for _, score in ranked:
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Gate semantics — momentum filter is conditional on momentum being active
# ---------------------------------------------------------------------------


class TestConditionalMomentumGate:
    def test_non_momentum_composite_drops_mom_filter(self):
        """
        A pure low-vol composite must NOT inherit the absolute-momentum (mom>0)
        filter (prereg Erratum). A name in a downtrend (mom<0) but above its
        EMA_200 long-window can be eligible under low-vol-only where it is barred
        under the momentum floor. We assert the low-vol gate is a SUPERSET of the
        momentum gate (dropping a condition can only admit more names).
        """
        isins = [f"ISIN{i:02d}" for i in range(10)]
        # Mixed regime: some names roll over at the end so mom_12_1 goes negative
        # while price can still sit above the long EMA on some days.
        prices = _make_prices(isins, seed=3, drift=0.0)
        mom_store = precompute_v3_signals(prices, _v3_cfg(active_factors=["mom_12_1"]))
        lv_store = precompute_v3_signals(prices, _v3_cfg(active_factors=["low_vol"]))

        cal = sorted(pd.to_datetime(prices["date"].unique()))
        admitted_extra = False
        for day in sorted(_month_end_dates(cal))[-4:]:
            mom_elig = {i for i in isins if mom_store.entry_gate(day, i)}
            lv_elig = {i for i in isins if lv_store.entry_gate(day, i)}
            # Dropping the mom>0 condition can only ever admit more names.
            assert mom_elig <= lv_elig
            if lv_elig - mom_elig:
                admitted_extra = True
        # The fixture must actually exercise the difference, else the test is vacuous.
        assert admitted_extra

    def test_momentum_active_flag_set_from_active_factors(self):
        """The conditional flag is driven by active_factors, nothing else."""
        prices = _make_prices([f"ISIN{i:02d}" for i in range(3)])
        assert precompute_v3_signals(
            prices, _v3_cfg(active_factors=["mom_12_1", "low_vol"])
        )._momentum_active
        assert not precompute_v3_signals(
            prices, _v3_cfg(active_factors=["low_vol"])
        )._momentum_active


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_determinism_same_inputs_same_selection():
    """Same config + data → identical eligible_ranked output (no hidden state)."""
    isins = [f"ISIN{i:02d}" for i in range(8)]
    prices = _make_prices(isins)
    cfg = _v3_cfg()
    day = _last_rebalance_day(prices)

    a = precompute_v3_signals(prices, cfg).eligible_ranked(day, isins)
    b = precompute_v3_signals(prices, cfg).eligible_ranked(day, isins)
    assert a == b
    # NaN scores never leak into the ranked output.
    assert all(not math.isnan(s) for _, s in a)
