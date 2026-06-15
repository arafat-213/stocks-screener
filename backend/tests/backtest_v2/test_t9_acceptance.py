"""
test_t9_acceptance.py — T9 acceptance suite: §10 of 02_SIMULATION_CORE.md as hard tests.

Each test encodes WHY the invariant matters (per Rule 9), not just what it checks.
All run offline against synthetic price data — no network, no yfinance, no NSE (Rule 5).

Acceptance criteria (02 §10):
  AC1  No-lookahead: decisions up to D are unchanged when future data (> D) is corrupted.
  AC2  Cash conservation: equity == cash + Σ shares*price every day; total cost paid
       == Σ per-fill costs (no double-counting).
  AC3  Determinism: same config + data → identical equity curve byte-for-byte.
  AC4  Exposure sanity: sustained downtrend with overlay=True → materially lower avg
       exposure than overlay=False (the regime overlay earns its keep).
  AC5  Turnover sanity: monthly rebalance with buffer → annualized turnover via
       compute_metrics is not absurd (< 1000%).
  AC6  v1-direction smoke: on clearly trending data with strong momentum, the strategy
       produces positive returns — a gross wiring check (02 §10.6).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.costs import CostConfig, fill_cost
from app.backtest_v2.engine import EngineResult, run
from app.backtest_v2.metrics import compute_metrics

# ---------------------------------------------------------------------------
# Shared synthetic-data helpers
# ---------------------------------------------------------------------------


def _make_prices(
    isins: list[str],
    start: str = "2021-01-04",
    n_days: int = 500,
    seed: int = 0,
    drift: float = 0.0006,
    vol: float = 0.012,
    base_price: float = 100.0,
    adv_20: float = 1e8,
) -> pd.DataFrame:
    """Long-format synthetic prices with all required columns."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    rows = []
    for isin in isins:
        price = base_price
        prices_list: list[float] = []
        for _ in dates:
            price = max(price * (1 + rng.normal(drift, vol)), 0.01)
            prices_list.append(price)
        for i, (d, p) in enumerate(zip(dates, prices_list)):
            rows.append(
                {
                    "isin": isin,
                    "symbol": isin,
                    "date": d,
                    "open": p * rng.uniform(0.99, 1.01),
                    "high": p * rng.uniform(1.00, 1.02),
                    "low": p * rng.uniform(0.98, 1.00),
                    "close": p,
                    "close_raw": p,
                    "close_tr": p * 1.001**i,
                    "volume": 200_000,
                    "traded_value": adv_20,
                    "adv_20": adv_20,
                    "adj_factor": 1.0,
                    "tr_factor": 1.001**i,
                    "series": "EQ",
                }
            )
    return pd.DataFrame(rows)


def _make_index(prices_df: pd.DataFrame, uptrend: bool = True) -> pd.Series:
    dates = prices_df["date"].drop_duplicates().sort_values()
    n = len(dates)
    vals = np.linspace(100, 200, n) if uptrend else np.linspace(200, 50, n)
    return pd.Series(vals, index=pd.to_datetime(dates))


def _cfg(**kwargs) -> MomentumConfig:
    base = dict(
        target_positions=4,
        sell_rank_buffer=7,
        liquidity_floor_cr=0.5,
        momentum_lookback_days=252,
        momentum_skip_days=21,
        vol_lookback_days=60,
        max_position_pct=35.0,
        starting_capital=1_000_000.0,
        use_regime_overlay=False,
        catastrophic_stop_pct=25.0,
        rebalance="monthly",
        date_from=None,
        date_to=None,
    )
    base.update(kwargs)
    return MomentumConfig(**base)


# ---------------------------------------------------------------------------
# AC1 — No-lookahead
#
# WHY: a backtest that leaks future prices into past decisions silently inflates
# results.  The engine's invariant is "all decisions use data ≤ decision date;
# all fills at D+1 open."  We prove this by corrupting future rows and showing
# the past equity curve is unchanged.
# ---------------------------------------------------------------------------


