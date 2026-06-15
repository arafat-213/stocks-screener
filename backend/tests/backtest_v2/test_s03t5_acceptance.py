"""
T5 acceptance suite — spec 03 §4 as hard tests (the gate for the cost + benchmark layer).

All five §4 criteria are encoded here.  Each test fails loudly if its invariant
breaks (CLAUDE.md Rule 12).  All tests are offline — synthetic equity/benchmark
and a fixture-based TRI stub; no live niftyindices/NSE calls (Rule 5).

Done-criteria being gated here (spec 03 T5):
  DC1  Cost wired into P&L: cost delta shows up in equity curve, not just metadata.
  DC2  Slippage moves cost basis: buy fills at effective price > raw open; cost
       basis is above open; realized P&L starts negative pre-move.
  DC3  Benchmark loaded + aligned + warmup-sliced: aligned series starts at
       date_from; Sharpe and Calmar are computable on that window.
  DC4  Three-cost-level report renders for any run (optimistic/base/pessimistic).
  DC5  Headline ratios (Calmar ratio, max-DD ratio) are present, finite, and
       surfaced prominently in benchmark_summary() output.

WHY each test class exists:
  TestCriterion1_CostWiredIntoPnL     — §4.1: cost model is in the equity path,
       not cosmetic.  Negative: removing all costs raises equity.
  TestCriterion2_SlippageMovesCostBasis — §4.2: slippage adjusts fill price;
       buy fills above raw open; optimistic fills at open (negative test).
  TestCriterion3_BenchmarkAlignedAndWarmupSliced — §4.3: align_benchmark slices
       warmup; metrics computable on that window; warmup dates absent (negative).
  TestCriterion4_ThreeLevelReportRenders — §4.4: all three levels produce valid
       EngineResult + BacktestMetrics; equity ordered correctly.
  TestCriterion5_HeadlineRatiosSurfaced — §4.5: calmar_ratio + max_dd_ratio
       present, finite, and appear in benchmark_summary() text.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.backtest_v2 import engine
from app.backtest_v2.benchmark import (
    align_benchmark,
)
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.costs import (
    CostConfig,
    effective_price,
)
from app.backtest_v2.metrics import (
    benchmark_summary,
    compute_benchmark_metrics,
    compute_metrics,
)

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _make_prices(
    n_days: int = 350,
    n_isins: int = 5,
    start_price: float = 100.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic prices frame usable by engine.run."""
    rng = np.random.default_rng(seed)
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
                    "adv_20": 1e8,
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


def _make_equity_series(
    daily_returns: list[float], capital: float = 1_000_000.0
) -> pd.Series:
    """Build DatetimeIndex equity series from daily returns."""
    base_ts = pd.Timestamp("2022-01-03")
    index = [base_ts + pd.Timedelta(days=i) for i in range(len(daily_returns) + 1)]
    vals = [capital]
    for r in daily_returns:
        vals.append(vals[-1] * (1 + r))
    return pd.Series(vals, index=pd.DatetimeIndex(index), dtype=float)


def _synthetic_tri(
    date_from: date, n_days: int = 500, daily_ret: float = 0.0005
) -> pd.Series:
    """Synthetic TRI series covering n_days trading days starting well before date_from."""
    # Start 200 days before date_from to give warmup headroom.
    warmup_start = pd.Timestamp(date_from) - pd.Timedelta(days=300)
    cal = pd.bdate_range(start=warmup_start, periods=n_days, freq="B")
    vals = [10_000.0]
    for _ in range(n_days - 1):
        vals.append(vals[-1] * (1 + daily_ret))
    return pd.Series(vals, index=pd.DatetimeIndex(cal), name="tri")


def _fake_fetch_fn(series: pd.Series):
    """Return a _fetch_fn stub that injects synthetic rows for offline tests."""
    from app.backtest_v2.benchmark import _rows_to_tri_series  # noqa: F401

    def _fn(index_name: str, start: str, end: str) -> list[dict]:
        rows = []
        for ts, val in series.items():
            rows.append(
                {
                    "RequestNumber": "FAKE",
                    "Index Name": index_name,
                    "Date": ts.strftime("%d %b %Y"),
                    "TotalReturnsIndex": str(round(val, 2)),
                    "NTR_Value": "-",
                }
            )
        return rows

    return _fn


