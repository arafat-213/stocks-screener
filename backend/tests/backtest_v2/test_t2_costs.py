"""
Costs test suite (updated for spec 03 T1 — real statutory + slippage model).

All offline: no network, no DB, no parquet reads.

Done-criteria coverage (spec 03 T1):
  DC1  fill_cost statutory + DP: hand-worked example matches per side.
  DC2  Slippage moves effective fill price (buy higher / sell lower); a buy's
       cost basis > raw open price.
  DC3  Slippage scales with participation; clamped at ceiling.
  DC4  fill_cost signature unchanged; legacy round_trip_bps path still works
       (backwards-compat for spec-02 test suites in test_t5_portfolio.py).
"""

import pytest

from app.backtest_v2.costs import CostConfig, CostFn, effective_price, fill_cost

# ---------------------------------------------------------------------------
# DC1 — Statutory + DP hand-worked examples
# ---------------------------------------------------------------------------

# Reference values for qty=100, price=₹1,000 (notional=₹100,000):
#   stt     = 0.001  × 100,000 = 100.0000
#   exchange= 0.0000297 × 100,000 =   2.9700
#   sebi    = 0.000001 × 100,000 =   0.1000
#   stamp   = 0.00015 × 100,000 =  15.0000  (buy only)
#   gst     = 0.18 × (2.97+0.10) =   0.5526
#   dp      = 15.34                         (sell only)
_BUY_STATUTORY = 100.0 + 2.97 + 0.10 + 15.0 + 0.5526  # 118.6226
_SELL_STATUTORY = 100.0 + 2.97 + 0.10 + 0.5526 + 15.34  # 118.9626 + 0 stamp


class TestFillCostStatutory:
    def test_buy_hand_worked(self):
        """fill_cost(buy) must match the T0-verified statutory breakdown."""
        cfg = CostConfig()
        cost = fill_cost("buy", qty=100.0, price=1_000.0, adv_20=1e7, cfg=cfg)
        assert cost == pytest.approx(_BUY_STATUTORY, rel=1e-6)

    def test_sell_hand_worked(self):
        """fill_cost(sell) includes DP charge + STT; no stamp duty."""
        cfg = CostConfig()
        cost = fill_cost("sell", qty=100.0, price=1_000.0, adv_20=1e7, cfg=cfg)
        assert cost == pytest.approx(_SELL_STATUTORY, rel=1e-6)

    def test_buy_cheaper_than_sell_for_small_position(self):
        """Sell costs more than buy for small notionals (DP dominates over stamp)."""
        cfg = CostConfig()
        c_buy = fill_cost("buy", 10.0, 100.0, 1e6, cfg)
        c_sell = fill_cost("sell", 10.0, 100.0, 1e6, cfg)
        # DP = ₹15.34 on sell; stamp duty = 0.015% × 1000 = ₹0.15 on buy
        # sell cost includes DP which dwarfs buy stamp for small notionals
        assert c_sell > c_buy

    def test_stamp_duty_buy_only(self):
        """Stamp duty is charged on buy but NOT on sell/trim."""
        cfg = CostConfig()
        c_buy = fill_cost("buy", 100.0, 1_000.0, 0.0, cfg)
        c_sell = fill_cost("sell", 100.0, 1_000.0, 0.0, cfg)
        stamp_on_buy = 100_000.0 * cfg.stamp_duty_pct
        # The buy cost exceeds sell cost (before DP) by exactly stamp_duty
        dp = cfg.dp_charge
        assert c_buy - c_sell == pytest.approx(stamp_on_buy - dp, rel=1e-6)

    def test_dp_charge_flat_on_sell_only(self):
        """DP charge is flat ₹15.34 per scrip on sell, regardless of qty."""
        cfg = CostConfig()
        c_small = fill_cost("sell", 1.0, 1_000.0, 0.0, cfg)
        c_large = fill_cost("sell", 1_000.0, 1_000.0, 0.0, cfg)
        assert c_large - c_small == pytest.approx(
            999.0 * 1_000.0 * (cfg.stt_pct + cfg.exchange_txn_pct + cfg.sebi_pct)
            + 999.0 * 1_000.0 * cfg.exchange_txn_pct * cfg.gst_pct
            + 999.0 * 1_000.0 * cfg.sebi_pct * cfg.gst_pct,
            rel=1e-5,
        )

    def test_trim_same_statutory_as_sell(self):
        """'trim' is a partial sell — same statutory cost path."""
        cfg = CostConfig()
        c_sell = fill_cost("sell", 50.0, 800.0, 1e6, cfg)
        c_trim = fill_cost("trim", 50.0, 800.0, 1e6, cfg)
        assert c_sell == pytest.approx(c_trim)

    def test_zero_qty_zero_cost(self):
        """Zero-share fill has zero statutory cost."""
        cfg = CostConfig()
        assert fill_cost("buy", 0.0, 1_000.0, 5e6, cfg) == pytest.approx(0.0)

    def test_deterministic(self):
        """Same inputs → same cost on repeated calls (spec 02 §10.3)."""
        cfg = CostConfig()
        c1 = fill_cost("buy", 50.0, 2_000.0, 5e6, cfg)
        c2 = fill_cost("buy", 50.0, 2_000.0, 5e6, cfg)
        assert c1 == pytest.approx(c2)

    def test_injectable_interface(self):
        """fill_cost satisfies the CostFn callable signature."""

        def run(fn: CostFn, cfg: CostConfig) -> float:
            return fn("buy", 10.0, 500.0, 1e6, cfg)

        result = run(fill_cost, CostConfig())
        assert result > 0.0  # real statutory cost is positive


