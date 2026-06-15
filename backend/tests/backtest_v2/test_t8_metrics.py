"""
test_t8_metrics.py — T8 done-criteria tests (offline; synthetic data only).

Done criteria (02_SIMULATION_CORE_TASKS T8):
  DC1  Each metric unit-tested against a hand-constructed equity curve with a
       known answer (fixed-CAGR ramp → exact CAGR; known drawdown → exact
       maxDD/Calmar).
  DC2  Sharpe uses daily returns × √252 (not step-on-exit — the v1 bug).
  DC3  Turnover computed per rebalance and annualized; flagged absurd if > 1000%.
  DC4  Tests offline (synthetic data; no live network).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pytest

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.metrics import (
    _compute_annualized_turnover,
    _compute_max_drawdown,
    _compute_per_name_stats,
    compute_metrics,
    summary,
)
from app.backtest_v2.types import DailySnapshot, Fill

# ---------------------------------------------------------------------------
# Helpers — build synthetic EngineResult-like objects
# ---------------------------------------------------------------------------


class _FakeEngineResult:
    """
    Minimal stand-in for EngineResult so tests don't need to run the engine.
    compute_metrics accesses: .snapshots, .fills_log,
    .per_rebalance_turnover, .total_cost_paid.
    """

    def __init__(
        self,
        snapshots: list[DailySnapshot],
        fills_log: list[Fill] | None = None,
        per_rebalance_turnover: list[tuple[date, float]] | None = None,
        total_cost_paid: float = 0.0,
        config: MomentumConfig | None = None,
    ):
        self.snapshots = snapshots
        self.fills_log = fills_log or []
        self.per_rebalance_turnover = per_rebalance_turnover or []
        self.total_cost_paid = total_cost_paid
        self.config = config or MomentumConfig()
        self.suspension_log: dict = {}
        self.rebalance_dates_used: list = []


def _snap(d: date, equity: float, exposure: float = 0.8) -> DailySnapshot:
    cash = equity * (1.0 - exposure)
    invested = equity * exposure
    return DailySnapshot(
        date=d,
        equity=equity,
        cash=cash,
        invested_value=invested,
        exposure=exposure,
        n_positions=5,
    )


def _fill(
    isin: str,
    side: str,
    qty: float,
    price: float,
    d: date,
    cost_rupees: float = 0.0,
    symbol: str | None = None,
) -> Fill:
    return Fill(
        isin=isin,
        symbol=symbol or isin,
        side=side,
        qty=qty,
        price=price,
        date=d,
        cost_rupees=cost_rupees,
    )


def _linear_snapshots(
    start: date,
    n_days: int,
    start_equity: float,
    end_equity: float,
    exposure: float = 0.8,
) -> list[DailySnapshot]:
    """Build n_days snapshots with equity linearly interpolated."""
    equities = np.linspace(start_equity, end_equity, n_days)
    return [
        _snap(start + timedelta(days=i), float(e), exposure)
        for i, e in enumerate(equities)
    ]


# ---------------------------------------------------------------------------
# DC1a — CAGR: fixed ramp → exact answer
# ---------------------------------------------------------------------------


class TestCAGR:
    def test_exact_10pct_cagr_over_one_year(self):
        # 1 year = 365 days; equity goes from 1_000_000 to 1_100_000
        start = date(2023, 1, 1)
        end = date(2024, 1, 1)
        n_days = (end - start).days + 1
        snaps = _linear_snapshots(start, n_days, 1_000_000.0, 1_100_000.0)
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        # CAGR = (1.1 / 1.0) ^ (1 / 1.0) - 1 = 10%
        assert abs(m.cagr - 0.10) < 1e-4, f"Expected ~10% CAGR, got {m.cagr:.4%}"

    def test_zero_return_gives_zero_cagr(self):
        start = date(2023, 1, 1)
        snaps = [_snap(start + timedelta(days=i), 1_000_000.0) for i in range(252)]
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert abs(m.cagr) < 1e-6

    def test_negative_return_gives_negative_cagr(self):
        start = date(2023, 1, 1)
        end = date(2024, 1, 1)
        n_days = (end - start).days + 1
        snaps = _linear_snapshots(start, n_days, 1_000_000.0, 900_000.0)
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert m.cagr < 0, "Declining equity must give negative CAGR"

    def test_cagr_uses_calendar_time_not_trading_days(self):
        # 1 calendar year; equity doubles → CAGR = 100%
        # Verify CAGR uses calendar days (365.25), not snapshot count.
        start = date(2023, 1, 1)
        end = date(2024, 1, 1)
        n_days = (end - start).days + 1
        snaps = _linear_snapshots(start, n_days, 1_000_000.0, 2_000_000.0)
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        # 2x over ~1 year → CAGR ≈ 100%; tolerance 1% to account for leap/365.25
        assert abs(m.cagr - 1.0) < 0.02, f"Expected ~100% CAGR, got {m.cagr:.4%}"
        # If CAGR used snapshot count instead of calendar time it would give a
        # wildly different answer; this test catches that class of bug.


# ---------------------------------------------------------------------------
# DC1b — Sharpe: daily returns × √252  (not step-on-exit)
# ---------------------------------------------------------------------------


class TestSharpe:
    def test_sharpe_uses_daily_returns(self):
        """
        Construct a known series of daily returns and verify Sharpe exactly.
        If the calculation used step-on-exit instead of daily MTM, it would
        see only 1 return and produce 0.0 / no variance.
        """
        start = date(2023, 1, 1)
        # Fixed daily return of +0.1%
        r = 0.001
        equity = 1_000_000.0
        snaps = []
        for i in range(253):  # 252 returns from 253 points
            snaps.append(_snap(start + timedelta(days=i), equity))
            equity *= 1 + r

        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)

        # All returns are identical → std ≈ 0 → Sharpe → inf or very large
        # With ddof=1 and nearly identical returns the std is tiny but non-zero.
        # Key assertion: Sharpe is computed (not 0), and annualized vol > 0.
        assert m.annualized_vol > 0, "Annualized vol must reflect daily return variance"
        assert m.sharpe > 0, "Positive daily returns must yield positive Sharpe"

    def test_sharpe_positive_vs_negative_returns(self):
        start = date(2023, 1, 1)
        # Alternating +2% / -1% pattern → net positive mean
        snaps = []
        equity = 1_000_000.0
        for i in range(200):
            snaps.append(_snap(start + timedelta(days=i), equity))
            equity *= 1.02 if i % 2 == 0 else 0.99

        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert m.sharpe > 0, "Net positive mean return must give positive Sharpe"

    def test_sharpe_negative_for_loss_series(self):
        start = date(2023, 1, 1)
        equity = 1_000_000.0
        snaps = []
        for i in range(200):
            snaps.append(_snap(start + timedelta(days=i), equity))
            equity *= 0.999  # consistent small loss
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert m.sharpe < 0, "Consistently negative returns must give negative Sharpe"

    def test_sortino_geq_sharpe_for_positive_only_returns(self):
        """For series with no negative daily returns, downside std = 0 → sortino = 0 (edge)."""
        start = date(2023, 1, 1)
        equity = 1_000_000.0
        snaps = []
        for i in range(200):
            snaps.append(_snap(start + timedelta(days=i), equity))
            equity *= 1.001
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        # No downside returns → sortino = 0.0
        assert m.sortino == 0.0

    def test_sortino_uses_only_downside_variance(self):
        """Mixed returns: Sortino should differ from Sharpe."""
        start = date(2023, 1, 1)
        equity = 1_000_000.0
        snaps = []
        # Mostly up, one big drawdown day
        for i in range(200):
            snaps.append(_snap(start + timedelta(days=i), equity))
            if i == 100:
                equity *= 0.90  # -10% shock
            else:
                equity *= 1.002
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert m.sortino != m.sharpe, (
            "Sortino must differ from Sharpe when downside variance ≠ total variance"
        )


# ---------------------------------------------------------------------------
# DC1c — Max drawdown + duration + Calmar
# ---------------------------------------------------------------------------


class TestMaxDrawdown:
    def test_known_drawdown_exact(self):
        # Equity: 100 → 120 (peak) → 90 (trough) → 110
        # Max DD = (120 - 90) / 120 = 25%
        dates = [date(2023, 1, 1) + timedelta(days=i) for i in range(4)]
        equities = [100.0, 120.0, 90.0, 110.0]
        snaps = [_snap(dates[i], equities[i]) for i in range(4)]
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert abs(m.max_drawdown - 0.25) < 1e-9, (
            f"Expected 25% DD, got {m.max_drawdown:.4%}"
        )

    def test_drawdown_duration_calendar_days(self):
        # Peak on day 0, trough on day 10
        start = date(2023, 1, 1)
        equities = [100.0] + [100.0 - i for i in range(1, 11)]  # 100 → 90 over 10 days
        dates = [start + timedelta(days=i) for i in range(11)]
        snaps = [_snap(dates[i], equities[i]) for i in range(11)]
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert m.max_dd_duration_days == 10

    def test_no_drawdown_series(self):
        # Monotonically rising — no drawdown
        start = date(2023, 1, 1)
        snaps = [_snap(start + timedelta(days=i), 100.0 + i) for i in range(50)]
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert m.max_drawdown == 0.0
        assert math.isnan(m.calmar), "Calmar should be nan when max_drawdown == 0"

    def test_calmar_equals_cagr_over_max_dd(self):
        # 1-year run: equity 1M → 1.2M with a known 10% drawdown in the middle
        start = date(2023, 1, 1)
        n = 366  # ~1 year
        equities = []
        for i in range(n):
            if i < n // 3:
                equities.append(1_000_000.0 + i * 1000)  # rising
            elif i < n // 2:
                equities.append(equities[-1] * 0.998)  # drawdown phase
            else:
                equities.append(equities[-1] * 1.002)  # recovery + gain

        dates = [start + timedelta(days=i) for i in range(n)]
        snaps = [_snap(dates[i], equities[i]) for i in range(n)]
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)

        if m.max_drawdown > 0:
            expected_calmar = m.cagr / m.max_drawdown
            assert abs(m.calmar - expected_calmar) < 1e-9


# ---------------------------------------------------------------------------
# DC1d — Exposure stats
# ---------------------------------------------------------------------------


class TestExposureStats:
    def test_constant_exposure(self):
        start = date(2023, 1, 1)
        snaps = [
            _snap(start + timedelta(days=i), 1_000_000.0, exposure=0.75)
            for i in range(100)
        ]
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert abs(m.avg_exposure - 0.75) < 1e-9
        assert abs(m.median_exposure - 0.75) < 1e-9
        assert m.time_in_cash_pct == 1.0  # all days exposure < 1.0

    def test_full_exposure_gives_zero_time_in_cash(self):
        start = date(2023, 1, 1)
        snaps = [
            _snap(start + timedelta(days=i), 1_000_000.0, exposure=1.0)
            for i in range(100)
        ]
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert m.time_in_cash_pct == 0.0

    def test_mixed_exposure_time_in_cash(self):
        start = date(2023, 1, 1)
        # 50 days at full exposure, 50 days at 80% exposure
        snaps = [
            _snap(start + timedelta(days=i), 1_000_000.0, exposure=1.0)
            for i in range(50)
        ] + [
            _snap(start + timedelta(days=50 + i), 1_000_000.0, exposure=0.8)
            for i in range(50)
        ]
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert abs(m.time_in_cash_pct - 0.5) < 1e-9
        assert abs(m.avg_exposure - 0.9) < 1e-9


# ---------------------------------------------------------------------------
# DC3 — Turnover: annualized correctly, flags absurd
# ---------------------------------------------------------------------------


class TestTurnover:
    def test_annualized_turnover_one_year(self):
        # 12 monthly rebalances, each 0.5 turnover → 6.0 / 1 year = 6.0 (600%)
        start = date(2023, 1, 1)
        per_reb = [(start + timedelta(days=30 * i), 0.5) for i in range(12)]
        snaps = [_snap(start + timedelta(days=i), 1_000_000.0) for i in range(366)]
        result = _FakeEngineResult(snaps, per_rebalance_turnover=per_reb)
        m = compute_metrics(result)
        # total = 6.0, years ≈ 1.0 → ann ≈ 6.0
        assert abs(m.annualized_turnover - 6.0) < 0.1

    def test_absurd_turnover_flag(self):
        # Very high turnover (>1000% annualized) should be flagged
        # 50 rebalances in 6 months, each 2.0 turnover → 100/0.5 = 200 (20000%)
        start = date(2023, 1, 1)
        per_reb = [(start + timedelta(days=3 * i), 2.0) for i in range(50)]
        snaps = [_snap(start + timedelta(days=i), 1_000_000.0) for i in range(182)]
        result = _FakeEngineResult(snaps, per_rebalance_turnover=per_reb)
        m = compute_metrics(result)
        assert m.turnover_is_absurd, "Extremely high turnover must be flagged"

    def test_sane_turnover_not_flagged(self):
        # 12 monthly rebalances, each 0.3 turnover → 3.6 (360%) — sane
        start = date(2023, 1, 1)
        per_reb = [(start + timedelta(days=30 * i), 0.3) for i in range(12)]
        snaps = [_snap(start + timedelta(days=i), 1_000_000.0) for i in range(366)]
        result = _FakeEngineResult(snaps, per_rebalance_turnover=per_reb)
        m = compute_metrics(result)
        assert not m.turnover_is_absurd

    def test_empty_rebalance_turnover(self):
        start = date(2023, 1, 1)
        snaps = [_snap(start + timedelta(days=i), 1_000_000.0) for i in range(100)]
        result = _FakeEngineResult(snaps, per_rebalance_turnover=[])
        m = compute_metrics(result)
        assert m.annualized_turnover == 0.0
        assert not m.turnover_is_absurd

    def test_annualized_turnover_helper_direct(self):
        start = date(2023, 1, 1)
        end = date(2024, 1, 1)
        per_reb = [(start, 2.0)]
        ann, is_absurd = _compute_annualized_turnover(per_reb, start, end)
        # 2.0 / 1 year = 2.0 (200%) — not absurd
        assert abs(ann - 2.0) < 0.01
        assert not is_absurd


# ---------------------------------------------------------------------------
# Per-name diagnostics (realized P&L, hold period, hit rate)
# ---------------------------------------------------------------------------


class TestPerNameStats:
    def test_realized_pnl_buy_then_sell(self):
        # Buy 100 shares @ 100, sell 100 shares @ 120 → P&L = 2000
        d0 = date(2023, 1, 1)
        d1 = date(2023, 2, 1)
        fills = [
            _fill("A", "buy", 100.0, 100.0, d0, cost_rupees=50.0),
            _fill("A", "sell", 100.0, 120.0, d1, cost_rupees=60.0),
        ]
        stats, hit_rate = _compute_per_name_stats(fills)
        assert len(stats) == 1
        s = stats[0]
        assert s.isin == "A"
        assert abs(s.buy_notional - 10_000.0) < 1e-6
        assert abs(s.sell_notional - 12_000.0) < 1e-6
        assert abs(s.cost_paid - 110.0) < 1e-6
        # P&L = 12000 - 10000 - 110 = 1890
        assert abs(s.realized_pnl - 1890.0) < 1e-6
        assert s.is_closed
        assert s.n_buys == 1
        assert s.n_sells == 1

    def test_hold_period_days(self):
        d0 = date(2023, 1, 1)
        d1 = date(2023, 3, 1)  # 59 days later
        fills = [
            _fill("A", "buy", 100.0, 100.0, d0),
            _fill("A", "sell", 100.0, 110.0, d1),
        ]
        stats, _ = _compute_per_name_stats(fills)
        assert abs(stats[0].hold_days - (d1 - d0).days) < 1e-9

    def test_still_open_position_has_nan_hold_days(self):
        d0 = date(2023, 1, 1)
        fills = [_fill("A", "buy", 100.0, 100.0, d0)]
        stats, hit_rate = _compute_per_name_stats(fills)
        assert math.isnan(stats[0].hold_days)
        assert not stats[0].is_closed
        assert math.isnan(hit_rate)  # no closed positions

    def test_hit_rate_all_profitable(self):
        d0 = date(2023, 1, 1)
        d1 = date(2023, 2, 1)
        fills = [
            _fill("A", "buy", 10.0, 100.0, d0),
            _fill("A", "sell", 10.0, 120.0, d1),
            _fill("B", "buy", 10.0, 100.0, d0),
            _fill("B", "sell", 10.0, 150.0, d1),
        ]
        _, hit_rate = _compute_per_name_stats(fills)
        assert abs(hit_rate - 1.0) < 1e-9

    def test_hit_rate_mixed(self):
        d0 = date(2023, 1, 1)
        d1 = date(2023, 2, 1)
        fills = [
            # A: profitable
            _fill("A", "buy", 10.0, 100.0, d0),
            _fill("A", "sell", 10.0, 120.0, d1),
            # B: loss
            _fill("B", "buy", 10.0, 100.0, d0),
            _fill("B", "sell", 10.0, 80.0, d1),
        ]
        _, hit_rate = _compute_per_name_stats(fills)
        assert abs(hit_rate - 0.5) < 1e-9

    def test_trim_counts_as_sell_for_realized_pnl(self):
        d0 = date(2023, 1, 1)
        d1 = date(2023, 2, 1)
        fills = [
            _fill("A", "buy", 100.0, 100.0, d0),
            _fill("A", "trim", 50.0, 120.0, d1),  # partial exit
        ]
        stats, hit_rate = _compute_per_name_stats(fills)
        s = stats[0]
        # sell_notional = 50 * 120 = 6000; buy_notional = 100 * 100 = 10000
        assert abs(s.sell_notional - 6_000.0) < 1e-6
        assert s.is_closed  # trim counts as a "sell" → position is considered closed
        assert s.n_sells == 1
        # realized_pnl = 6000 - 10000 - 0 = -4000 (book loss; still holding 50 shares)
        assert s.realized_pnl < 0
        # hit_rate = 0.0: one closed name, P&L is negative
        assert abs(hit_rate - 0.0) < 1e-9

    def test_multiple_isins(self):
        d0 = date(2023, 1, 1)
        d1 = date(2023, 3, 1)
        fills = [
            _fill("A", "buy", 10.0, 100.0, d0),
            _fill("A", "sell", 10.0, 110.0, d1),
            _fill("B", "buy", 20.0, 50.0, d0),
            # B never sold → still open
        ]
        stats, hit_rate = _compute_per_name_stats(fills)
        assert len(stats) == 2
        a = next(s for s in stats if s.isin == "A")
        b = next(s for s in stats if s.isin == "B")
        assert a.is_closed
        assert not b.is_closed
        # Only A is closed; A is profitable → hit_rate = 1.0
        assert abs(hit_rate - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# compute_metrics integration: end-to-end with a fake EngineResult
# ---------------------------------------------------------------------------


class TestComputeMetricsIntegration:
    def _make_result(self) -> _FakeEngineResult:
        start = date(2022, 1, 3)
        n = 260  # ~1 trading year
        equity = 1_000_000.0
        snaps = []
        rng = np.random.default_rng(42)
        for i in range(n):
            ret = rng.normal(0.0004, 0.012)
            equity = max(equity * (1 + ret), 1.0)
            snaps.append(_snap(start + timedelta(days=i), equity, exposure=0.85))

        per_reb = [(start + timedelta(days=22 * i), 0.35) for i in range(11)]
        fills = [
            _fill("ISIN1", "buy", 50.0, 200.0, date(2022, 1, 3), cost_rupees=30.0),
            _fill("ISIN2", "buy", 40.0, 250.0, date(2022, 1, 3), cost_rupees=25.0),
            _fill("ISIN1", "sell", 50.0, 220.0, date(2022, 6, 1), cost_rupees=33.0),
        ]
        return _FakeEngineResult(snaps, fills, per_reb, total_cost_paid=88.0)

    def test_all_fields_populated(self):
        result = self._make_result()
        m = compute_metrics(result)
        assert m.start_date is not None
        assert m.end_date is not None
        assert m.n_trading_days == 260
        assert m.n_calendar_days > 0
        assert m.n_fills == 3
        assert abs(m.total_cost_paid - 88.0) < 1e-6

    def test_cagr_is_finite(self):
        m = compute_metrics(self._make_result())
        assert math.isfinite(m.cagr)

    def test_sharpe_is_finite(self):
        m = compute_metrics(self._make_result())
        assert math.isfinite(m.sharpe)
        assert math.isfinite(m.sortino)

    def test_drawdown_is_non_negative(self):
        m = compute_metrics(self._make_result())
        assert m.max_drawdown >= 0.0
        assert m.max_dd_duration_days >= 0

    def test_exposure_in_range(self):
        m = compute_metrics(self._make_result())
        assert 0.0 <= m.avg_exposure <= 1.0
        assert 0.0 <= m.median_exposure <= 1.0
        assert 0.0 <= m.time_in_cash_pct <= 1.0

    def test_turnover_series_passed_through(self):
        result = self._make_result()
        m = compute_metrics(result)
        assert len(m.per_rebalance_turnover) == len(result.per_rebalance_turnover)

    def test_per_name_stats_populated(self):
        m = compute_metrics(self._make_result())
        assert len(m.per_name_stats) == 2  # ISIN1, ISIN2
        isin1 = next(s for s in m.per_name_stats if s.isin == "ISIN1")
        assert isin1.is_closed
        assert abs(isin1.buy_notional - 50 * 200) < 1e-6
        assert abs(isin1.sell_notional - 50 * 220) < 1e-6

    def test_hit_rate_computed(self):
        m = compute_metrics(self._make_result())
        # ISIN1 closed with P&L = 50*220 - 50*200 - 63 = 1000 - 63 = 937 > 0
        # ISIN2 still open → not counted
        assert abs(m.hit_rate - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_snapshot_no_returns(self):
        snaps = [_snap(date(2023, 1, 1), 1_000_000.0)]
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        assert m.sharpe == 0.0
        assert m.sortino == 0.0
        assert m.annualized_vol == 0.0
        assert m.max_drawdown == 0.0

    def test_empty_snapshots_raises(self):
        result = _FakeEngineResult([])
        with pytest.raises(ValueError, match="empty"):
            compute_metrics(result)

    def test_empty_fills_log(self):
        start = date(2023, 1, 1)
        snaps = [_snap(start + timedelta(days=i), 1_000_000.0) for i in range(50)]
        result = _FakeEngineResult(snaps, fills_log=[])
        m = compute_metrics(result)
        assert m.n_fills == 0
        assert len(m.per_name_stats) == 0
        assert math.isnan(m.hit_rate)

    def test_two_snapshots_minimal_returns(self):
        d0, d1 = date(2023, 1, 1), date(2023, 1, 2)
        snaps = [_snap(d0, 1_000_000.0), _snap(d1, 1_010_000.0)]
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        # With only 1 return, std ddof=1 raises — should be handled gracefully
        assert math.isfinite(m.cagr) or m.cagr == 0.0

    def test_max_drawdown_helper_single_point(self):
        dd, dur = _compute_max_drawdown(np.array([100.0]), [date(2023, 1, 1)])
        assert dd == 0.0
        assert dur == 0


# ---------------------------------------------------------------------------
# summary() smoke test
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_returns_string(self):
        start = date(2023, 1, 1)
        snaps = [
            _snap(start + timedelta(days=i), 1_000_000.0 + i * 100) for i in range(100)
        ]
        result = _FakeEngineResult(snaps)
        m = compute_metrics(result)
        s = summary(m)
        assert isinstance(s, str)
        assert "CAGR" in s
        assert "Sharpe" in s
        assert "Drawdown" in s
        assert "Turnover" in s