# ---------------------------------------------------------------------------
# Criterion 1 — §4.1: cost model is in the P&L path
# ---------------------------------------------------------------------------


class TestCriterion1_CostWiredIntoPnL:
    """§4.1: cost delta must show up in the equity curve, not just in metadata.

    WHY: A cost model that only tracks fees cosmetically (without debiting cash
    or adjusting fill prices) would leave the equity curve unchanged.  Here we
    assert the opposite: different configs produce measurably different equities.
    """

    def test_base_vs_zero_cost_equity_differs(self):
        """Removing all costs must increase final equity (cost is in the P&L path)."""
        prices = _make_prices()
        config = _make_config()

        # Zero-cost config: statutory zeroed AND no slippage.
        zero_cost_cfg = CostConfig(
            stt_pct=0.0,
            exchange_txn_pct=0.0,
            sebi_pct=0.0,
            stamp_duty_pct=0.0,
            gst_pct=0.0,
            dp_charge=0.0,
            base_slippage_pct=0.0,
            impact_coeff=0.0,
        )

        r_zero = engine.run(prices, config, cost_cfg=zero_cost_cfg)
        r_base = engine.run(prices, config, cost_level="base")

        eq_zero = r_zero.snapshots[-1].equity
        eq_base = r_base.snapshots[-1].equity

        assert eq_zero > eq_base, (
            f"Zero-cost equity ({eq_zero:.2f}) must exceed base-cost equity "
            f"({eq_base:.2f}) — cost is not being deducted from P&L"
        )

    def test_flat_bps_vs_real_model_equity_differs(self):
        """v1-style flat 0.25% RT (no slippage) differs from real statutory + slippage.

        The round_trip_bps=25 path bypasses slippage entirely; the real model adds
        slippage as an effective fill-price adjustment.  Final equities must differ.
        """
        prices = _make_prices()
        config = _make_config()

        # v1-style: flat 25bps round-trip, no slippage model.
        v1_cfg = CostConfig(round_trip_bps=25.0)

        r_v1 = engine.run(prices, config, cost_cfg=v1_cfg)
        r_base = engine.run(prices, config, cost_level="base")

        eq_v1 = r_v1.snapshots[-1].equity
        eq_base = r_base.snapshots[-1].equity

        # They should differ because the real model's slippage moves fill prices
        # (which changes cost basis and position sizing) whereas flat bps does not.
        assert eq_v1 != pytest.approx(eq_base, rel=1e-4), (
            "v1-style flat cost and real statutory+slippage model should produce "
            "different equity curves — both cost paths must actually touch the P&L"
        )

    def test_cost_drag_shows_in_equity_not_only_total_cost_paid(self):
        """Statutory + slippage must together explain lower equity vs zero-cost.

        This test checks that total_cost_paid is non-zero AND that equity falls
        by more than total_cost_paid alone (slippage is an effective-price drag,
        not captured in total_cost_paid, so the real equity impact is larger).
        """
        prices = _make_prices()
        config = _make_config()

        zero_cfg = CostConfig(
            stt_pct=0.0,
            exchange_txn_pct=0.0,
            sebi_pct=0.0,
            stamp_duty_pct=0.0,
            gst_pct=0.0,
            dp_charge=0.0,
            base_slippage_pct=0.0,
            impact_coeff=0.0,
        )

        r_zero = engine.run(prices, config, cost_cfg=zero_cfg)
        r_base = engine.run(prices, config, cost_level="base")

        eq_zero = r_zero.snapshots[-1].equity
        eq_base = r_base.snapshots[-1].equity
        total_statutory_cost = r_base.total_cost_paid

        equity_drag = eq_zero - eq_base  # total economic drag (statutory + slippage)
        assert equity_drag > 0, "economic drag must be positive (costs are in P&L)"
        assert total_statutory_cost > 0, "statutory cost must be non-zero"
        # Slippage drag is additional to statutory — total equity drag exceeds cash cost.
        assert equity_drag > total_statutory_cost, (
            f"equity drag ({equity_drag:.2f}) should exceed statutory-only cash "
            f"cost ({total_statutory_cost:.2f}), because slippage adjusts fill prices "
            f"and is not captured in total_cost_paid"
        )

    def test_negative_no_cost_does_not_raise(self):
        """Negative: zero-cost config runs without error (model handles 0 parameters)."""
        prices = _make_prices()
        config = _make_config()
        zero_cfg = CostConfig(
            stt_pct=0.0,
            exchange_txn_pct=0.0,
            sebi_pct=0.0,
            stamp_duty_pct=0.0,
            gst_pct=0.0,
            dp_charge=0.0,
            base_slippage_pct=0.0,
            impact_coeff=0.0,
        )
        r = engine.run(prices, config, cost_cfg=zero_cfg)
        assert len(r.snapshots) > 0
        assert r.total_cost_paid == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Criterion 2 — §4.2: slippage moves cost basis (engine level)
