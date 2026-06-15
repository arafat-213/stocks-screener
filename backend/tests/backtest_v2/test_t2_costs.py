"""
T2 acceptance tests — cost interface + trivial default (costs.py).

All offline: no network, no DB, no parquet reads.

WHY each test exists:
  - Known ₹ output: proves the flat-bps arithmetic is correct so downstream
    modules (portfolio cash conservation in T5) can rely on it.
  - ADV ignored: documents the zero-slippage contract of the placeholder;
    a failing test here would mean the placeholder accidentally introduces
    ADV-dependent behaviour, making it non-trivial to swap out in spec 03.
  - Side symmetry: both buy and sell legs cost the same (flat bps, no
    asymmetric STT yet — that is spec 03's job).
  - Injectable interface: proves fill_cost satisfies the CostFn signature,
    so T5/T7 can pass it as a callable parameter without type errors.
  - Determinism: spec 02 §10.3 — same inputs must always produce same cost.
"""

import pytest

from app.backtest_v2.costs import CostConfig, CostFn, fill_cost


class TestFillCost:
    def test_known_output_buy(self):
        """100 shares × ₹1 000 × 30 bps RT → half per leg → ₹150."""
        cfg = CostConfig(round_trip_bps=30.0)
        cost = fill_cost("buy", qty=100.0, price=1_000.0, adv_20=1e7, cfg=cfg)
        assert cost == pytest.approx(150.0)

    def test_known_output_sell(self):
        """Same notional on sell side must match buy (flat bps, no asymmetry)."""
        cfg = CostConfig(round_trip_bps=30.0)
        cost = fill_cost("sell", qty=100.0, price=1_000.0, adv_20=1e7, cfg=cfg)
        assert cost == pytest.approx(150.0)

    def test_trim_same_as_sell(self):
        """'trim' is a partial sell and should incur the same flat cost."""
        cfg = CostConfig(round_trip_bps=30.0)
        cost_sell = fill_cost("sell", 50.0, 800.0, 1e6, cfg)
        cost_trim = fill_cost("trim", 50.0, 800.0, 1e6, cfg)
        assert cost_sell == pytest.approx(cost_trim)

    def test_adv_ignored(self):
        """Placeholder has zero slippage — different adv_20 must give identical cost."""
        cfg = CostConfig(round_trip_bps=30.0)
        cost_high = fill_cost("buy", 100.0, 1_000.0, adv_20=1e10, cfg=cfg)
        cost_low = fill_cost("buy", 100.0, 1_000.0, adv_20=1e3, cfg=cfg)
        assert cost_high == pytest.approx(cost_low)

    def test_custom_bps(self):
        """100 bps round-trip → 50 bps per leg; 200 × ₹500 notional → ₹500."""
        cfg = CostConfig(round_trip_bps=100.0)
        cost = fill_cost("buy", qty=200.0, price=500.0, adv_20=5e6, cfg=cfg)
        assert cost == pytest.approx(500.0)

    def test_zero_qty(self):
        """Zero-share fill has zero cost (edge case for trims/rounding)."""
        cfg = CostConfig()
        assert fill_cost("buy", 0.0, 1_000.0, 5e6, cfg) == pytest.approx(0.0)

    def test_deterministic(self):
        """Same inputs → same output on repeated calls (02 §10.3)."""
        cfg = CostConfig()
        c1 = fill_cost("buy", 50.0, 2_000.0, 5e6, cfg)
        c2 = fill_cost("buy", 50.0, 2_000.0, 5e6, cfg)
        assert c1 == pytest.approx(c2)

    def test_injectable_interface(self):
        """fill_cost must be passable as a CostFn — proves the injectable contract
        that T5 (portfolio) and T7 (engine) depend on."""

        def simulate_one_fill(cost_fn: CostFn, cfg: CostConfig) -> float:
            return cost_fn("buy", 10.0, 500.0, 1e6, cfg)

        cfg = CostConfig(round_trip_bps=20.0)
        result = simulate_one_fill(fill_cost, cfg)
        # notional=5 000; half_bps=10; cost = 5 000 × 10 / 10 000 = 5.0
        assert result == pytest.approx(5.0)

    def test_cost_config_default_bps(self):
        """Default CostConfig round_trip_bps must match the spec 02 placeholder value."""
        cfg = CostConfig()
        assert cfg.round_trip_bps == 30.0

    def test_cost_scales_linearly_with_notional(self):
        """Doubling qty must double cost (no fixed-fee component in placeholder)."""
        cfg = CostConfig(round_trip_bps=30.0)
        c1 = fill_cost("buy", 100.0, 1_000.0, 5e6, cfg)
        c2 = fill_cost("buy", 200.0, 1_000.0, 5e6, cfg)
        assert c2 == pytest.approx(2 * c1)
