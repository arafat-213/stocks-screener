"""
test_t5_portfolio.py — T5 done-criteria tests (offline; no network).

Done criteria (02_SIMULATION_CORE_TASKS T5):
  DC1  cash conservation — equity == cash + Σ shares*price after any sequence of fills
  DC2  total cost paid == Σ per-fill fill_cost  (02 §10.2, no double-count)
  DC3  suspension — held ISIN missing on day D carries last price, is flagged,
       run continues
  DC4  MTM uses the prices dict passed in (caller is responsible for passing close_tr);
       different price values produce different equity
"""

from datetime import date

import pytest

from app.backtest_v2.costs import CostConfig, fill_cost
from app.backtest_v2.portfolio import Portfolio, build_rebalance_plan
from app.backtest_v2.schemas import Fill, Position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fill(
    isin: str,
    side: str,
    qty: float,
    price: float,
    d: date = date(2024, 1, 2),
) -> Fill:
    return Fill(
        isin=isin,
        symbol="SYM",
        side=side,  # type: ignore[arg-type]
        qty=qty,
        price=price,
        date=d,
        cost_rupees=0.0,
    )


def _position(
    isin: str,
    shares: float,
    last_price: float,
    cost_basis: float = 100.0,
) -> Position:
    return Position(
        isin=isin,
        symbol="SYM",
        shares=shares,
        cost_basis=cost_basis,
        entry_date=date(2024, 1, 1),
        last_price=last_price,
    )


_ZERO_COST = CostConfig(round_trip_bps=0.0)
_30BPS = CostConfig(round_trip_bps=30.0)

D1 = date(2024, 1, 2)
D2 = date(2024, 1, 3)
D3 = date(2024, 1, 4)


# ---------------------------------------------------------------------------
# DC1 — Cash conservation
# ---------------------------------------------------------------------------


class TestCashConservation:
    """equity == cash + Σ shares * price after any sequence of fills."""

    def _assert_conservation(self, p: Portfolio, prices: dict) -> None:
        snap = p.mark_to_market(D1, prices)
        assert abs(snap.equity - (p.cash + snap.invested_value)) < 1e-6

    def test_buy_zero_cost(self):
        p = Portfolio(cash=1_000_000)
        p.apply_fills([_fill("A", "buy", 100, 1_000.0)], fill_cost, _ZERO_COST)
        # cash = 1_000_000 − 100*1000 = 900_000
        self._assert_conservation(p, {"A": 1_000.0})
        assert abs(p.cash - 900_000.0) < 1e-6

    def test_sell_zero_cost(self):
        p = Portfolio(cash=900_000)
        p.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        p.apply_fills([_fill("A", "sell", 100, 1_000.0)], fill_cost, _ZERO_COST)
        snap = p.mark_to_market(D1, {})
        # No positions remain; equity == cash
        assert abs(snap.equity - p.cash) < 1e-6
        assert abs(p.cash - 1_000_000.0) < 1e-6

    def test_buy_with_cost(self):
        p = Portfolio(cash=1_000_000)
        p.apply_fills([_fill("A", "buy", 100, 1_000.0)], fill_cost, _30BPS)
        # cost = 100*1000 * 15/10_000 = 15
        # cash = 1_000_000 − 100_000 − 15 = 899_985
        self._assert_conservation(p, {"A": 1_000.0})

    def test_sequence_buy_sell_trim(self):
        p = Portfolio(cash=1_000_000)
        p.apply_fills(
            [
                _fill("A", "buy", 50, 1_000.0, D1),
                _fill("B", "buy", 100, 500.0, D1),
                _fill("C", "buy", 200, 250.0, D1),
            ],
            fill_cost,
            _ZERO_COST,
        )
        p.apply_fills(
            [
                _fill("A", "sell", 50, 1_100.0, D2),
                _fill("C", "trim", 100, 260.0, D2),
            ],
            fill_cost,
            _ZERO_COST,
        )
        snap = p.mark_to_market(D2, {"B": 520.0, "C": 260.0})
        assert abs(snap.equity - (p.cash + snap.invested_value)) < 1e-6

    def test_conservation_over_multiple_mtm_days(self):
        p = Portfolio(cash=1_000_000)
        p.apply_fills([_fill("A", "buy", 100, 1_000.0)], fill_cost, _ZERO_COST)
        for price, d in [(1_100.0, D1), (1_050.0, D2), (1_200.0, D3)]:
            snap = p.mark_to_market(d, {"A": price})
            assert abs(snap.equity - (p.cash + snap.invested_value)) < 1e-6