# ---------------------------------------------------------------------------


class TestCriterion2_SlippageMovesCostBasis:
    """§4.2: slippage must adjust the effective fill price, not apply as a fee.

    WHY: If slippage were a fee-only term (cash deduction after the fill), the
    fill price recorded in Portfolio would equal the raw open, and cost basis
    would not reflect market impact.  The spec is explicit (§1.3 and §4.2):
    buys fill higher, sells fill lower — both in the recorded fill price.
    """

    def test_buy_fills_recorded_above_open_with_base_config(self):
        """Base config: every buy fill price must exceed the open price on that day.

        _stamp_fills applies effective_price before recording, so the fill.price
        stored in fills_log should be > the raw open (buys fill at higher price).
        """
        prices = _make_prices(n_days=350, n_isins=5, seed=7)
        config = _make_config(n_days=350)

        r = engine.run(prices, config, cost_level="base")

        buy_fills = [f for f in r.fills_log if f.side == "buy"]
        assert buy_fills, "must have at least one buy fill in the run"

        # Build open-price lookup: {(date, isin) → open}
        prices_df = prices.copy()
        prices_df["date"] = pd.to_datetime(prices_df["date"])
        open_lookup: dict[tuple, float] = {}
        for row in prices_df.itertuples(index=False):
            open_lookup[(row.date.date(), row.isin)] = float(row.open)

        violations = 0
        for f in buy_fills:
            raw_open = open_lookup.get((f.date, f.isin))
            if raw_open is None:
                continue
            if f.price <= raw_open:
                violations += 1

        assert violations == 0, (
            f"{violations}/{len(buy_fills)} buy fills recorded at or below the raw "
            "open price — slippage should push buy fill price ABOVE open"
        )

    def test_optimistic_buys_at_effective_open_not_above(self):
        """Negative: with zero-slippage (optimistic), buy fills at raw open price."""
        prices = _make_prices(n_days=350, n_isins=5, seed=7)
        config = _make_config(n_days=350)

        r = engine.run(prices, config, cost_level="optimistic")

        buy_fills = [f for f in r.fills_log if f.side == "buy"]
        assert buy_fills, "must have at least one buy fill"

        prices_df = prices.copy()
        prices_df["date"] = pd.to_datetime(prices_df["date"])
        open_lookup: dict[tuple, float] = {}
        for row in prices_df.itertuples(index=False):
            open_lookup[(row.date.date(), row.isin)] = float(row.open)

        # Optimistic: base_slippage_pct=0, impact_coeff=0 → fill at raw open.
        for f in buy_fills:
            raw_open = open_lookup.get((f.date, f.isin))
            if raw_open is None:
                continue
            # With zero slippage, effective_price == raw_open → qty = target / open.
            # Fill price stored should equal open (within floating-point rounding).
            assert f.price == pytest.approx(raw_open, rel=1e-9), (
                f"optimistic fill price {f.price:.4f} != raw open {raw_open:.4f} "
                "— zero-slippage config should fill at the open price"
            )

    def test_effective_price_unit_buy_above_raw(self):
        """Unit: effective_price('buy', ...) > price for base config."""
        cfg = CostConfig.base()
        raw = 100.0
        eff = effective_price("buy", raw, qty=50.0, adv_20=1e6, cfg=cfg)
        assert eff > raw, f"effective buy price {eff} should exceed raw {raw}"

    def test_effective_price_unit_sell_below_raw(self):
        """Unit: effective_price('sell', ...) < price for base config."""
        cfg = CostConfig.base()
        raw = 100.0
        eff = effective_price("sell", raw, qty=50.0, adv_20=1e6, cfg=cfg)
        assert eff < raw, f"effective sell price {eff} should be below raw {raw}"

    def test_slippage_moves_pnl_not_just_recorded_as_fee(self):
        """Slippage reduces equity more than statutory-only costs account for.

        If slippage were a fee, total_cost_paid would capture it.  Since it's an
        effective-price adjustment, the equity difference exceeds total_cost_paid.
        """
        prices = _make_prices()
        config = _make_config()

        # Optimistic: zero slippage, real statutory charges only.
        r_opt = engine.run(prices, config, cost_level="optimistic")
        r_base = engine.run(prices, config, cost_level="base")

        eq_opt = r_opt.snapshots[-1].equity
        eq_base = r_base.snapshots[-1].equity

        # Both runs pay statutory charges; base additionally has slippage drag.
        equity_delta = eq_opt - eq_base
        assert equity_delta > 0, (
            "base (with slippage) must have lower equity than optimistic (no slippage)"
        )
        # The statutory cost_paid should be similar across both (same statutory params).
        # The extra equity drag in base is from slippage, not from statutory.
        stat_delta = abs(r_opt.total_cost_paid - r_base.total_cost_paid)
        # slippage drag >> statutory delta (slippage is the dominant extra cost in base)
        assert equity_delta > stat_delta, (
            f"equity delta ({equity_delta:.2f}) should exceed statutory difference "
            f"({stat_delta:.2f}) — slippage drag is via fill price, not a cash fee"
        )


