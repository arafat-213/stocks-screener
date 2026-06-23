"""
test_whole_shares.py — whole-share (integer) sizing at the apply_fills chokepoint.

NSE equity delivery trades only in whole shares (lot size 1). Portfolio.apply_fills
gained a `whole_shares` flag (threaded from EngineContext.whole_shares); when True it
floors every fill's qty before it touches state. Default False preserves the legacy
fractional behaviour (byte-for-byte parity — covered by the existing t5/t7/t9 suites).

These tests encode the INTENT (Rule 9): an order that cannot exist on NSE (a fraction
of a share) must never reach portfolio state, capital must never be over-deployed by
the flooring, and the cash-conservation identity must continue to hold exactly.
"""

from datetime import date

from app.backtest_v2.costs import CostConfig
from app.backtest_v2.portfolio import Portfolio
from app.backtest_v2.schemas import Fill

_ZERO_COST = CostConfig(round_trip_bps=0.0)
_30BPS = CostConfig(round_trip_bps=30.0)
D1 = date(2024, 1, 2)


def _fill(isin: str, side: str, qty: float, price: float) -> Fill:
    return Fill(
        isin=isin,
        symbol="SYM",
        side=side,
        qty=qty,
        price=price,  # type: ignore[arg-type]
        date=D1,
        cost_rupees=0.0,
    )


def _is_integer(x: float) -> bool:
    return abs(x - round(x)) < 1e-9


def test_buy_qty_floored_to_whole_shares():
    """A fractional target (33.99 shares) buys exactly 33 — never the fraction."""
    p = Portfolio(cash=1_000_000.0)
    p.apply_fills(
        [_fill("A", "buy", 33.99, 100.0)], cost_cfg=_ZERO_COST, whole_shares=True
    )
    assert p.positions["A"].shares == 33.0
    assert _is_integer(p.positions["A"].shares)


def test_default_off_keeps_fractional():
    """Flag defaults OFF ⇒ legacy fractional sizing (parity guarantee)."""
    p = Portfolio(cash=1_000_000.0)
    p.apply_fills([_fill("A", "buy", 33.99, 100.0)], cost_cfg=_ZERO_COST)
    assert p.positions["A"].shares == 33.99


def test_sub_one_share_fill_dropped():
    """A fill that floors to 0 (price > target) cannot transact and is dropped."""
    p = Portfolio(cash=1_000_000.0)
    p.apply_fills(
        [_fill("A", "buy", 0.4, 5000.0)], cost_cfg=_ZERO_COST, whole_shares=True
    )
    assert "A" not in p.positions


def test_flooring_never_over_deploys_cash():
    """Floored buy spends strictly less than (or equal to) the fractional intent —
    cash is never driven negative by the flooring."""
    p = Portfolio(cash=1_000_000.0)
    p.apply_fills(
        [_fill("A", "buy", 99.9, 1000.0)], cost_cfg=_ZERO_COST, whole_shares=True
    )
    assert p.positions["A"].shares == 99.0
    assert p.cash == 1_000_000.0 - 99.0 * 1000.0
    assert p.cash >= 0.0


def test_cash_conservation_identity_holds_with_flooring():
    """equity == cash + Σ shares·last_price still holds exactly after floored fills."""
    p = Portfolio(cash=1_000_000.0)
    p.apply_fills(
        [_fill("A", "buy", 12.7, 250.0), _fill("B", "buy", 8.3, 480.0)],
        cost_cfg=_ZERO_COST,
        whole_shares=True,
    )
    p.mark_to_market(D1, {"A": 250.0, "B": 480.0})
    snap = p.snapshots[-1]
    assert snap.equity == snap.cash + snap.invested_value


def test_whole_share_buy_capped_to_cash_never_negative():
    """Regression (warm-start succession bug): with costs, a floored buy must be capped
    to the cash on hand so re-hydrated cash never goes negative. ₹10,050 buying at ₹1000
    with 30bps round-trip (15bps/side): 10 shares cost 10,015 (fits), 11 cost 11,016.5
    (over) ⇒ capped to exactly 10 shares, cash stays ≥ 0."""
    p = Portfolio(cash=10_050.0)
    p.apply_fills([_fill("A", "buy", 50.0, 1000.0)], cost_cfg=_30BPS, whole_shares=True)
    assert p.positions["A"].shares == 10.0
    assert p.cash >= 0.0


def test_positions_stay_integer_so_full_exit_is_integer():
    """Because every buy/trim is floored, pos.shares stays integer ⇒ a full-position
    sell (qty = pos.shares) is automatically whole too."""
    p = Portfolio(cash=1_000_000.0)
    p.apply_fills(
        [_fill("A", "buy", 50.6, 200.0)], cost_cfg=_ZERO_COST, whole_shares=True
    )
    held = p.positions["A"].shares
    assert _is_integer(held)
    p.apply_fills(
        [_fill("A", "sell", held, 210.0)], cost_cfg=_ZERO_COST, whole_shares=True
    )
    assert "A" not in p.positions