# ---------------------------------------------------------------------------
# DC2 — Cost accounting  (02 §10.2)
# ---------------------------------------------------------------------------


class TestCostAccounting:
    """_total_cost_paid == Σ fill_cost across all fills; fills_log has actual costs."""

    def test_total_matches_sum_of_per_fill_cost(self):
        p = Portfolio(cash=2_000_000)
        fills = [
            _fill("A", "buy", 100, 1_000.0),
            _fill("B", "buy", 200, 500.0),
        ]
        p.apply_fills(fills, fill_cost, _30BPS)
        expected = sum(fill_cost(f.side, f.qty, f.price, 0.0, _30BPS) for f in fills)
        assert abs(p._total_cost_paid - expected) < 1e-9

    def test_fills_log_cost_rupees_sum_equals_total(self):
        p = Portfolio(cash=2_000_000)
        fills = [
            _fill("A", "buy", 100, 1_000.0),
            _fill("A", "sell", 100, 1_100.0),
        ]
        p.apply_fills(fills, fill_cost, _30BPS)
        assert abs(sum(f.cost_rupees for f in p.fills_log) - p._total_cost_paid) < 1e-9

    def test_no_double_count_across_two_calls(self):
        p = Portfolio(cash=2_000_000)
        p.apply_fills([_fill("A", "buy", 100, 1_000.0)], fill_cost, _30BPS)
        cost_after_first = p._total_cost_paid
        p.apply_fills([_fill("B", "buy", 50, 500.0)], fill_cost, _30BPS)
        added = fill_cost("buy", 50, 500.0, 0.0, _30BPS)
        assert abs(p._total_cost_paid - (cost_after_first + added)) < 1e-9

    def test_zero_qty_fill_not_charged_not_logged(self):
        p = Portfolio(cash=1_000_000)
        zero = Fill(
            isin="A",
            symbol="SYM",
            side="buy",
            qty=0.0,
            price=1_000.0,
            date=D1,
            cost_rupees=0.0,
        )
        p.apply_fills([zero], fill_cost, _30BPS)
        assert p._total_cost_paid == 0.0
        assert len(p.fills_log) == 0

    def test_incoming_cost_rupees_field_ignored(self):
        """The Fill.cost_rupees coming in is replaced by the computed value."""
        p = Portfolio(cash=1_000_000)
        # Bogus cost_rupees=99999 should be ignored; apply_fills recomputes.
        bogus = Fill(
            isin="A",
            symbol="SYM",
            side="buy",
            qty=100,
            price=1_000.0,
            date=D1,
            cost_rupees=99_999.0,
        )
        p.apply_fills([bogus], fill_cost, _30BPS)
        actual = fill_cost("buy", 100, 1_000.0, 0.0, _30BPS)
        assert abs(p.fills_log[0].cost_rupees - actual) < 1e-9
        assert abs(p._total_cost_paid - actual) < 1e-9

    def test_injectable_cost_fn_used(self):
        """A custom cost function is called, not the hard-imported default."""
        calls: list[tuple] = []

        def capturing_cost(side, qty, price, adv_20, cfg):
            calls.append((side, qty, price))
            return 0.0

        p = Portfolio(cash=1_000_000)
        p.apply_fills([_fill("A", "buy", 100, 1_000.0)], capturing_cost, _ZERO_COST)
        assert len(calls) == 1
        assert calls[0] == ("buy", 100, 1_000.0)


# ---------------------------------------------------------------------------
# DC3 — Suspension handling
# ---------------------------------------------------------------------------