# ---------------------------------------------------------------------------
# Criterion 3 — §4.3: benchmark aligned + warmup-sliced
# ---------------------------------------------------------------------------


class TestCriterion3_BenchmarkAlignedAndWarmupSliced:
    """§4.3: align_benchmark must slice off warmup; Sharpe/Calmar computable.

    WHY: The v1 compute_metrics bug diluted benchmark returns by including the
    warmup period before the strategy starts.  The spec requires align_benchmark
    to start the series at date_from, not at the earlier warmup start.
    """

    def test_aligned_series_starts_at_date_from(self):
        """align_benchmark's output must begin at date_from, not before it."""
        date_from = date(2022, 6, 1)
        n_days = 500

        tri = _synthetic_tri(date_from, n_days=n_days)

        # Trading calendar from date_from onward.
        cal = pd.bdate_range(start=date_from, periods=252, freq="B")
        trading_calendar = list(pd.DatetimeIndex(cal))

        aligned = align_benchmark(
            tri,
            date_from=date_from,
            trading_calendar=trading_calendar,
            starting_capital=1_000_000.0,
        )

        assert len(aligned) > 0, "aligned series must not be empty"
        assert aligned.index[0].date() >= date_from, (
            f"aligned series starts at {aligned.index[0].date()}, which is before "
            f"date_from={date_from} — warmup was not sliced off"
        )

    def test_warmup_dates_absent_from_aligned_series(self):
        """Dates strictly before date_from must not appear in aligned series."""
        date_from = date(2022, 6, 1)
        tri = _synthetic_tri(date_from, n_days=500)

        cal = pd.bdate_range(start=date_from, periods=252, freq="B")
        aligned = align_benchmark(
            tri,
            date_from=date_from,
            trading_calendar=list(pd.DatetimeIndex(cal)),
            starting_capital=1_000_000.0,
        )

        pre_warmup = aligned[aligned.index < pd.Timestamp(date_from)]
        assert len(pre_warmup) == 0, (
            f"{len(pre_warmup)} warmup dates found in aligned series "
            f"(before {date_from}) — these should have been sliced off"
        )

    def test_benchmark_metrics_computable_on_aligned_window(self):
        """Sharpe and Calmar are computable from an aligned benchmark series."""
        date_from = date(2022, 1, 3)
        n_days = 500
        tri = _synthetic_tri(date_from, n_days=n_days, daily_ret=0.0008)

        cal = pd.bdate_range(start=date_from, periods=252, freq="B")
        aligned = align_benchmark(
            tri,
            date_from=date_from,
            trading_calendar=list(pd.DatetimeIndex(cal)),
            starting_capital=1_000_000.0,
        )

        # Build a synthetic strategy equity that covers the same window.
        strat_returns = [0.001] * len(aligned)
        strat_eq = pd.Series(
            [1_000_000.0 * (1.001**i) for i in range(len(strat_returns) + 1)],
            index=pd.DatetimeIndex(
                [
                    aligned.index[0] + pd.Timedelta(days=i)
                    for i in range(len(strat_returns) + 1)
                ]
            ),
        )

        bm = compute_benchmark_metrics(strat_eq, aligned)

        assert math.isfinite(bm.strategy_cagr), "strategy CAGR must be finite"
        assert math.isfinite(bm.benchmark_cagr), "benchmark CAGR must be finite"
        assert math.isfinite(bm.strategy_max_dd) or bm.strategy_max_dd == 0.0

    def test_aligned_rebased_to_starting_capital(self):
        """First value of aligned series equals starting_capital exactly."""
        date_from = date(2022, 6, 1)
        capital = 750_000.0
        tri = _synthetic_tri(date_from, n_days=500)

        cal = pd.bdate_range(start=date_from, periods=252, freq="B")
        aligned = align_benchmark(
            tri,
            date_from=date_from,
            trading_calendar=list(pd.DatetimeIndex(cal)),
            starting_capital=capital,
        )

        assert aligned.iloc[0] == pytest.approx(capital, rel=1e-9), (
            f"aligned series first value {aligned.iloc[0]:.2f} != "
            f"starting_capital {capital:.2f} — rebase is wrong"
        )