# ---------------------------------------------------------------------------
# DC2 — Slippage moves the effective fill price
# ---------------------------------------------------------------------------


class TestEffectivePrice:
    def test_buy_fills_higher_than_raw_open(self):
        """A buy's effective price must exceed the raw open (slippage up)."""
        cfg = CostConfig()
        eff = effective_price("buy", 1_000.0, 100.0, 1e8, cfg)
        assert eff > 1_000.0

    def test_sell_fills_lower_than_raw_open(self):
        """A sell's effective price must be below the raw open (slippage down)."""
        cfg = CostConfig()
        eff = effective_price("sell", 1_000.0, 100.0, 1e8, cfg)
        assert eff < 1_000.0

    def test_trim_fills_lower_than_raw_open(self):
        """Trim is treated identically to sell for slippage direction."""
        cfg = CostConfig()
        eff_sell = effective_price("sell", 1_000.0, 50.0, 1e8, cfg)
        eff_trim = effective_price("trim", 1_000.0, 50.0, 1e8, cfg)
        assert eff_sell == pytest.approx(eff_trim)

    def test_buy_cost_basis_exceeds_raw_open(self):
        """After a slipped buy, per-share cost basis > raw open (spec 03 §4.2).

        Simulates what portfolio._do_buy computes:
          per_share_basis = (qty * eff_p + statutory) / qty
        """
        cfg = CostConfig()
        raw_open = 1_000.0
        qty = 100.0
        adv_20 = 1e8  # large ADV → minimal participation impact

        eff_p = effective_price("buy", raw_open, qty, adv_20, cfg)
        statutory = fill_cost("buy", qty, eff_p, adv_20, cfg)
        per_share_basis = (qty * eff_p + statutory) / qty

        assert eff_p > raw_open, "effective price must exceed raw open"
        assert per_share_basis > raw_open, "cost basis must exceed raw open"

    def test_zero_adv_uses_base_slippage_only(self):
        """Unknown ADV (0) → base_slippage_pct floor, no participation impact."""
        cfg = CostConfig(base_slippage_pct=0.002, impact_coeff=0.5)
        eff = effective_price("buy", 1_000.0, 100.0, 0.0, cfg)
        assert eff == pytest.approx(1_000.0 * (1.0 + 0.002))

    def test_base_slippage_floor_at_negligible_participation(self):
        """Near-zero participation → slippage ≈ base_slippage_pct."""
        cfg = CostConfig(base_slippage_pct=0.0015, impact_coeff=0.15)
        # participation = (1 × 1) / 1e12 ≈ 0
        eff = effective_price("buy", 1_000.0, 1.0, 1e12, cfg)
        assert eff == pytest.approx(1_000.0 * 1.0015, rel=1e-4)


# ---------------------------------------------------------------------------
# DC3 — Participation scaling + ceiling
# ---------------------------------------------------------------------------


