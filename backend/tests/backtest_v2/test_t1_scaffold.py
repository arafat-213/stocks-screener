"""
T1 acceptance tests — scaffold, types, config.

All offline: no network, no DB, no parquet reads.
WHY: pins the dataclass contracts so later tasks (T2-T9) build against
fixed field sets; a field rename here would break every downstream module.
"""

import dataclasses
from datetime import date

import pytest

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.schemas import DailySnapshot, Fill, Position, RebalancePlan

# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


class TestPosition:
    def test_fields_present(self):
        pos = Position(
            isin="INE009A01021",
            symbol="INFY",
            shares=100.0,
            cost_basis=1500.0,
            entry_date=date(2024, 1, 15),
            last_price=1600.0,
        )
        assert pos.isin == "INE009A01021"
        assert pos.symbol == "INFY"
        assert pos.shares == 100.0
        assert pos.cost_basis == 1500.0
        assert pos.entry_date == date(2024, 1, 15)
        assert pos.last_price == 1600.0

    def test_frozen(self):
        pos = Position("X", "Y", 1.0, 100.0, date(2024, 1, 1), 100.0)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            pos.shares = 999.0  # type: ignore[misc]

    def test_field_count(self):
        assert len(dataclasses.fields(Position)) == 6


# ---------------------------------------------------------------------------
# Fill
# ---------------------------------------------------------------------------


class TestFill:
    def test_fields_present(self):
        f = Fill(
            isin="INE009A01021",
            symbol="INFY",
            side="buy",
            qty=50.0,
            price=1550.0,
            date=date(2024, 1, 16),
            cost_rupees=232.5,
        )
        assert f.side == "buy"
        assert f.qty == 50.0
        assert f.cost_rupees == 232.5

    def test_frozen(self):
        f = Fill("X", "Y", "sell", 10.0, 100.0, date(2024, 1, 1), 5.0)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            f.qty = 999.0  # type: ignore[misc]

    def test_valid_sides(self):
        for side in ("buy", "sell", "trim"):
            f = Fill("X", "Y", side, 1.0, 100.0, date(2024, 1, 1), 1.0)
            assert f.side == side


# ---------------------------------------------------------------------------
# RebalancePlan
# ---------------------------------------------------------------------------


class TestRebalancePlan:
    def test_empty_plan(self):
        plan = RebalancePlan()
        assert plan.sells == []
        assert plan.buys == []
        assert plan.trims == []

    def test_with_fills(self):
        sell = Fill("A", "AAA", "sell", 10.0, 200.0, date(2024, 2, 1), 2.0)
        buy = Fill("B", "BBB", "buy", 20.0, 300.0, date(2024, 2, 1), 6.0)
        plan = RebalancePlan(sells=[sell], buys=[buy])
        assert len(plan.sells) == 1
        assert len(plan.buys) == 1
        assert len(plan.trims) == 0

    def test_frozen(self):
        plan = RebalancePlan()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            plan.sells = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DailySnapshot
# ---------------------------------------------------------------------------


class TestDailySnapshot:
    def test_fields_present(self):
        snap = DailySnapshot(
            date=date(2024, 3, 1),
            equity=1_050_000.0,
            cash=200_000.0,
            invested_value=850_000.0,
            exposure=850_000.0 / 1_050_000.0,
            n_positions=15,
        )
        assert snap.equity == pytest.approx(1_050_000.0)
        assert snap.exposure == pytest.approx(850_000.0 / 1_050_000.0)
        assert snap.n_positions == 15

    def test_frozen(self):
        snap = DailySnapshot(date(2024, 1, 1), 1e6, 1e6, 0.0, 0.0, 0)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            snap.equity = 0.0  # type: ignore[misc]

    def test_field_count(self):
        assert len(dataclasses.fields(DailySnapshot)) == 6


# ---------------------------------------------------------------------------
# MomentumConfig — field set must match spec 02 §7 exactly
# ---------------------------------------------------------------------------

_SPEC_FIELDS = {
    "target_positions",
    "sell_rank_buffer",
    "liquidity_floor_cr",
    "momentum_lookback_days",
    "momentum_skip_days",
    "vol_lookback_days",
    "trend_ma",
    "max_position_pct",
    "starting_capital",
    "use_regime_overlay",
    "catastrophic_stop_pct",
    "rebalance",
    "date_from",
    "date_to",
}


class TestMomentumConfig:
    def test_field_set_exact(self):
        actual = {f.name for f in dataclasses.fields(MomentumConfig)}
        assert actual == _SPEC_FIELDS, (
            f"Extra fields: {actual - _SPEC_FIELDS}  |  Missing: {_SPEC_FIELDS - actual}"
        )

    def test_defaults_match_spec(self):
        cfg = MomentumConfig()
        assert cfg.target_positions == 20
        assert cfg.sell_rank_buffer == 35
        assert cfg.liquidity_floor_cr == 5.0
        assert cfg.momentum_lookback_days == 252
        assert cfg.momentum_skip_days == 21
        assert cfg.vol_lookback_days == 126
        assert cfg.trend_ma == "EMA_200"
        assert cfg.max_position_pct == 10.0
        assert cfg.starting_capital == 1_000_000.0
        assert cfg.use_regime_overlay is True
        assert cfg.catastrophic_stop_pct == 25.0
        assert cfg.rebalance == "monthly"
        assert cfg.date_from is None
        assert cfg.date_to is None

    def test_mutable_config(self):
        cfg = MomentumConfig(target_positions=30, rebalance="weekly")
        assert cfg.target_positions == 30
        assert cfg.rebalance == "weekly"

    def test_buffer_gt_target(self):
        cfg = MomentumConfig()
        assert cfg.sell_rank_buffer > cfg.target_positions, (
            "sell_rank_buffer (M) must be > target_positions (N) by design"
        )