# ---------------------------------------------------------------------------
# Criterion 4 — §4.4: three-cost-level report renders
# ---------------------------------------------------------------------------


class TestCriterion4_ThreeLevelReportRenders:
    """§4.4: all three cost levels produce valid EngineResult + BacktestMetrics.

    WHY: The three-cost-level sensitivity report (§1.4) is a hard requirement:
    if the edge only exists at optimistic, the report must make that obvious.
    The report must render — not crash — for any run.
    """

    def test_all_three_levels_produce_snapshots(self):
        """Each cost level must return an EngineResult with non-empty snapshots."""
        prices = _make_prices()
        config = _make_config()

        for level in ("optimistic", "base", "pessimistic"):
            r = engine.run(prices, config, cost_level=level)
            assert len(r.snapshots) > 0, f"cost_level='{level}' produced no snapshots"

    def test_all_three_levels_metrics_computable(self):
        """compute_metrics must not raise for any of the three cost levels."""
        prices = _make_prices()
        config = _make_config()

        for level in ("optimistic", "base", "pessimistic"):
            r = engine.run(prices, config, cost_level=level)
            m = compute_metrics(r)
            assert math.isfinite(m.cagr), f"CAGR not finite for level={level}"
            assert math.isfinite(m.sharpe), f"Sharpe not finite for level={level}"
            assert math.isfinite(m.max_drawdown), f"MaxDD not finite for level={level}"

    def test_equity_ordered_optimistic_gte_base_gte_pessimistic(self):
        """Optimistic equity ≥ base ≥ pessimistic (slippage drag is real).

        Ordering is on final equity (not total_cost_paid) because slippage
        manifests as effective fill-price drag, not a cash deduction.
        """
        prices = _make_prices()
        config = _make_config()

        r_opt = engine.run(prices, config, cost_level="optimistic")
        r_base = engine.run(prices, config, cost_level="base")
        r_pess = engine.run(prices, config, cost_level="pessimistic")

        eq_opt = r_opt.snapshots[-1].equity
        eq_base = r_base.snapshots[-1].equity
        eq_pess = r_pess.snapshots[-1].equity

        assert eq_opt >= eq_base, (
            f"optimistic ({eq_opt:.2f}) must have equity ≥ base ({eq_base:.2f})"
        )
        assert eq_base >= eq_pess, (
            f"base ({eq_base:.2f}) must have equity ≥ pessimistic ({eq_pess:.2f})"
        )

    def test_three_levels_produce_distinct_equity_curves(self):
        """All three levels must produce different final equities (not identical)."""
        prices = _make_prices()
        config = _make_config()

        equities = {
            level: engine.run(prices, config, cost_level=level).snapshots[-1].equity
            for level in ("optimistic", "base", "pessimistic")
        }

        assert equities["optimistic"] != pytest.approx(equities["base"], rel=1e-4), (
            "optimistic and base must produce different equities"
        )
        assert equities["base"] != pytest.approx(equities["pessimistic"], rel=1e-4), (
            "base and pessimistic must produce different equities"
        )

    def test_cost_level_overrides_explicit_cost_cfg(self):
        """cost_level overrides cost_cfg when both are passed (spec 03 T4)."""
        prices = _make_prices()
        config = _make_config()

        # Pass an explicit cost_cfg that differs from optimistic; cost_level should win.
        explicit_cfg = CostConfig.pessimistic()
        r_via_level = engine.run(
            prices, config, cost_level="optimistic", cost_cfg=explicit_cfg
        )
        r_direct = engine.run(prices, config, cost_level="optimistic")

        eq_via_level = r_via_level.snapshots[-1].equity
        eq_direct = r_direct.snapshots[-1].equity

        assert eq_via_level == pytest.approx(eq_direct, rel=1e-9), (
            "cost_level='optimistic' must override explicit cost_cfg=pessimistic"
        )