class TestSuspension:
    """Held ISIN missing on day D: carry last price, flag it, continue."""

    def test_missing_isin_carries_last_price(self):
        p = Portfolio(cash=800_000)
        p.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        snap = p.mark_to_market(D1, {})  # no price for A
        assert abs(snap.invested_value - 100 * 1_000.0) < 1e-6

    def test_suspension_flagged_in_log(self):
        p = Portfolio(cash=800_000)
        p.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        p.mark_to_market(D1, {})
        assert "A" in p.suspension_log
        assert D1 in p.suspension_log["A"]

    def test_other_isins_still_valued_correctly(self):
        p = Portfolio(cash=500_000)
        p.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        p.positions["B"] = _position("B", shares=200, last_price=500.0)
        snap = p.mark_to_market(D1, {"B": 510.0})  # A missing, B present
        assert "A" in p.suspension_log
        assert abs(p.positions["A"].last_price - 1_000.0) < 1e-9  # carried
        assert abs(p.positions["B"].last_price - 510.0) < 1e-9  # updated
        assert abs(snap.invested_value - (100 * 1_000.0 + 200 * 510.0)) < 1e-6

    def test_multiple_suspension_days_accumulated(self):
        p = Portfolio(cash=800_000)
        p.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        for d in [D1, D2, D3]:
            p.mark_to_market(d, {})
        assert len(p.suspension_log["A"]) == 3

    def test_nan_price_treated_as_missing(self):
        p = Portfolio(cash=800_000)
        p.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        snap = p.mark_to_market(D1, {"A": float("nan")})
        assert "A" in p.suspension_log
        assert abs(snap.invested_value - 100 * 1_000.0) < 1e-6

    def test_equity_consistent_during_suspension(self):
        """equity == cash + carried_value even when a position is suspended."""
        p = Portfolio(cash=500_000)
        p.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        snap = p.mark_to_market(D1, {})
        assert abs(snap.equity - (p.cash + 100 * 1_000.0)) < 1e-6


# ---------------------------------------------------------------------------
# DC4 — MTM uses the prices dict (caller passes close_tr)
# ---------------------------------------------------------------------------


class TestMTMPriceSource:
    """
    Portfolio.mark_to_market uses exactly the values in the prices dict.

    This test documents the contract: the caller (engine) is responsible for
    passing close_tr (total-return adjusted); the portfolio has no internal
    price source.  Passing different values → different equity.
    """

    def test_equity_reflects_passed_price(self):
        p = Portfolio(cash=500_000)
        p.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        snap = p.mark_to_market(D1, {"A": 1_100.0})  # close_tr includes dividend
        assert abs(snap.invested_value - 100 * 1_100.0) < 1e-6

    def test_tr_price_gives_higher_equity_than_plain_price(self):
        """close_tr > close (dividend) → higher equity when using TR prices."""
        p_tr = Portfolio(cash=500_000)
        p_tr.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        snap_tr = p_tr.mark_to_market(D1, {"A": 1_100.0})

        p_price = Portfolio(cash=500_000)
        p_price.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        snap_price = p_price.mark_to_market(D1, {"A": 1_080.0})

        assert snap_tr.equity > snap_price.equity

    def test_snapshot_appended_per_mtm_call(self):
        p = Portfolio(cash=1_000_000)
        for i, d in enumerate([D1, D2, D3]):
            p.mark_to_market(d, {})
            assert len(p.snapshots) == i + 1


# ---------------------------------------------------------------------------
# Position mechanics
# ---------------------------------------------------------------------------


