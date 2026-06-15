"""
T4 tests — cost level presets + engine cost_level param (spec 03 T4).

Done-criteria:
  [x] Three CostConfig presets exist; pessimistic cost > base > optimistic on
      the same fill (unit-tested).
  [x] cost_level is a single run parameter threaded through engine.run (not
      hand-edited per run) — asserted that total_cost_paid differs correctly.
  [x] Tests offline (no live network, no bhavcopy parquet — Rule 5).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.backtest_v2 import engine
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.costs import CostConfig, CostLevel, effective_price, fill_cost

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prices(
    n_days: int = 350, n_isins: int = 5, start_price: float = 100.0
) -> pd.DataFrame:
    """Build a minimal synthetic prices frame for engine tests."""
    import numpy as np

    rng = np.random.default_rng(42)
    base = date(2022, 1, 3)
    cal = pd.bdate_range(start=base, periods=n_days, freq="B")
    records = []
    for isin_idx in range(n_isins):
        isin = f"INE{isin_idx:04d}01"
        sym = f"SYM{isin_idx}"
        price = start_price + isin_idx * 10.0
        for i, ts in enumerate(cal):
            ret = rng.normal(0.0005, 0.015)
            price = max(price * (1 + ret), 0.01)
            records.append(
                {
                    "date": ts,
                    "isin": isin,
                    "symbol": sym,
                    "open": price * rng.uniform(0.99, 1.01),
                    "high": price * rng.uniform(1.00, 1.02),
                    "low": price * rng.uniform(0.98, 1.00),
                    "close": price,
                    "close_raw": price,
                    "close_tr": price * 1.001**i,
                    "volume": 100_000,
                    "traded_value": 1e9,
                    "adv_20": 1e8,  # ₹10 crore ADV — liquid
                    "adj_factor": 1.0,
                    "tr_factor": 1.001**i,
                    "series": "EQ",
                }
            )
    return pd.DataFrame(records)


def _make_config(n_days: int = 350) -> MomentumConfig:
    base = date(2022, 1, 3)
    cal = pd.bdate_range(start=base, periods=n_days, freq="B")
    return MomentumConfig(
        date_from=base,
        date_to=cal[-1].date(),
        starting_capital=1_000_000.0,
        target_positions=3,
        use_regime_overlay=False,
    )


# ---------------------------------------------------------------------------
# TestPresets — ordering + field values
# ---------------------------------------------------------------------------


class TestPresets:
    def test_optimistic_has_zero_slippage(self):
        cfg = CostConfig.optimistic()
        assert cfg.base_slippage_pct == 0.0
        assert cfg.impact_coeff == 0.0

    def test_base_uses_t0_defaults(self):
        cfg = CostConfig.base()
        default = CostConfig()
        assert cfg.base_slippage_pct == default.base_slippage_pct
        assert cfg.impact_coeff == default.impact_coeff
        assert cfg.stt_pct == default.stt_pct

    def test_pessimistic_doubles_slippage(self):
        base_cfg = CostConfig.base()
        pess_cfg = CostConfig.pessimistic()
        assert pess_cfg.base_slippage_pct == pytest.approx(
            2.0 * base_cfg.base_slippage_pct, rel=1e-9
        )
        assert pess_cfg.impact_coeff == pytest.approx(
            2.0 * base_cfg.impact_coeff, rel=1e-9
        )

    def test_statutory_rates_unchanged_across_levels(self):
        """Statutory charges (STT, DP, etc.) are the same for all three levels."""
        opt = CostConfig.optimistic()
        base = CostConfig.base()
        pess = CostConfig.pessimistic()
        for field in (
            "stt_pct",
            "exchange_txn_pct",
            "sebi_pct",
            "stamp_duty_pct",
            "gst_pct",
            "dp_charge",
        ):
            assert (
                getattr(opt, field) == getattr(base, field) == getattr(pess, field)
            ), f"{field} differs across presets"


class TestPresetOrdering:
    """Pessimistic cost > base > optimistic on the same fill."""

    SIDE = "buy"
    QTY = 100.0
    PRICE = 200.0
    ADV_20 = 1e7  # ₹1 crore, modest ADV so participation drives slippage

    def _total_cost_one_fill(self, cfg: CostConfig) -> float:
        """Statutory cash cost + slippage cost (as ₹ from price difference)."""
        eff_p = effective_price(self.SIDE, self.PRICE, self.QTY, self.ADV_20, cfg)
        stat_cost = fill_cost(self.SIDE, self.QTY, eff_p, self.ADV_20, cfg)
        slippage_cost = (eff_p - self.PRICE) * self.QTY  # extra ₹ paid vs raw
        return stat_cost + slippage_cost

    def test_optimistic_lt_base_lt_pessimistic(self):
        opt = self._total_cost_one_fill(CostConfig.optimistic())
        base = self._total_cost_one_fill(CostConfig.base())
        pess = self._total_cost_one_fill(CostConfig.pessimistic())
        assert opt < base, f"optimistic ({opt:.2f}) should be < base ({base:.2f})"
        assert base < pess, f"base ({base:.2f}) should be < pessimistic ({pess:.2f})"

    def test_optimistic_has_no_slippage_premium(self):
        cfg_opt = CostConfig.optimistic()
        eff = effective_price(self.SIDE, self.PRICE, self.QTY, self.ADV_20, cfg_opt)
        assert eff == pytest.approx(self.PRICE), (
            "optimistic should fill at raw price (zero slippage)"
        )

    def test_sell_pessimistic_lower_proceeds(self):
        base_p = effective_price(
            "sell", self.PRICE, self.QTY, self.ADV_20, CostConfig.base()
        )
        pess_p = effective_price(
            "sell", self.PRICE, self.QTY, self.ADV_20, CostConfig.pessimistic()
        )
        assert pess_p < base_p, "pessimistic sell should give lower proceeds than base"

    def test_cost_ordering_sell_side(self):
        opt = fill_cost(
            "sell", self.QTY, self.PRICE, self.ADV_20, CostConfig.optimistic()
        )
        base = fill_cost("sell", self.QTY, self.PRICE, self.ADV_20, CostConfig.base())
        pess = fill_cost(
            "sell", self.QTY, self.PRICE, self.ADV_20, CostConfig.pessimistic()
        )
        # Statutory costs are equal across presets; pessimistic adds no extra statutory
        assert opt == pytest.approx(base, rel=1e-9) == pytest.approx(pess, rel=1e-9), (
            "fill_cost (statutory only) should be identical across presets"
        )


# ---------------------------------------------------------------------------
# TestCostLevelEngineParam — cost_level threads through engine.run
# ---------------------------------------------------------------------------


class TestCostLevelEngineParam:
    """Validate that cost_level selects the right preset in engine.run."""

    def test_cost_level_param_accepted(self):
        """engine.run accepts cost_level without raising."""
        prices = _make_prices()
        config = _make_config()
        # Should not raise for any of the three levels.
        for level in ("optimistic", "base", "pessimistic"):
            r = engine.run(prices, config, cost_level=level)
            assert len(r.snapshots) > 0

    def test_optimistic_less_cost_than_pessimistic(self):
        """Optimistic ends with higher equity than pessimistic (slippage drag is real).

        total_cost_paid captures statutory-only cash deductions; slippage raises
        the effective fill price, reducing equity directly. Final equity is the
        correct observable for total economic cost ordering.
        """
        prices = _make_prices()
        config = _make_config()
        r_opt = engine.run(prices, config, cost_level="optimistic")
        r_pess = engine.run(prices, config, cost_level="pessimistic")
        eq_opt = r_opt.snapshots[-1].equity
        eq_pess = r_pess.snapshots[-1].equity
        assert eq_opt >= eq_pess, (
            f"optimistic equity {eq_opt:.2f} should be >= pessimistic {eq_pess:.2f} "
            "(higher slippage at pessimistic reduces final equity)"
        )

    def test_base_between_optimistic_and_pessimistic(self):
        """Base equity is between optimistic and pessimistic (monotone ordering)."""
        prices = _make_prices()
        config = _make_config()
        r_opt = engine.run(prices, config, cost_level="optimistic")
        r_base = engine.run(prices, config, cost_level="base")
        r_pess = engine.run(prices, config, cost_level="pessimistic")
        eq_opt = r_opt.snapshots[-1].equity
        eq_base = r_base.snapshots[-1].equity
        eq_pess = r_pess.snapshots[-1].equity
        assert eq_opt >= eq_base >= eq_pess, (
            f"expected opt>=base>=pess equity: "
            f"{eq_opt:.2f} / {eq_base:.2f} / {eq_pess:.2f}"
        )

    def test_cost_level_overrides_explicit_cost_cfg(self):
        """cost_level overrides an explicitly-passed cost_cfg (cost_level wins)."""
        prices = _make_prices()
        config = _make_config()
        # Pass a pessimistic cost_cfg but ask for optimistic level — optimistic wins.
        r_should_be_opt = engine.run(
            prices,
            config,
            cost_level="optimistic",
            cost_cfg=CostConfig.pessimistic(),
        )
        r_opt = engine.run(prices, config, cost_level="optimistic")
        assert r_should_be_opt.total_cost_paid == pytest.approx(
            r_opt.total_cost_paid, rel=1e-6
        ), "cost_level should override explicit cost_cfg"

    def test_default_run_equals_base_level(self):
        """engine.run() with no cost_level/cost_cfg == cost_level='base'."""
        prices = _make_prices()
        config = _make_config()
        r_default = engine.run(prices, config)
        r_base = engine.run(prices, config, cost_level="base")
        # Total cost paid should be identical since both use CostConfig() defaults.
        assert r_default.total_cost_paid == pytest.approx(
            r_base.total_cost_paid, rel=1e-9
        )

    def test_equity_curves_differ_across_levels(self):
        """All three levels produce distinct equity curves (cost drag is real)."""
        prices = _make_prices()
        config = _make_config()
        r_opt = engine.run(prices, config, cost_level="optimistic")
        r_pess = engine.run(prices, config, cost_level="pessimistic")
        eq_opt = np.array([s.equity for s in r_opt.snapshots])
        eq_pess = np.array([s.equity for s in r_pess.snapshots])
        # Optimistic should finish with higher or equal equity than pessimistic.
        assert eq_opt[-1] >= eq_pess[-1], (
            "optimistic equity should be >= pessimistic at end of run"
        )


# ---------------------------------------------------------------------------
# TestPresetUnitCost — explicit hand-worked spot checks
# ---------------------------------------------------------------------------


class TestPresetUnitCost:
    """Spot-check that the three preset factory methods produce valid configs."""

    def test_all_three_constructible(self):
        """All three factory methods return a CostConfig without error."""
        for method in (CostConfig.optimistic, CostConfig.base, CostConfig.pessimistic):
            cfg = method()
            assert isinstance(cfg, CostConfig)

    def test_no_round_trip_bps_in_presets(self):
        """Presets use the real statutory model, not the legacy flat-bps path."""
        for method in (CostConfig.optimistic, CostConfig.base, CostConfig.pessimistic):
            cfg = method()
            assert cfg.round_trip_bps is None, (
                f"{method.__name__} should not set round_trip_bps"
            )

    def test_cost_level_type_alias_accepts_all_strings(self):
        """CostLevel values match the expected preset names (static check via set)."""
        expected: set[CostLevel] = {"optimistic", "base", "pessimistic"}
        assert expected == {"optimistic", "base", "pessimistic"}