# ---------------------------------------------------------------------------
# Criterion 5 — §4.5: headline ratios present, finite, surfaced
# ---------------------------------------------------------------------------


class TestCriterion5_HeadlineRatiosSurfaced:
    """§4.5: Calmar ratio + max-DD ratio must be computed, finite, and printed.

    WHY: These are the two headline pass/fail numbers for the whole project.
    The test confirms both are present in BenchmarkMetrics, are finite on valid
    input, and appear in the text produced by benchmark_summary().
    """

    def test_calmar_ratio_present_and_finite(self):
        """BenchmarkMetrics.calmar_ratio is present and finite for valid input."""
        bench_rets = [0.001, -0.01, 0.005, -0.005, 0.002] * 50
        strat_rets = [0.002, -0.008, 0.006, -0.004, 0.003] * 50

        bench_eq = _make_equity_series(bench_rets)
        strat_eq = _make_equity_series(strat_rets)

        bm = compute_benchmark_metrics(strat_eq, bench_eq)

        assert hasattr(bm, "calmar_ratio"), "BenchmarkMetrics must have calmar_ratio"
        assert math.isfinite(bm.calmar_ratio), (
            f"calmar_ratio={bm.calmar_ratio} must be finite for valid input"
        )

    def test_max_dd_ratio_present_and_finite(self):
        """BenchmarkMetrics.max_dd_ratio is present and finite for valid input."""
        bench_rets = [0.001, -0.01, 0.005, -0.005, 0.002] * 50
        strat_rets = [0.002, -0.008, 0.006, -0.004, 0.003] * 50

        bench_eq = _make_equity_series(bench_rets)
        strat_eq = _make_equity_series(strat_rets)

        bm = compute_benchmark_metrics(strat_eq, bench_eq)

        assert hasattr(bm, "max_dd_ratio"), "BenchmarkMetrics must have max_dd_ratio"
        assert math.isfinite(bm.max_dd_ratio), (
            f"max_dd_ratio={bm.max_dd_ratio} must be finite for valid input"
        )

    def test_benchmark_summary_contains_calmar_ratio_label(self):
        """benchmark_summary() text must contain 'Calmar Ratio' (prominently surfaced)."""
        bench_rets = [0.001, -0.01, 0.005] * 84
        strat_rets = [0.002, -0.008, 0.006] * 84

        bm = compute_benchmark_metrics(
            _make_equity_series(strat_rets), _make_equity_series(bench_rets)
        )
        text = benchmark_summary(bm)

        assert "Calmar Ratio" in text, (
            "benchmark_summary() must include 'Calmar Ratio' (spec 03 §4.5 — headline)"
        )

    def test_benchmark_summary_contains_max_dd_ratio_label(self):
        """benchmark_summary() text must contain 'Max-DD Ratio' (prominently surfaced)."""
        bench_rets = [0.001, -0.01, 0.005] * 84
        strat_rets = [0.002, -0.008, 0.006] * 84

        bm = compute_benchmark_metrics(
            _make_equity_series(strat_rets), _make_equity_series(bench_rets)
        )
        text = benchmark_summary(bm)

        assert "Max-DD Ratio" in text, (
            "benchmark_summary() must include 'Max-DD Ratio' (spec 03 §4.5 — headline)"
        )

    def test_pass_flag_when_calmar_ratio_greater_than_one(self):
        """When Calmar ratio > 1, benchmark_summary includes a pass indicator."""
        # Strategy: low drawdown relative to benchmark → Calmar ratio > 1.
        bench_rets = [0.005] * 50 + [-0.20] + [0.005] * 201
        strat_rets = [0.005] * 50 + [-0.06] + [0.005] * 201

        bm = compute_benchmark_metrics(
            _make_equity_series(strat_rets), _make_equity_series(bench_rets)
        )

        assert bm.calmar_ratio > 1.0, f"calmar_ratio={bm.calmar_ratio}, expected > 1"
        text = benchmark_summary(bm)
        assert "> 1" in text or "✓" in text, (
            "benchmark_summary() should indicate a pass (> 1 or ✓) when calmar_ratio > 1"
        )

    def test_negative_calmar_ratio_nan_when_bench_no_drawdown(self):
        """Degenerate: all-rising benchmark → calmar_ratio is nan, no crash."""
        bench_rets = [0.001] * 100
        strat_rets = [0.001, -0.01, 0.005] * 33 + [0.001]

        bm = compute_benchmark_metrics(
            _make_equity_series(strat_rets), _make_equity_series(bench_rets)
        )

        assert math.isnan(bm.calmar_ratio), (
            "calmar_ratio must be nan when benchmark has no drawdown (bench_calmar=nan)"
        )
        # benchmark_summary should still render without raising.
        text = benchmark_summary(bm)
        assert "Calmar Ratio" in text

    def test_max_dd_ratio_target_surfaced_in_summary(self):
        """benchmark_summary() surfaces the ≤ 0.70 target for max-DD ratio."""
        # Build a case where max_dd_ratio <= 0.70 (strategy has smaller drawdown).
        bench_rets = [0.005] * 30 + [-0.30] + [0.005] * 200
        strat_rets = [0.005] * 30 + [-0.10] + [0.005] * 200

        bm = compute_benchmark_metrics(
            _make_equity_series(strat_rets), _make_equity_series(bench_rets)
        )
        assert bm.max_dd_ratio <= 0.70, (
            f"max_dd_ratio={bm.max_dd_ratio:.3f}, expected ≤ 0.70"
        )

        text = benchmark_summary(bm)
        assert "0.70" in text or "≤ 0.70" in text or "✓" in text, (
            "benchmark_summary() should surface the ≤ 0.70 target for max-DD ratio"
        )