class TestPositionMechanics:
    def test_buy_creates_new_position(self):
        p = Portfolio(cash=1_000_000)
        p.apply_fills([_fill("A", "buy", 100, 500.0)], fill_cost, _ZERO_COST)
        assert "A" in p.positions
        assert abs(p.positions["A"].shares - 100.0) < 1e-9

    def test_sell_removes_full_position(self):
        p = Portfolio(cash=500_000)
        p.positions["A"] = _position(
            "A", shares=100, last_price=500.0, cost_basis=500.0
        )
        p.apply_fills([_fill("A", "sell", 100, 500.0)], fill_cost, _ZERO_COST)
        assert "A" not in p.positions

    def test_trim_reduces_shares(self):
        p = Portfolio(cash=500_000)
        p.positions["A"] = _position("A", shares=200, last_price=500.0)
        p.apply_fills([_fill("A", "trim", 80, 500.0)], fill_cost, _ZERO_COST)
        assert abs(p.positions["A"].shares - 120.0) < 1e-9

    def test_partial_sell_keeps_position(self):
        p = Portfolio(cash=500_000)
        p.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        p.apply_fills([_fill("A", "sell", 40, 1_000.0)], fill_cost, _ZERO_COST)
        assert "A" in p.positions
        assert abs(p.positions["A"].shares - 60.0) < 1e-9

    def test_augment_buy_weighted_average_cost_basis(self):
        p = Portfolio(cash=2_000_000)
        p.apply_fills([_fill("A", "buy", 100, 100.0)], fill_cost, _ZERO_COST)
        assert abs(p.positions["A"].cost_basis - 100.0) < 1e-6
        p.apply_fills([_fill("A", "buy", 100, 200.0)], fill_cost, _ZERO_COST)
        # weighted avg = (100*100 + 100*200) / 200 = 150
        assert abs(p.positions["A"].cost_basis - 150.0) < 1e-6
        assert abs(p.positions["A"].shares - 200.0) < 1e-9

    def test_cost_rolled_into_cost_basis(self):
        """Transaction cost increases cost_basis (making the breakeven higher)."""
        p = Portfolio(cash=1_000_000)
        p.apply_fills([_fill("A", "buy", 100, 1_000.0)], fill_cost, _30BPS)
        # cost = 100*1000 * 15/10000 = 15; basis = (100_000 + 15) / 100 = 1000.15
        assert p.positions["A"].cost_basis > 1_000.0

    def test_cash_decreases_on_buy(self):
        p = Portfolio(cash=1_000_000)
        p.apply_fills([_fill("A", "buy", 100, 1_000.0)], fill_cost, _ZERO_COST)
        assert abs(p.cash - 900_000.0) < 1e-6

    def test_cash_increases_on_sell(self):
        p = Portfolio(cash=0.0)
        p.positions["A"] = _position(
            "A", shares=100, last_price=1_000.0, cost_basis=1_000.0
        )
        p.apply_fills([_fill("A", "sell", 100, 1_000.0)], fill_cost, _ZERO_COST)
        assert abs(p.cash - 100_000.0) < 1e-6

    def test_exposure_calculation(self):
        p = Portfolio(cash=500_000)
        p.positions["A"] = _position("A", shares=100, last_price=1_000.0)
        snap = p.mark_to_market(D1, {"A": 1_000.0})
        # invested = 100_000; equity = 600_000; exposure = 100_000/600_000
        assert abs(snap.exposure - 100_000 / 600_000) < 1e-6

    def test_zero_equity_exposure_is_zero_no_division_error(self):
        p = Portfolio(cash=0.0)
        snap = p.mark_to_market(D1, {})
        assert snap.exposure == 0.0

    def test_sell_nonexistent_position_is_ignored(self):
        p = Portfolio(cash=1_000_000)
        # Should log a warning but not raise
        p.apply_fills([_fill("GHOST", "sell", 100, 500.0)], fill_cost, _ZERO_COST)
        # Cash unchanged (ignored fill)
        assert abs(p.cash - 1_000_000.0) < 1e-6


# ---------------------------------------------------------------------------
# Guard-rail tests
# ---------------------------------------------------------------------------


class TestGuardRails:
    def test_negative_starting_cash_raises(self):
        with pytest.raises(ValueError, match="≥ 0"):
            Portfolio(cash=-1.0)

    def test_unknown_fill_side_raises(self):
        p = Portfolio(cash=1_000_000)
        bad = Fill(
            isin="A",
            symbol="SYM",
            side="short",  # type: ignore[arg-type]
            qty=100,
            price=1_000.0,
            date=D1,
            cost_rupees=0.0,
        )
        with pytest.raises(ValueError, match="Unknown fill side"):
            p.apply_fills([bad], fill_cost, _ZERO_COST)

    def test_entry_date_preserved_on_augment(self):
        p = Portfolio(cash=2_000_000)
        p.apply_fills([_fill("A", "buy", 100, 1_000.0, D1)], fill_cost, _ZERO_COST)
        entry_before = p.positions["A"].entry_date
        p.apply_fills([_fill("A", "buy", 50, 1_100.0, D2)], fill_cost, _ZERO_COST)
        assert (
            p.positions["A"].entry_date == entry_before
        )  # original entry date preserved


# ---------------------------------------------------------------------------
# T6 stub guard
# ---------------------------------------------------------------------------


def test_build_rebalance_plan_empty_portfolio_empty_ranked():
    """build_rebalance_plan with no holdings and no ranked names returns empty plan."""
    from app.backtest_v2.config import MomentumConfig

    p = Portfolio(cash=1_000_000)
    plan = build_rebalance_plan(p, [], 1.0, MomentumConfig())
    assert plan.sells == []
    assert plan.buys == []
    assert plan.trims == []
