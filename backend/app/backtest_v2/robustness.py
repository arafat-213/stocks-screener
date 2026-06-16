"""
robustness.py — Spec 04 T4: five §6 robustness checks on the T3 candidate.

Candidate (T3 layer-1 plateau winner, accepted 2026-06-16):
    MomentumConfig defaults + RegimeConfig(debounce_days=1, risk_off_floor=0.25)
    run on DISCOVERY (2018-02-06 → 2023-06-30).

Five checks (04 §6):
    §6.1  Cost stress       — beats Nifty50 TRI Calmar at pessimistic cost
    §6.2  Universe perturb  — drop top-10 P&L names; Calmar retains >= 70%
    §6.3  Neighborhood      — plateau on candidate + immediate neighbors
    §6.4  Subperiod         — positive Calmar in >= 2 of 3 market-cycle periods
    §6.5  Turnover/capacity — avg trade participation < 5% of ADV floor

Each check records every engine call to the ConfigLedger so the K-trial count
stays accurate for deflated-Sharpe discounting in T5.

Run:
    backend/venv/bin/python -m app.backtest_v2.robustness
"""

from __future__ import annotations

import dataclasses
import logging
import math
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from app.backtest_v2 import benchmark, engine, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.iterate import GridPoint, plateau_check
from app.backtest_v2.regime import RegimeConfig
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Candidate — T3 layer-1 plateau winner; do NOT change (this is the config
# under test, not a new search — Rule 12)
# ---------------------------------------------------------------------------
CANDIDATE_REGIME = RegimeConfig(debounce_days=1, risk_off_floor=0.25)

# Benchmark fetch range matches T1/T3 cache keys so no network hit is needed.
_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# ---------------------------------------------------------------------------
# §6.3 Neighborhood grid:
#   debounce ∈ [1, 3]      — candidate=1, one step up=3 (no step below boundary)
#   risk_off ∈ [0.0, 0.25, 0.50] — full T3 range (candidate=0.25)
#   → 6 combos: winner + 3 immediate neighbors
# ---------------------------------------------------------------------------
_NBR_DEBOUNCE: list[int] = [1, 3]
_NBR_RISK_OFF: list[float] = [0.0, 0.25, 0.50]

# ---------------------------------------------------------------------------
# §6.4 Subperiods within DISCOVERY (2018-02-06 → 2023-06-30).
# Named after distinct Indian equity-market regimes; boundaries fixed before
# running (Rule 12 — no moving the window to make a check pass).
# ---------------------------------------------------------------------------
SUBPERIODS: list[tuple[str, date, date]] = [
    # IL&FS credit crisis (2018 H2) → COVID crash peak
    ("Pre-COVID chop", date(2018, 2, 6), date(2020, 3, 31)),
    # V-shaped recovery → pre-rate-hike Nifty50 peak
    ("Post-COVID bull", date(2020, 4, 1), date(2022, 1, 31)),
    # RBI hikes + Russia-Ukraine + mid/smallcap correction and partial recovery
    ("Rate-hike correction", date(2022, 2, 1), date(2023, 6, 30)),
]

# ---------------------------------------------------------------------------
# Thresholds — all named so tests can verify logic without re-deriving them
# ---------------------------------------------------------------------------
UNIVERSE_PERTURB_THRESHOLD: float = 0.70  # §6.2: Calmar must retain >= 70%
N_TOP_CONTRIBUTORS: int = 10  # §6.2: names to drop
SUBPERIOD_MIN_POSITIVE: int = 2  # §6.4: need this many positive Calmar
GLITCH_PNL_RATIO_THRESHOLD: float = 5.0  # §6.2: realized_pnl/buy_notional > this → flag
MAX_ADV_PARTICIPATION_PCT: float = 5.0  # §6.5: avg trade < 5% of liquidity-floor ADV


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Outcome of one §6 robustness check."""

    name: str  # e.g. "§6.1 Cost stress"
    passed: bool
    summary: str  # one-line verdict — no softening (Rule 12)
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _candidate_config(date_from: date, date_to: date) -> MomentumConfig:
    """Floor MomentumConfig defaults pinned to [date_from, date_to]."""
    return MomentumConfig(date_from=date_from, date_to=date_to)


def _equity_series(result: engine.EngineResult) -> pd.Series:
    return pd.Series(
        [s.equity for s in result.snapshots],
        index=pd.DatetimeIndex([pd.Timestamp(s.date) for s in result.snapshots]),
    )


def _run(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    date_from: date,
    date_to: date,
    cost_level: str = "base",
    signal_store=None,
) -> tuple[engine.EngineResult, metrics.BacktestMetrics]:
    """Run the candidate on [date_from, date_to] and return (result, metrics)."""
    cfg = _candidate_config(date_from, date_to)
    result = engine.run(
        prices,
        cfg,
        index_prices=index_prices,
        regime_config=CANDIDATE_REGIME,
        cost_level=cost_level,
        signal_store=signal_store,
    )
    m = metrics.compute_metrics(result)
    return result, m


# ---------------------------------------------------------------------------
# §6.1 Cost stress
# ---------------------------------------------------------------------------


def check_cost_stress(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    ledger: ConfigLedger,
    signal_store=None,
) -> CheckResult:
    """§6.1: candidate beats Nifty50 TRI Calmar at pessimistic cost on DISCOVERY."""
    ledger.add(
        {"regime": dataclasses.asdict(CANDIDATE_REGIME), "cost_level": "pessimistic"},
        check="§6.1_cost_stress",
    )
    result, m = _run(
        prices,
        index_prices,
        DISCOVERY[0],
        DISCOVERY[1],
        cost_level="pessimistic",
        signal_store=signal_store,
    )

    cfg = _candidate_config(DISCOVERY[0], DISCOVERY[1])
    trading_cal = [pd.Timestamp(s.date) for s in result.snapshots]
    tri = benchmark.load_tri(
        benchmark.TRI_NIFTY_50, _BENCH_FETCH_START, _BENCH_FETCH_END
    )
    bench = benchmark.align_benchmark(
        tri, cfg.date_from, trading_cal, cfg.starting_capital
    )
    bm = metrics.compute_benchmark_metrics(_equity_series(result), bench)

    passed = bm.calmar_ratio >= 1.0
    summary = (
        f"PASS — calmar_ratio {bm.calmar_ratio:.2f} >= 1.0 at pessimistic cost"
        if passed
        else (
            f"FAIL — calmar_ratio {bm.calmar_ratio:.2f} < 1.0: "
            "can't beat Nifty50 at worst-case cost"
        )
    )
    return CheckResult(
        name="§6.1 Cost stress",
        passed=passed,
        summary=summary,
        details={
            "cost_level": "pessimistic",
            "c_strat": round(bm.strategy_calmar, 3),
            "c_nifty50": round(bm.benchmark_calmar, 3),
            "calmar_ratio": round(bm.calmar_ratio, 2),
        },
    )


# ---------------------------------------------------------------------------
# §6.2 Universe perturbation
# ---------------------------------------------------------------------------


def check_universe_perturbation(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    ledger: ConfigLedger,
    base_metrics: metrics.BacktestMetrics,
    signal_store=None,
) -> CheckResult:
    """§6.2: drop top-N P&L contributors; Calmar retains >= threshold.

    Uses the original signal_store with perturbed prices because the engine
    derives its universe from _membership (built from prices), so dropped ISINs
    are structurally excluded from ranking even with the full signal_store.
    """
    sorted_names = sorted(
        base_metrics.per_name_stats,
        key=lambda ns: ns.realized_pnl,
        reverse=True,
    )
    top_n = sorted_names[:N_TOP_CONTRIBUTORS]
    top_isins: set[str] = {ns.isin for ns in top_n}
    top_symbols: list[str] = [ns.symbol for ns in top_n]

    # Cross-check for data glitches: realized_pnl/buy_notional > threshold is suspicious.
    glitch_flags: list[str] = []
    for ns in top_n:
        if ns.buy_notional > 0:
            ratio = ns.realized_pnl / ns.buy_notional
            if ratio > GLITCH_PNL_RATIO_THRESHOLD:
                glitch_flags.append(f"{ns.symbol} pnl_ratio={ratio:.1f}x")

    prices_perturbed = prices[~prices["isin"].isin(top_isins)].copy()
    ledger.add(
        {"n_dropped": N_TOP_CONTRIBUTORS, "dropped_symbols": top_symbols},
        check="§6.2_universe_perturb",
    )
    _, m_perturbed = _run(
        prices_perturbed,
        index_prices,
        DISCOVERY[0],
        DISCOVERY[1],
        cost_level="base",
        signal_store=signal_store,
    )

    base_calmar = base_metrics.calmar
    if base_calmar > 0 and not math.isnan(base_calmar):
        retention = m_perturbed.calmar / base_calmar
    else:
        retention = float("nan")

    passed = (not math.isnan(retention)) and retention >= UNIVERSE_PERTURB_THRESHOLD
    summary = (
        f"PASS — Calmar retention {retention:.0%} >= {UNIVERSE_PERTURB_THRESHOLD:.0%} "
        f"after dropping top-{N_TOP_CONTRIBUTORS} names"
        if passed
        else (
            f"FAIL — Calmar retention {retention:.0%} < {UNIVERSE_PERTURB_THRESHOLD:.0%}: "
            "edge concentrated in top names"
        )
    )
    return CheckResult(
        name="§6.2 Universe perturbation",
        passed=passed,
        summary=summary,
        details={
            "base_calmar": round(base_calmar, 3),
            "perturbed_calmar": round(m_perturbed.calmar, 3),
            "calmar_retention": round(retention, 2)
            if not math.isnan(retention)
            else "n/a",
            "top_contributors": top_symbols,
            "glitch_flags": glitch_flags,
        },
    )


# ---------------------------------------------------------------------------
# §6.3 Parameter neighborhood
# ---------------------------------------------------------------------------


def check_neighborhood(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    ledger: ConfigLedger,
    signal_store=None,
) -> CheckResult:
    """§6.3: plateau check — candidate + immediate neighbors in regime-param space.

    Runs a 6-combo grid (debounce × risk_off) centred on the T3 winner and
    re-applies the same plateau_check from iterate.py so the criterion is
    identical to T3's acceptance test.
    """
    cfg = _candidate_config(DISCOVERY[0], DISCOVERY[1])
    ss = signal_store if signal_store is not None else precompute_signals(prices, cfg)

    combos = [(d, r) for d in _NBR_DEBOUNCE for r in _NBR_RISK_OFF]
    points: list[GridPoint] = []
    for debounce, risk_off in combos:
        trial_id = ledger.add(
            {"debounce_days": debounce, "risk_off_floor": risk_off},
            check="§6.3_neighborhood",
        )
        regime_cfg = RegimeConfig(debounce_days=debounce, risk_off_floor=risk_off)
        result = engine.run(
            prices,
            cfg,
            index_prices=index_prices,
            regime_config=regime_cfg,
            cost_level="base",
            signal_store=ss,
        )
        m = metrics.compute_metrics(result)
        points.append(
            GridPoint(
                params={"debounce_days": debounce, "risk_off_floor": risk_off},
                trial_id=trial_id,
                calmar=m.calmar,
                sharpe=m.sharpe,
                cagr=m.cagr,
                max_dd=m.max_drawdown,
            )
        )
        log.info(
            "  nbr debounce=%d  rof=%.2f  calmar=%.3f", debounce, risk_off, m.calmar
        )

    axes: list[tuple[str, list]] = [
        ("debounce_days", _NBR_DEBOUNCE),
        ("risk_off_floor", _NBR_RISK_OFF),
    ]
    verdict = plateau_check(points, axes, tolerance=0.85)

    passed = verdict.has_plateau
    summary = (
        f"PASS — {verdict.explanation}" if passed else f"FAIL — {verdict.explanation}"
    )
    min_nbr = (
        round(min(n.calmar for n in verdict.neighbors), 3)
        if verdict.neighbors
        else "n/a"
    )
    return CheckResult(
        name="§6.3 Parameter neighborhood",
        passed=passed,
        summary=summary,
        details={
            "n_combos": len(combos),
            "winner_calmar": round(verdict.winner.calmar, 3),
            "winner_params": verdict.winner.params,
            "n_neighbors": len(verdict.neighbors),
            "min_neighbor_calmar": min_nbr,
        },
    )


# ---------------------------------------------------------------------------
# §6.4 Subperiod stability
# ---------------------------------------------------------------------------


def check_subperiod_stability(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    ledger: ConfigLedger,
    signal_store=None,
) -> CheckResult:
    """§6.4: positive Calmar in >= SUBPERIOD_MIN_POSITIVE of 3 market-cycle periods.

    WHY this check exists: v1's edge was almost entirely the 2021 bull market —
    a single-regime fluke.  Requiring positive Calmar across distinct market
    conditions (chop, bull, correction) guards against that failure mode.
    """
    subresults: list[tuple[str, metrics.BacktestMetrics]] = []
    for label, start, end in SUBPERIODS:
        ledger.add(
            {"subperiod": label, "start": str(start), "end": str(end)},
            check="§6.4_subperiod",
        )
        _, m = _run(
            prices,
            index_prices,
            start,
            end,
            cost_level="base",
            signal_store=signal_store,
        )
        subresults.append((label, m))
        log.info(
            "  Subperiod '%s': calmar=%.3f  cagr=%.2f%%",
            label,
            m.calmar,
            m.cagr * 100,
        )

    n_positive = sum(
        1 for _, m in subresults if not math.isnan(m.calmar) and m.calmar > 0
    )
    passed = n_positive >= SUBPERIOD_MIN_POSITIVE

    calmar_map = {lbl: round(m.calmar, 3) for lbl, m in subresults}
    cagr_map = {lbl: round(m.cagr * 100, 2) for lbl, m in subresults}

    summary = (
        f"PASS — {n_positive}/{len(SUBPERIODS)} subperiods have positive Calmar"
        if passed
        else (
            f"FAIL — only {n_positive}/{len(SUBPERIODS)} subperiods positive Calmar "
            f"(need >= {SUBPERIOD_MIN_POSITIVE}): single-regime trap"
        )
    )
    return CheckResult(
        name="§6.4 Subperiod stability",
        passed=passed,
        summary=summary,
        details={
            "n_positive": n_positive,
            "min_required": SUBPERIOD_MIN_POSITIVE,
            "calmar_per_subperiod": calmar_map,
            "cagr_per_subperiod_%": cagr_map,
        },
    )


# ---------------------------------------------------------------------------
# §6.5 Turnover / capacity
# ---------------------------------------------------------------------------


def check_turnover_capacity(
    base_metrics: metrics.BacktestMetrics,
    capital: float = 1_000_000.0,
    liquidity_floor_cr: float = 5.0,
) -> CheckResult:
    """§6.5: avg trade participation << ADV floor; no market-impact risk at ₹10L.

    Participation = avg_trade_inr / ADV_floor_inr.  Every held stock has ADV20 >=
    liquidity_floor_cr crore (MomentumConfig.liquidity_floor_cr default), so the
    floor ADV is the worst-case denominator — the real participation will be lower.
    """
    ann_turnover_frac = base_metrics.annualized_turnover
    years = base_metrics.n_calendar_days / 365.25
    n_fills = max(base_metrics.n_fills, 1)

    # Total one-way notional (buys only = half of round-trip turnover)
    total_one_way_inr = capital * ann_turnover_frac * years / 2.0
    avg_trade_inr = total_one_way_inr / n_fills

    adv_floor_inr = liquidity_floor_cr * 1e7  # 1 crore = 10M ₹
    participation_pct = (avg_trade_inr / adv_floor_inr) * 100.0

    passed = participation_pct < MAX_ADV_PARTICIPATION_PCT
    lakh = capital / 1e5
    summary = (
        f"PASS — avg participation {participation_pct:.3f}% < "
        f"{MAX_ADV_PARTICIPATION_PCT:.0f}% of ADV floor at ₹{lakh:.0f}L capital"
        if passed
        else (
            f"FAIL — avg participation {participation_pct:.3f}% >= "
            f"{MAX_ADV_PARTICIPATION_PCT:.0f}%: position sizes exceed safe zone"
        )
    )
    return CheckResult(
        name="§6.5 Turnover / capacity",
        passed=passed,
        summary=summary,
        details={
            "ann_turnover_%": round(ann_turnover_frac * 100, 1),
            "n_fills": base_metrics.n_fills,
            "avg_trade_inr": round(avg_trade_inr, 0),
            "adv_floor_inr": adv_floor_inr,
            "participation_%": round(participation_pct, 3),
            "capital_inr": capital,
        },
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(results: list[CheckResult]) -> None:
    print()
    print("=" * 72)
    print("  SPEC 04 T4 — ROBUSTNESS CHECKS  (T3 candidate: layer-1 plateau winner)")
    print(f"  Candidate: {CANDIDATE_REGIME}")
    print(f"  Window:    DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
    print("=" * 72)

    for cr in results:
        mark = "  PASS" if cr.passed else "  FAIL"
        print(f"\n{mark}  {cr.name}")
        print(f"       {cr.summary}")
        for k, v in cr.details.items():
            if k not in ("top_contributors", "glitch_flags", "winner_params"):
                print(f"       {k}: {v}")
        if cr.details.get("glitch_flags"):
            print(f"       ⚠ glitch-flag candidates: {cr.details['glitch_flags']}")
        if cr.details.get("top_contributors"):
            print(f"       top contributors dropped: {cr.details['top_contributors']}")

    all_pass = all(r.passed for r in results)
    print()
    print("=" * 72)
    print(
        f"  T4 OVERALL: >>> {'ALL PASS — proceed to T5' if all_pass else 'ONE OR MORE FAILED — do not open T5'} <<<"
    )
    print("=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for _noisy in (
        "app.backtest_v2.portfolio",
        "app.backtest_v2.engine",
        "app.core.strategy",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(_noisy).setLevel(logging.ERROR)

    print("Spec 04 T4 — Robustness Checks")
    print(f"  Candidate regime: {CANDIDATE_REGIME}")
    print()

    print("Loading prices_adjusted...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(
        f"  rows={len(prices):,}  ISINs={prices['isin'].nunique():,}"
        f"  range={prices['date'].min().date()} → {prices['date'].max().date()}",
        flush=True,
    )

    print("Loading real Nifty 50 price index (cached from T1)...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    except Exception as exc:
        print(f"FAIL: regime index unavailable: {exc}", file=sys.stderr)
        return 2

    ledger = ConfigLedger()

    # Precompute signals on DISCOVERY once — reused by §6.1, §6.2, §6.3, §6.4
    print("Precomputing signals on DISCOVERY window...", flush=True)
    disc_config = _candidate_config(DISCOVERY[0], DISCOVERY[1])
    signal_store = precompute_signals(prices, disc_config)

    # Base run at base cost (needed for §6.2 per_name_stats and §6.5 metrics)
    print("Base run (base cost, DISCOVERY)...", flush=True)
    ledger.add(
        {"regime": dataclasses.asdict(CANDIDATE_REGIME), "cost_level": "base"},
        check="base_reference",
    )
    base_result, base_m = _run(
        prices,
        index_prices,
        DISCOVERY[0],
        DISCOVERY[1],
        cost_level="base",
        signal_store=signal_store,
    )
    print(
        f"  calmar={base_m.calmar:.3f}  sharpe={base_m.sharpe:.3f}"
        f"  cagr={base_m.cagr * 100:.2f}%  maxdd={base_m.max_drawdown:.2%}"
        f"  turnover={base_m.annualized_turnover * 100:.0f}%",
        flush=True,
    )

    checks: list[CheckResult] = []

    print("\n§6.1 Cost stress (pessimistic cost)...", flush=True)
    checks.append(
        check_cost_stress(prices, index_prices, ledger, signal_store=signal_store)
    )

    print("§6.2 Universe perturbation (drop top-10 P&L names)...", flush=True)
    checks.append(
        check_universe_perturbation(
            prices, index_prices, ledger, base_m, signal_store=signal_store
        )
    )

    print("§6.3 Parameter neighborhood (6-combo grid)...", flush=True)
    checks.append(
        check_neighborhood(prices, index_prices, ledger, signal_store=signal_store)
    )

    print("§6.4 Subperiod stability (3 market-cycle periods)...", flush=True)
    checks.append(
        check_subperiod_stability(
            prices, index_prices, ledger, signal_store=signal_store
        )
    )

    print("§6.5 Turnover / capacity...", flush=True)
    checks.append(check_turnover_capacity(base_m))

    _print_report(checks)
    print(f"\n  Total trials in ledger (K): {ledger.n_trials}")
    print("  (K feeds deflated_sharpe in T5 — report raw Sharpe and K together.)")

    return 0 if all(c.passed for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