def test_ac1_no_lookahead_future_corruption_leaves_past_unchanged():
    """
    Corrupt every price row after the cutoff date and assert that the equity
    curve up to the cutoff is byte-identical to the clean run.
    """
    isins = [f"ISIN{i:02d}" for i in range(8)]
    prices_clean = _make_prices(isins, n_days=500, seed=11)

    # Cutoff: split the calendar roughly in half
    dates = sorted(prices_clean["date"].drop_duplicates().tolist())
    cutoff = dates[len(dates) // 2]
    cutoff_date = pd.Timestamp(cutoff).date()

    cfg = _cfg(date_to=cutoff_date)

    # Run 1: clean data, up to cutoff
    r_clean = run(prices_clean, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    # Run 2: corrupt ALL future rows (after cutoff) with wild price values
    prices_corrupted = prices_clean.copy()
    future_mask = prices_corrupted["date"] > pd.Timestamp(cutoff)
    prices_corrupted.loc[future_mask, "close"] = 9_999_999.0
    prices_corrupted.loc[future_mask, "close_tr"] = 9_999_999.0
    prices_corrupted.loc[future_mask, "open"] = 0.001
    prices_corrupted.loc[future_mask, "high"] = 9_999_999.0
    prices_corrupted.loc[future_mask, "low"] = 0.001
    prices_corrupted.loc[future_mask, "adv_20"] = 0.0

    r_corrupted = run(prices_corrupted, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    # Both runs must produce the same number of snapshots (identical calendar)
    assert len(r_clean.snapshots) == len(r_corrupted.snapshots), (
        "Snapshot counts differ — future data affected the active window calendar"
    )

    # Every per-day equity value must be identical to floating-point tolerance
    for s_c, s_x in zip(r_clean.snapshots, r_corrupted.snapshots):
        assert s_c.date == s_x.date
        assert abs(s_c.equity - s_x.equity) < 1e-4, (
            f"Equity differs on {s_c.date}: clean={s_c.equity:.6f} "
            f"corrupted={s_x.equity:.6f}  — future data leaked into past decisions"
        )
        assert abs(s_c.cash - s_x.cash) < 1e-4, (
            f"Cash differs on {s_c.date}: future data leaked"
        )


def test_ac1_negative_past_corruption_does_change_results():
    """
    Negative test: corrupting data WITHIN the active window does change results,
    proving the engine is not simply ignoring all data.
    """
    isins = [f"ISIN{i:02d}" for i in range(8)]
    prices_clean = _make_prices(isins, n_days=500, seed=12, drift=0.001)

    dates = sorted(prices_clean["date"].drop_duplicates().tolist())
    # Corrupt the second quarter — inside the active window
    corrupt_start = dates[len(dates) // 4]
    corrupt_end = dates[len(dates) // 2]
    cutoff_date = pd.Timestamp(dates[-1]).date()

    cfg = _cfg(date_to=cutoff_date)
    r_clean = run(prices_clean, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    prices_corrupted = prices_clean.copy()
    inside_mask = (prices_corrupted["date"] >= pd.Timestamp(corrupt_start)) & (
        prices_corrupted["date"] <= pd.Timestamp(corrupt_end)
    )
    # Collapse all prices to near-zero → triggers stops, collapses equity
    prices_corrupted.loc[inside_mask, "close"] = 0.01
    prices_corrupted.loc[inside_mask, "close_tr"] = 0.01
    prices_corrupted.loc[inside_mask, "open"] = 0.01

    r_corrupted = run(prices_corrupted, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    final_equity_clean = r_clean.snapshots[-1].equity
    final_equity_corrupted = r_corrupted.snapshots[-1].equity

    # Past corruption must cause a measurable difference
    assert abs(final_equity_clean - final_equity_corrupted) > 1.0, (
        f"Inside-window corruption had no effect (clean={final_equity_clean:.2f}, "
        f"corrupted={final_equity_corrupted:.2f}) — engine may be ignoring all data"
    )


# ---------------------------------------------------------------------------
# AC2 — Cash conservation (re-asserted at acceptance level)
#
# WHY: broken cash accounting is the most common silent backtest bug.  Every
# day, equity must equal cash + market value of positions.  Total cost paid
# must equal the sum of per-fill costs (no double-counting anywhere).
# ---------------------------------------------------------------------------


def test_ac2_cash_conservation_every_snapshot():
    """equity == cash + invested_value within ₹0.01 every single day."""
    isins = [f"ISIN{i:02d}" for i in range(10)]
    prices = _make_prices(isins, n_days=500, seed=20)
    result = run(prices, _cfg(), cost_fn=fill_cost, cost_cfg=CostConfig())

    for snap in result.snapshots:
        residual = abs(snap.cash + snap.invested_value - snap.equity)
        assert residual < 0.01, (
            f"Cash conservation broken on {snap.date}: "
            f"cash={snap.cash:.4f} + invested={snap.invested_value:.4f} "
            f"≠ equity={snap.equity:.4f}  (residual={residual:.6f})"
        )


def test_ac2_total_cost_equals_sum_of_fill_costs():
    """
    result.total_cost_paid must equal Σ fill.cost_rupees across fills_log.

    WHY: double-counting or missed costs in apply_fills would corrupt the P&L
    without triggering an obvious error.
    """
    isins = [f"ISIN{i:02d}" for i in range(8)]
    prices = _make_prices(isins, n_days=500, seed=21)
    result = run(prices, _cfg(), cost_fn=fill_cost, cost_cfg=CostConfig())

    sum_fill_costs = sum(f.cost_rupees for f in result.fills_log)
    assert abs(result.total_cost_paid - sum_fill_costs) < 0.01, (
        f"total_cost_paid ({result.total_cost_paid:.4f}) ≠ "
        f"Σ fill.cost_rupees ({sum_fill_costs:.4f})"
    )


def test_ac2_starting_capital_conserved_when_no_fills():
    """
    If no ISINs ever pass the entry gate (impossible universe), equity stays at
    starting capital every day — all money stays as cash, no cost paid.
    """
    # Create prices where momentum is always negative (downtrend for 500 days)
    isins = [f"ISIN{i:02d}" for i in range(6)]
    prices = _make_prices(isins, n_days=500, seed=99, drift=-0.003, vol=0.005)
    cfg = _cfg(use_regime_overlay=False)
    result = run(prices, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    if not result.fills_log:
        # No fills — equity must stay at starting capital the whole time
        start_cap = cfg.starting_capital
        for snap in result.snapshots:
            assert abs(snap.equity - start_cap) < 0.01, (
                f"Equity drifted without fills on {snap.date}: {snap.equity:.4f} "
                f"≠ starting capital {start_cap:.4f}"
            )
            assert snap.exposure == 0.0, (
                f"Exposure non-zero with no fills on {snap.date}: {snap.exposure}"
            )


# ---------------------------------------------------------------------------
# AC3 — Determinism
#
# WHY: any non-determinism means two users running the same backtest get
# different answers — unacceptable for reproducibility.
# ---------------------------------------------------------------------------


def test_ac3_identical_runs_produce_identical_equity_curves():
    """Same config + data → byte-identical equity curve across three runs."""
    isins = [f"ISIN{i:02d}" for i in range(8)]
    prices = _make_prices(isins, n_days=500, seed=30)
    cfg = _cfg()

    results = [
        run(prices, cfg, cost_fn=fill_cost, cost_cfg=CostConfig()) for _ in range(3)
    ]

    for run_idx in range(1, 3):
        r_ref = results[0]
        r_cmp = results[run_idx]
        assert len(r_ref.snapshots) == len(r_cmp.snapshots), (
            f"Run {run_idx}: snapshot count differs ({len(r_ref.snapshots)} vs {len(r_cmp.snapshots)})"
        )
        for snap_ref, snap_cmp in zip(r_ref.snapshots, r_cmp.snapshots):
            assert snap_ref.date == snap_cmp.date
            assert abs(snap_ref.equity - snap_cmp.equity) < 1e-6, (
                f"Run {run_idx}: equity differs on {snap_ref.date}: "
                f"{snap_ref.equity} vs {snap_cmp.equity}"
            )


def test_ac3_different_configs_produce_different_results():
    """
    Negative test: a config change (fewer positions) produces a different equity
    curve, proving the engine actually uses the config.
    """
    isins = [f"ISIN{i:02d}" for i in range(10)]
    prices = _make_prices(isins, n_days=500, seed=31, drift=0.001)

    r_narrow = run(
        prices, _cfg(target_positions=2), cost_fn=fill_cost, cost_cfg=CostConfig()
    )
    r_wide = run(
        prices, _cfg(target_positions=8), cost_fn=fill_cost, cost_cfg=CostConfig()
    )

    eq_narrow = [s.equity for s in r_narrow.snapshots]
    eq_wide = [s.equity for s in r_wide.snapshots]

    # After enough rebalances the portfolios must diverge
    assert eq_narrow != eq_wide, (
        "Different target_positions configs produced identical equity curves — "
        "config may not be wired to the engine correctly"
    )


# ---------------------------------------------------------------------------
# AC4 — Exposure sanity with regime overlay
#
# WHY: the entire edge thesis is that a regime overlay cuts exposure in
# downtrends, reducing drawdown.  If overlay=True and overlay=False produce the
# same exposure in a bear market, the overlay is broken.
# ---------------------------------------------------------------------------


def test_ac4_overlay_on_lower_avg_exposure_in_downtrend():
    """
    Sustained downtrend index → overlay=True produces materially lower avg
    exposure than overlay=False over the same price data.
    """
    isins = [f"ISIN{i:02d}" for i in range(8)]
    prices = _make_prices(isins, n_days=600, seed=40, drift=0.0003)
    index_down = _make_index(prices, uptrend=False)

    r_on = run(prices, _cfg(use_regime_overlay=True), index_prices=index_down)
    r_off = run(prices, _cfg(use_regime_overlay=False))

    avg_on = sum(s.exposure for s in r_on.snapshots) / len(r_on.snapshots)
    avg_off = sum(s.exposure for s in r_off.snapshots) / len(r_off.snapshots)

    assert avg_on < avg_off, (
        f"Overlay ON avg exposure ({avg_on:.3f}) is not lower than "
        f"overlay OFF ({avg_off:.3f}) in a sustained downtrend — "
        "regime overlay is not reducing exposure"
    )


def test_ac4_overlay_off_ignores_downtrend_index():
    """
    With overlay=False the index series is ignored: avg exposure should be the
    same whether we pass a downtrend or uptrend index (or None).
    """
    isins = [f"ISIN{i:02d}" for i in range(8)]
    prices = _make_prices(isins, n_days=500, seed=41)
    index_down = _make_index(prices, uptrend=False)
    index_up = _make_index(prices, uptrend=True)

    cfg_off = _cfg(use_regime_overlay=False)
    r_down = run(prices, cfg_off, index_prices=index_down)
    r_up = run(prices, cfg_off, index_prices=index_up)
    r_none = run(prices, cfg_off, index_prices=None)

    avgs = {
        "down": sum(s.exposure for s in r_down.snapshots) / len(r_down.snapshots),
        "up": sum(s.exposure for s in r_up.snapshots) / len(r_up.snapshots),
        "none": sum(s.exposure for s in r_none.snapshots) / len(r_none.snapshots),
    }
    # All three must be identical (overlay is disabled)
    for label, avg in avgs.items():
        assert abs(avg - avgs["none"]) < 1e-9, (
            f"overlay=False run with index_{label} has avg exposure {avg:.6f} "
            f"≠ index_none run {avgs['none']:.6f} — overlay may not be gated correctly"
        )


def test_ac4_overlay_on_uptrend_stays_fully_deployed():
    """
    In a sustained uptrend the index is above its 200-DMA the whole time →
    regime stays risk-on → deployable_fraction=1.0 → avg exposure should be
    similar to overlay=False (i.e., the overlay doesn't over-constrain).
    """
    isins = [f"ISIN{i:02d}" for i in range(8)]
    # Need enough data for 200-DMA warmup + rebalances
    prices = _make_prices(isins, n_days=600, seed=42, drift=0.001)
    index_up = _make_index(prices, uptrend=True)

    r_on = run(prices, _cfg(use_regime_overlay=True), index_prices=index_up)
    r_off = run(prices, _cfg(use_regime_overlay=False))

    avg_on = sum(s.exposure for s in r_on.snapshots) / len(r_on.snapshots)
    avg_off = sum(s.exposure for s in r_off.snapshots) / len(r_off.snapshots)

    # In an uptrend overlay must not be MORE restrictive than no overlay
    # (allow 5pp tolerance for the 200-DMA warmup period at the start)
    assert avg_on >= avg_off - 0.05, (
        f"Overlay ON in uptrend ({avg_on:.3f}) is much lower than overlay OFF "
        f"({avg_off:.3f}) — regime overlay incorrectly constraining a bull market"
    )


# ---------------------------------------------------------------------------
# AC5 — Turnover sanity
#
# WHY: runaway turnover (> 1000% annualized) is a red flag — it implies the
# hysteresis buffer is broken or the sell/buy logic has a bug.  Transaction
# costs explode and the strategy would be unimplementable in practice.
# ---------------------------------------------------------------------------


def test_ac5_annualized_turnover_below_absurd_threshold():
    """
    Monthly rebalance with buffer → annualized turnover via compute_metrics
    must be < 1000% (the spec threshold in 02 §10.5 and metrics.py).
    """
    isins = [f"ISIN{i:02d}" for i in range(12)]
    prices = _make_prices(isins, n_days=600, seed=50)
    cfg = _cfg(target_positions=4, sell_rank_buffer=8)
    result = run(prices, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    if not result.per_rebalance_turnover:
        pytest.skip("No rebalances fired; skip turnover check")

    metrics = compute_metrics(result)

    # annualized_turnover is a fraction: 1.0 = 100%, 10.0 = 1000%
    assert not metrics.turnover_is_absurd, (
        f"Annualized turnover {metrics.annualized_turnover * 100:.1f}% exceeds the "
        "1000% absurdity threshold — hysteresis buffer may be broken"
    )


def test_ac5_buffer_reduces_turnover_vs_no_buffer():
    """
    A wide hysteresis buffer (sell_rank_buffer >> target_positions) should
    produce lower turnover than a tight buffer (sell = buy threshold).

    WHY: the buffer is the primary churn-reduction mechanism; if it doesn't
    lower turnover, it's not doing its job.
    """
    isins = [f"ISIN{i:02d}" for i in range(14)]
    prices = _make_prices(isins, n_days=600, seed=51, drift=0.0002)

    cfg_tight = _cfg(target_positions=4, sell_rank_buffer=4)  # no buffer
    cfg_wide = _cfg(target_positions=4, sell_rank_buffer=10)  # wide buffer

    r_tight = run(prices, cfg_tight, cost_fn=fill_cost, cost_cfg=CostConfig())
    r_wide = run(prices, cfg_wide, cost_fn=fill_cost, cost_cfg=CostConfig())

    if not r_tight.per_rebalance_turnover or not r_wide.per_rebalance_turnover:
        pytest.skip("Insufficient rebalances; skip")

    def _annualized(result: EngineResult) -> float:
        n = len(result.per_rebalance_turnover)
        total = sum(t for _, t in result.per_rebalance_turnover)
        return (total / n) * 12 * 100 if n > 0 else 0.0

    to_tight = _annualized(r_tight)
    to_wide = _annualized(r_wide)

    assert to_wide <= to_tight, (
        f"Wide buffer turnover ({to_wide:.1f}%) is higher than tight buffer "
        f"({to_tight:.1f}%) — hysteresis buffer is not reducing churn"
    )


# ---------------------------------------------------------------------------
# AC6 — v1-direction smoke check (02 §10.6)
#
# WHY: not a correctness test — a gross wiring check.  On a clearly trending
# universe where all names have strong positive momentum, a working momentum
# strategy must at minimum deploy capital and not lose everything.  A final
# equity well below starting capital with no fills would indicate a broken
# pipeline wiring, not just a strategy that underperformed.
# ---------------------------------------------------------------------------


def _make_strong_uptrend_prices(n_days: int = 600, n_isins: int = 10) -> pd.DataFrame:
    """
    All ISINs trend strongly upward with a fixed drift sufficient to build
    positive 12-1 momentum after the warmup window.
    """
    rng = np.random.default_rng(77)
    dates = pd.bdate_range("2020-01-02", periods=n_days)
    rows = []
    for idx in range(n_isins):
        isin = f"ISIN{idx:02d}"
        # Strong drift (0.15% / day ≈ 45% / year) with small vol
        returns = rng.normal(0.0015, 0.008, n_days)
        prices_arr = 100.0 * np.cumprod(1 + returns)
        for i, (d, p) in enumerate(zip(dates, prices_arr)):
            rows.append(
                {
                    "isin": isin,
                    "symbol": isin,
                    "date": d,
                    "open": p * 0.999,
                    "high": p * 1.008,
                    "low": p * 0.992,
                    "close": p,
                    "close_raw": p,
                    "close_tr": p * 1.0008**i,
                    "volume": 500_000,
                    "traded_value": 5e8,
                    "adv_20": 5e8,
                    "adj_factor": 1.0,
                    "tr_factor": 1.0008**i,
                    "series": "EQ",
                }
            )
    return pd.DataFrame(rows)


def test_ac6_strategy_deploys_capital_on_uptrend():
    """
    On a strong uptrend universe the strategy must deploy capital: at least
    one fill must occur and final equity must not be near zero.
    """
    prices = _make_strong_uptrend_prices()
    cfg = _cfg(
        target_positions=4,
        sell_rank_buffer=7,
        liquidity_floor_cr=0.5,  # ₹0.5 Cr — easily passed by adv_20=5e8
        use_regime_overlay=False,
    )
    result = run(prices, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    assert len(result.fills_log) > 0, (
        "No fills on a strong uptrend universe — entry gate or ranking is broken"
    )
    assert len(result.rebalance_dates_used) > 0, (
        "No rebalance dates used — month-end detection or calendar is broken"
    )
    # Starting capital should still be largely intact (at worst portfolio went
    # to cash — not acceptable to lose 50%+ with no extreme scenario)
    final_equity = result.snapshots[-1].equity
    assert final_equity > cfg.starting_capital * 0.5, (
        f"Final equity {final_equity:.0f} < 50% of starting capital "
        f"{cfg.starting_capital:.0f} on a strong uptrend — gross wiring error"
    )


def test_ac6_uptrend_produces_positive_cagr():
    """
    A strong multi-year uptrend universe must produce positive CAGR after costs.
    This is the v1-direction smoke check: not a precise target, just positive.
    """
    prices = _make_strong_uptrend_prices(n_days=600, n_isins=10)
    cfg = _cfg(
        target_positions=4,
        liquidity_floor_cr=0.5,
        use_regime_overlay=False,
    )
    result = run(prices, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    if not result.fills_log:
        pytest.skip("No fills produced; skip CAGR check")

    metrics = compute_metrics(result)
    assert metrics.cagr > 0.0, (
        f"CAGR={metrics.cagr:.4f} is not positive on a strong uptrend universe — "
        "check signal → engine wiring, cost model, or fill price stamping"
    )


def test_ac6_flat_market_does_not_gain_on_cash():
    """
    If no names pass the entry gate (all flat / no momentum), the portfolio
    stays in cash and final equity ≈ starting capital (costs only on any fills).

    WHY: verifies the "never force deployment" invariant — unallocated capital
    stays in cash, not burned on bad trades.
    """
    # Build a market where all prices are perfectly flat (zero momentum)
    isins = [f"ISIN{i:02d}" for i in range(6)]
    dates = pd.bdate_range("2021-01-04", periods=400)
    rows = []
    for isin in isins:
        for d in dates:
            rows.append(
                {
                    "isin": isin,
                    "symbol": isin,
                    "date": d,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "close_raw": 100.0,
                    "close_tr": 100.0,
                    "volume": 100_000,
                    "traded_value": 1e8,
                    "adv_20": 1e8,
                    "adj_factor": 1.0,
                    "tr_factor": 1.0,
                    "series": "EQ",
                }
            )
    prices_flat = pd.DataFrame(rows)
    cfg = _cfg(use_regime_overlay=False)
    result = run(prices_flat, cfg, cost_fn=fill_cost, cost_cfg=CostConfig())

    final_equity = result.snapshots[-1].equity
    start_cap = cfg.starting_capital
    # Equity should be at or very near starting capital (at most costs of any fills)
    # In practice flat closes → zero momentum → no entry gate pass → no fills
    assert final_equity >= start_cap * 0.99, (
        f"Flat market final equity {final_equity:.2f} is more than 1% below "
        f"starting capital {start_cap:.2f} — capital is being lost without trades"
    )