class TestSlippageScaling:
    def test_higher_participation_higher_slippage(self):
        """More of ADV consumed → larger effective price deviation."""
        cfg = CostConfig()
        raw = 1_000.0
        adv_20 = 1_000_000.0  # ₹1M ADV

        # Low participation: qty × price = ₹1k → participation = 0.1%
        eff_low = effective_price("buy", raw, 1.0, adv_20, cfg)

        # High participation: qty × price = ₹100k → participation = 10% (cap)
        eff_high = effective_price("buy", raw, 100.0, adv_20, cfg)

        assert eff_high > eff_low

    def test_participation_clamped_at_ceiling(self):
        """participation_cap clamps slippage beyond a threshold."""
        cfg = CostConfig(
            base_slippage_pct=0.001,
            impact_coeff=0.10,
            participation_cap=0.05,
        )
        raw = 1_000.0
        adv_20 = 1_000.0  # tiny ADV

        # participation = (1000 × 1000) / 1000 = 1000 → clamped at 0.05
        eff_capped = effective_price("buy", raw, 1_000.0, adv_20, cfg)
        # expected slip = 0.001 + 0.10 × 0.05 = 0.006
        assert eff_capped == pytest.approx(raw * (1.0 + 0.006), rel=1e-6)

    def test_1pct_adv_participation_adds_015pct(self):
        """Spec §1.2 calibration: 1%-of-ADV order adds ~0.15% additional slippage."""
        cfg = CostConfig()
        raw = 1_000.0
        adv_20 = 1_000_000.0  # ₹1M
        # 1% of ADV = ₹10,000 → qty = 10 @ ₹1,000
        eff = effective_price("buy", raw, 10.0, adv_20, cfg)
        # participation = 10,000 / 1,000,000 = 0.01
        # slip = 0.0015 + 0.15 × 0.01 = 0.003
        assert eff == pytest.approx(raw * 1.003, rel=1e-6)


# ---------------------------------------------------------------------------
# DC4 — Backward compatibility: legacy round_trip_bps path
# ---------------------------------------------------------------------------


class TestLegacyFlatBpsPath:
    def test_round_trip_bps_flat_buy(self):
        """CostConfig(round_trip_bps=30) → half-RT per leg = 15 bps."""
        cfg = CostConfig(round_trip_bps=30.0)
        cost = fill_cost("buy", qty=100.0, price=1_000.0, adv_20=1e7, cfg=cfg)
        assert cost == pytest.approx(150.0)  # 100,000 × 15 / 10,000

    def test_round_trip_bps_flat_sell(self):
        """Legacy sell cost equals buy cost (flat bps, no asymmetry)."""
        cfg = CostConfig(round_trip_bps=30.0)
        c_buy = fill_cost("buy", 100.0, 1_000.0, 1e7, cfg)
        c_sell = fill_cost("sell", 100.0, 1_000.0, 1e7, cfg)
        assert c_buy == pytest.approx(c_sell)

    def test_zero_round_trip_bps_zero_cost(self):
        """CostConfig(round_trip_bps=0.0) → zero cost (used in spec-02 tests)."""
        cfg = CostConfig(round_trip_bps=0.0)
        assert fill_cost("buy", 100.0, 1_000.0, 1e7, cfg) == pytest.approx(0.0)

    def test_legacy_effective_price_unchanged(self):
        """Legacy path: effective_price returns raw price (no slippage)."""
        cfg = CostConfig(round_trip_bps=30.0)
        raw = 1_000.0
        assert effective_price("buy", raw, 100.0, 1e7, cfg) == pytest.approx(raw)
        assert effective_price("sell", raw, 100.0, 1e7, cfg) == pytest.approx(raw)

    def test_adv_ignored_in_legacy_path(self):
        """Legacy fill_cost ignores adv_20 (zero-slippage contract from spec-02)."""
        cfg = CostConfig(round_trip_bps=30.0)
        c_high = fill_cost("buy", 100.0, 1_000.0, adv_20=1e10, cfg=cfg)
        c_low = fill_cost("buy", 100.0, 1_000.0, adv_20=1e3, cfg=cfg)
        assert c_high == pytest.approx(c_low)

    def test_cost_scales_linearly_with_notional_legacy(self):
        """Doubling qty doubles cost in legacy path (no fixed-fee component)."""
        cfg = CostConfig(round_trip_bps=30.0)
        c1 = fill_cost("buy", 100.0, 1_000.0, 5e6, cfg)
        c2 = fill_cost("buy", 200.0, 1_000.0, 5e6, cfg)
        assert c2 == pytest.approx(2 * c1)
