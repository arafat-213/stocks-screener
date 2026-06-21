"""
r10_battery.py — R10.2: full §6 battery + §5 acceptance on the locked S3, DISCOVERY only.

Pre-registration: `specs/v3/10_SKEW_REVALIDATION_PREREG.md` §5/§6/§12 + the §13 post-hoc
deviation (Arafat 2026-06-21). R10.1's dense §6.3 lattice FAILED (U=400 neighbour 83% <
85%); §13 overrides the §5 null and authorizes this battery + a one-shot OOS as an
EXPLORATORY run. §6.3 is the ONLY waived gate — everything else stays HARD.

Single candidate: S3 (stable U=350, B=1.25, 5-factor TRACK_A_BASELINE, N=20, M=130,
sm=0, monthly, regime ON). Mirrors su2_battery's plumbing, narrowed to one config and
extended with the §2c fair-costed deployment bar at base AND pessimistic cost.

Gates (§5 items 1–5):
  1. §6.1  pessimistic-cost Calmar ratio ≥ 1.0 vs Nifty50 TRI       — HARD (re-confirm SU1 1.51)
  2. §6.2  skew-aware retention (median≥70% / p5≥50% / rot≥25)      — HARD; ADOPTED from the
           committed su_md_skew_recheck S3 result (91% / 72% / 55), byte-identical config
           (`10` §5.2 permits adoption; re-run optional). Classic drop-top-10 reported (35% FAIL).
  3. §6.3  dense-lattice plateau                                    — FAILED (R10.1), WAIVED per §13
  4. deploy §2c: beats the FAIR-COSTED Nifty200 Mom30 on base Calmar AND stays above it at
           pessimistic, maxDD ≤ 100% of benchmark; zero-cost TRI reported as cross-check — HARD
  5. §6.5  capacity (avg participation < 5% ADV floor)             — HARD
  §6.4  subperiod stability — DIAGNOSTIC (not gating).

A deploy-bar FAIL at pessimistic cost is an INDEPENDENT null (§13.2) — the §6.3 waiver
waives nothing else. DISCOVERY only — FINAL_OOS stays pristine (R10.3 spends it, once).

Run:
    backend/venv/bin/python -m app.backtest_v2.r10_battery
"""

from __future__ import annotations

import gc
import logging
import math
import sys
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.costs import CostConfig
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.stable_universe import build_stable_universe_mask
from app.backtest_v2.v3_config import TRACK_A_BASELINE, V3Config
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# Frozen S3 construction (`10` §3).
_U, _B, _M = 350, 1.25, 130
_SMOOTHING = 0
_CADENCE = "monthly"
_S3_ANCHOR = 0.575
_ANCHOR_TOL = 0.01

# §6.1 / §6.5 thresholds (carried, NOT relaxed).
_S61_RATIO_FLOOR = 1.0
_MAX_ADV_PARTICIPATION_PCT = 5.0
_LIQUIDITY_FLOOR_CR = 5.0

# §6.2 skew-aware — ADOPTED from the committed su_md_skew_recheck S3 run (commit 713d450a,
# byte-identical config; `10` §5.2 permits adoption). NOT re-run here (Rule 6 — 200-draw
# perturbation already on the record + ledger). Classic drop-top-10 reported alongside.
_S62_SKEW_MEDIAN = 0.91
_S62_SKEW_P5 = 0.72
_S62_SKEW_ROT = 55
_S62_SKEW_PASS = True  # 91% ≥ 70% AND 72% ≥ 50% AND 55 ≥ 25
_S62_CLASSIC_RETENTION = (
    0.35  # FAIL — the contaminated gate (the "conditional" label driver)
)

# §6.3 — FAILED in R10.1 (U=400 neighbour 0.479 = 83% < 85%), WAIVED per §13.
_S63_FAILED_WAIVED = True

# §2c fair-costed Mom30 — explicit, documented drag (see _annual_fair_cost_drag).
_ETF_EXPENSE_ANNUAL = 0.0030  # ~0.30%/yr ETF expense ratio (`10` §2c)
_INDEX_TWOWAY_TURNOVER = 1.00  # assumed index two-way turnover/yr (see note in drag fn)

# §6.4 subperiods — identical to su2_battery (fixed before any run, Rule 12).
SUBPERIODS: list[tuple[str, date, date]] = [
    ("Pre-COVID chop", date(2018, 2, 6), date(2020, 3, 31)),
    ("Post-COVID bull", date(2020, 4, 1), date(2022, 1, 31)),
    ("Rate-hike correction", date(2022, 2, 1), date(2023, 6, 30)),
]


@dataclass
class BatteryResult:
    base_calmar: float
    base_max_dd: float
    base_turnover_pct: float
    base_sharpe: float
    anchor_ok: bool
    # §6.1
    pess_calmar: float
    s61_ratio: float
    s61_pass: bool
    # §6.2 (adopted)
    s62_median: float
    s62_p5: float
    s62_rot: int
    s62_pass: bool
    s62_classic: float
    # §6.4 diagnostic
    s64_calmar_per_period: dict[str, float] = field(default_factory=dict)
    s64_n_positive: int = 0
    # §6.5
    s65_participation_pct: float = 0.0
    s65_pass: bool = False
    # deploy bar §2c (base)
    dep_base_strat: float = 0.0
    dep_base_fair: float = 0.0
    dep_base_zerocost: float = 0.0
    dep_base_dd_ratio: float = 0.0
    dep_base_pass: bool = False
    # deploy bar §2c (pessimistic — the binding test)
    dep_pess_strat: float = 0.0
    dep_pess_fair: float = 0.0
    dep_pess_dd_ratio: float = 0.0
    dep_pess_pass: bool = False
    fair_drag_base: float = 0.0
    fair_drag_pess: float = 0.0
    # §5 acceptance
    advance_to_oos: bool = False


def _v3_config(date_from: date, date_to: date) -> V3Config:
    return V3Config(
        active_factors=list(TRACK_A_BASELINE.active_factors),
        rebalance_cadence=_CADENCE,
        sell_rank_buffer=_M,
        rank_smoothing_months=_SMOOTHING,
        target_positions=TRACK_A_BASELINE.target_positions,
        use_regime_overlay=True,
        catastrophic_stop_pct=25.0,
        liquidity_floor_cr=5.0,
        universe_mode="stable",
        universe_size_U=_U,
        universe_buffer_B=_B,
        date_from=date_from,
        date_to=date_to,
    )


def _engine_cfg(v3cfg: V3Config, date_from: date, date_to: date) -> MomentumConfig:
    return MomentumConfig(
        target_positions=v3cfg.target_positions,
        sell_rank_buffer=v3cfg.sell_rank_buffer,
        liquidity_floor_cr=v3cfg.liquidity_floor_cr,
        momentum_lookback_days=v3cfg.momentum_lookback_days,
        momentum_skip_days=v3cfg.momentum_skip_days,
        vol_lookback_days=v3cfg.vol_lookback_days,
        trend_ma=v3cfg.trend_ma,
        max_position_pct=v3cfg.max_position_pct,
        starting_capital=v3cfg.starting_capital,
        use_regime_overlay=v3cfg.use_regime_overlay,
        catastrophic_stop_pct=v3cfg.catastrophic_stop_pct,
        rebalance=v3cfg.rebalance_cadence,
        date_from=date_from,
        date_to=date_to,
    )


def _equity_series(result: engine.EngineResult) -> pd.Series:
    return pd.Series(
        [s.equity for s in result.snapshots],
        index=pd.DatetimeIndex([pd.Timestamp(s.date) for s in result.snapshots]),
    )


def _annual_fair_cost_drag(cost_level: str) -> float:
    """Annual cost drag for an investable (passive-replication) Nifty200 Mom30 ETF.

    `10` §2c: TRI minus the index's own replication turnover (through the same costs.py)
    minus an ETF expense (~0.30%/yr). Implemented as a transparent constant annual drag:

      drag = ETF_expense + replication_cost
      replication_cost = (T_idx / 2) × buy_rate + (T_idx / 2) × sell_rate

    where T_idx is the index two-way turnover/yr (assumed 1.00 — momentum indices
    reconstitute semi-annually and are high-turnover; a HIGHER assumption only LOWERS
    the bar further). Per-side rates use the statutory model + slippage FLOOR only (a
    passive ETF trades at negligible ADV participation → no impact term). base vs
    pessimistic differ solely in the slippage floor (costs.py).

    Guard against lowering the bar (`10` §2c): S3 already beats the HARDER zero-cost TRI
    (0.575 > 0.473), so this fair-costed bar cannot be accused of being engineered to pass.
    The zero-cost TRI is retained and reported as the conservative cross-check.
    """
    cfg = CostConfig.base() if cost_level == "base" else CostConfig.pessimistic()
    statutory_both = (cfg.exchange_txn_pct + cfg.sebi_pct) * (1.0 + cfg.gst_pct)
    buy_rate = cfg.stt_pct + cfg.stamp_duty_pct + cfg.base_slippage_pct + statutory_both
    sell_rate = cfg.stt_pct + cfg.base_slippage_pct + statutory_both
    repl = (_INDEX_TWOWAY_TURNOVER / 2.0) * (buy_rate + sell_rate)
    return _ETF_EXPENSE_ANNUAL + repl


def _apply_fair_cost(tri: pd.Series, annual_drag: float) -> pd.Series:
    """Geometric constant-drag fair-costing. The downstream rebase at date_from makes
    the accrued drag relative to the live-trading start, so applying it on the full
    series is correct (costed_t / costed_from = (tri_t/tri_from)·(1-d)^Δyears)."""
    years = (tri.index - tri.index[0]).days / 365.25
    return tri * ((1.0 - annual_drag) ** years)


def check_s65(m: metrics.BacktestMetrics) -> dict:
    capital = m.start_equity or 1_000_000.0
    years = m.n_calendar_days / 365.25
    n_fills = max(m.n_fills, 1)
    total_one_way = capital * m.annualized_turnover * years / 2.0
    avg_trade = total_one_way / n_fills
    participation_pct = (avg_trade / (_LIQUIDITY_FLOOR_CR * 1e7)) * 100.0
    return {
        "participation_pct": round(participation_pct, 3),
        "passes": participation_pct < _MAX_ADV_PARTICIPATION_PCT,
    }


def run_battery(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    tri_mom30: pd.Series,
    tri_nifty50: pd.Series,
    composite: pd.DataFrame,
    gate_ind,
    ledger: ConfigLedger,
) -> BatteryResult:
    v3cfg = _v3_config(*DISCOVERY)
    mask = build_stable_universe_mask(
        prices, _U, _B, v3cfg.universe_rank_lookback_td, v3cfg.universe_review_cadence
    )
    ss = V3SignalStore(gate_ind, composite, v3cfg, universe_mask=mask)
    payload = {"config": "S3", "U": _U, "B": _B, "M": _M, "stage_note": "R10.2"}

    # -- Base run (reproduce 0.575) --
    eng_base = _engine_cfg(v3cfg, *DISCOVERY)
    ledger.add({**payload, "cost_level": "base"}, stage="R10_battery_base")
    res_base = engine.run(
        prices, eng_base, index_prices=index_prices, cost_level="base", signal_store=ss
    )
    m_base = metrics.compute_metrics(res_base)
    anchor_ok = abs(m_base.calmar - _S3_ANCHOR) <= _ANCHOR_TOL
    log.info(
        "  [base] calmar=%.3f (anchor %.3f %s)  maxdd=%.1f%%  turn=%.0f%%  sharpe=%.3f",
        m_base.calmar,
        _S3_ANCHOR,
        "OK" if anchor_ok else "MISMATCH",
        m_base.max_drawdown * 100,
        m_base.annualized_turnover * 100,
        m_base.sharpe,
    )
    base_equity = _equity_series(res_base)
    trading_cal = [pd.Timestamp(s.date) for s in res_base.snapshots]

    # -- Pessimistic run (§6.1 + deploy-pessimistic) --
    ledger.add({**payload, "cost_level": "pessimistic"}, stage="R10_battery_pess")
    res_pess = engine.run(
        prices,
        eng_base,
        index_prices=index_prices,
        cost_level="pessimistic",
        signal_store=ss,
    )
    m_pess = metrics.compute_metrics(res_pess)
    pess_equity = _equity_series(res_pess)
    log.info(
        "  [pessimistic] calmar=%.3f  maxdd=%.1f%%",
        m_pess.calmar,
        m_pess.max_drawdown * 100,
    )

    # -- §6.1: pessimistic Calmar ratio vs Nifty50 TRI ≥ 1.0 (re-confirm SU1 1.51) --
    n50_aligned = benchmark.align_benchmark(
        tri_nifty50, eng_base.date_from, trading_cal, eng_base.starting_capital
    )
    bm_n50 = metrics.compute_benchmark_metrics(pess_equity, n50_aligned)
    s61_ratio = bm_n50.calmar_ratio
    s61_pass = (not math.isnan(s61_ratio)) and s61_ratio >= _S61_RATIO_FLOOR
    log.info(
        "  [§6.1] pess Calmar %.3f / Nifty50 TRI %.3f = ratio %.2f → %s",
        m_pess.calmar,
        bm_n50.benchmark_calmar,
        s61_ratio,
        "PASS" if s61_pass else "FAIL",
    )

    # -- §6.4 subperiods (diagnostic) --
    s64_map: dict[str, float] = {}
    for label, sub_s, sub_e in SUBPERIODS:
        v3_sub = _v3_config(sub_s, sub_e)
        eng_sub = _engine_cfg(v3_sub, sub_s, sub_e)
        ss_sub = V3SignalStore(gate_ind, composite, v3_sub, universe_mask=mask)
        res_sub = engine.run(
            prices,
            eng_sub,
            index_prices=index_prices,
            cost_level="base",
            signal_store=ss_sub,
        )
        s64_map[label] = round(metrics.compute_metrics(res_sub).calmar, 3)
        ledger.add({**payload, "subperiod": label}, stage="R10_battery_s64")
        del res_sub, ss_sub
        gc.collect()
    s64_n_pos = sum(1 for c in s64_map.values() if c > 0)
    log.info(
        "  [§6.4 diagnostic] %s  (n_positive=%d/3)",
        {k: v for k, v in s64_map.items()},
        s64_n_pos,
    )

    # -- §6.5 capacity --
    s65 = check_s65(m_base)
    log.info(
        "  [§6.5] participation=%.3f%% → %s",
        s65["participation_pct"],
        "PASS" if s65["passes"] else "FAIL",
    )

    # -- Deploy bar §2c: fair-costed Mom30 at base + pessimistic; zero-cost TRI cross-check --
    drag_base = _annual_fair_cost_drag("base")
    drag_pess = _annual_fair_cost_drag("pessimistic")
    fair_base = _apply_fair_cost(tri_mom30, drag_base)
    fair_pess = _apply_fair_cost(tri_mom30, drag_pess)

    # zero-cost TRI Calmar (cross-check) + fair-costed-base Calmar; compared to S3 base.
    zc_aligned = benchmark.align_benchmark(
        tri_mom30, eng_base.date_from, trading_cal, eng_base.starting_capital
    )
    bm_zc = metrics.compute_benchmark_metrics(base_equity, zc_aligned)
    fb_aligned = benchmark.align_benchmark(
        fair_base, eng_base.date_from, trading_cal, eng_base.starting_capital
    )
    bm_fb = metrics.compute_benchmark_metrics(base_equity, fb_aligned)
    dep_base_pass = (
        bm_fb.strategy_calmar > bm_fb.benchmark_calmar
        and not math.isnan(bm_fb.max_dd_ratio)
        and bm_fb.max_dd_ratio <= 1.0
    )
    log.info(
        "  [deploy base] S3 %.3f vs fair-Mom30 %.3f (drag %.2f%%/yr; zero-cost TRI %.3f), "
        "dd_ratio %.2f → %s",
        bm_fb.strategy_calmar,
        bm_fb.benchmark_calmar,
        drag_base * 100,
        bm_zc.benchmark_calmar,
        bm_fb.max_dd_ratio,
        "PASS" if dep_base_pass else "FAIL",
    )

    # Pessimistic — the binding test: S3 pessimistic Calmar vs fair-costed-pessimistic Mom30.
    fp_aligned = benchmark.align_benchmark(
        fair_pess,
        eng_base.date_from,
        [pd.Timestamp(s.date) for s in res_pess.snapshots],
        eng_base.starting_capital,
    )
    bm_fp = metrics.compute_benchmark_metrics(pess_equity, fp_aligned)
    dep_pess_pass = (
        bm_fp.strategy_calmar > bm_fp.benchmark_calmar
        and not math.isnan(bm_fp.max_dd_ratio)
        and bm_fp.max_dd_ratio <= 1.0
    )
    log.info(
        "  [deploy pessimistic — BINDING] S3 %.3f vs fair-Mom30 %.3f (drag %.2f%%/yr), "
        "dd_ratio %.2f → %s",
        bm_fp.strategy_calmar,
        bm_fp.benchmark_calmar,
        drag_pess * 100,
        bm_fp.max_dd_ratio,
        "PASS" if dep_pess_pass else "FAIL",
    )

    # -- §5 acceptance: items 1,2,4,5 HARD; item 3 (§6.3) FAILED-but-WAIVED per §13 --
    advance = (
        s61_pass
        and _S62_SKEW_PASS
        and dep_base_pass
        and dep_pess_pass
        and s65["passes"]
    )

    return BatteryResult(
        base_calmar=m_base.calmar,
        base_max_dd=m_base.max_drawdown,
        base_turnover_pct=m_base.annualized_turnover * 100,
        base_sharpe=m_base.sharpe,
        anchor_ok=anchor_ok,
        pess_calmar=m_pess.calmar,
        s61_ratio=s61_ratio,
        s61_pass=s61_pass,
        s62_median=_S62_SKEW_MEDIAN,
        s62_p5=_S62_SKEW_P5,
        s62_rot=_S62_SKEW_ROT,
        s62_pass=_S62_SKEW_PASS,
        s62_classic=_S62_CLASSIC_RETENTION,
        s64_calmar_per_period=s64_map,
        s64_n_positive=s64_n_pos,
        s65_participation_pct=s65["participation_pct"],
        s65_pass=s65["passes"],
        dep_base_strat=bm_fb.strategy_calmar,
        dep_base_fair=bm_fb.benchmark_calmar,
        dep_base_zerocost=bm_zc.benchmark_calmar,
        dep_base_dd_ratio=bm_fb.max_dd_ratio,
        dep_base_pass=dep_base_pass,
        dep_pess_strat=bm_fp.strategy_calmar,
        dep_pess_fair=bm_fp.benchmark_calmar,
        dep_pess_dd_ratio=bm_fp.max_dd_ratio,
        dep_pess_pass=dep_pess_pass,
        fair_drag_base=drag_base,
        fair_drag_pess=drag_pess,
        advance_to_oos=advance,
    )


def _print_report(r: BatteryResult) -> None:
    sep = "=" * 88
    print(f"\n{sep}")
    print(
        "  R10.2 — FULL §6 BATTERY + §5 ACCEPTANCE on S3 (EXPLORATORY, under §13 deviation)"
    )
    print(
        f"  DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]} | S3 = stable U={_U} B={_B}, 5-factor, M={_M}"
    )
    print(
        "  §6.3 FAILED in R10.1 (U=400 83%<85%) — WAIVED per §13; verdict ceiling = 'exploratory'"
    )
    print(sep)
    print(
        f"\n  base Calmar {r.base_calmar:.3f} (anchor {_S3_ANCHOR:.3f} "
        f"{'REPRODUCED' if r.anchor_ok else 'MISMATCH — FAIL LOUD'}), "
        f"maxDD {r.base_max_dd:.1%}, turnover {r.base_turnover_pct:.0f}%, Sharpe {r.base_sharpe:.3f}"
    )

    print(
        f"\n  §6.1  pessimistic Calmar {r.pess_calmar:.3f} / Nifty50 TRI → ratio {r.s61_ratio:.2f} "
        f"(≥{_S61_RATIO_FLOOR:.1f}) → {'PASS' if r.s61_pass else 'FAIL'}  [HARD]"
    )
    print(
        f"\n  §6.2  skew-aware (ADOPTED, su_md_skew_recheck 713d450a) → "
        f"{'PASS' if r.s62_pass else 'FAIL'}  [HARD]"
    )
    print(
        f"        median {r.s62_median:.0%} (≥70%) · p5 {r.s62_p5:.0%} (≥50%) · "
        f"rotation {r.s62_rot} (≥25)"
    )
    print(
        f"        classic drop-top-10 {r.s62_classic:.0%} → FAIL (contaminated guard) ⇒ "
        f"'conditional' name-concentration caveat"
    )
    print(
        "\n  §6.3  dense-lattice plateau → FAILED (R10.1 U=400 83%<85%) — WAIVED per §13  [not gating here]"
    )
    print(
        f"\n  §6.4  subperiod stability — DIAGNOSTIC (not gating), n_positive {r.s64_n_positive}/3"
    )
    for k, v in r.s64_calmar_per_period.items():
        print(f"        {k:24s} calmar={v:.3f}")
    print(
        f"\n  §6.5  capacity participation {r.s65_participation_pct:.3f}% (<5%) → "
        f"{'PASS' if r.s65_pass else 'FAIL'}  [HARD]"
    )

    print("\n  DEPLOY BAR §2c (fair-costed investable Nifty200 Mom30)  [HARD]")
    print(
        f"        base:        S3 {r.dep_base_strat:.3f} vs fair {r.dep_base_fair:.3f} "
        f"(drag {r.fair_drag_base * 100:.2f}%/yr) | zero-cost TRI {r.dep_base_zerocost:.3f} "
        f"| dd_ratio {r.dep_base_dd_ratio:.2f} → {'PASS' if r.dep_base_pass else 'FAIL'}"
    )
    print(
        f"        pessimistic: S3 {r.dep_pess_strat:.3f} vs fair {r.dep_pess_fair:.3f} "
        f"(drag {r.fair_drag_pess * 100:.2f}%/yr) | dd_ratio {r.dep_pess_dd_ratio:.2f} "
        f"→ {'PASS' if r.dep_pess_pass else 'FAIL'}  ← BINDING"
    )

    print(f"\n{sep}")
    if r.advance_to_oos:
        print(
            "  §5 ACCEPTANCE: items 1,2,4,5 PASS; item 3 (§6.3) FAILED-but-WAIVED per §13."
        )
        print(
            "  → S3 ADVANCES to R10.3 one-shot FINAL_OOS as an EXPLORATORY candidate."
        )
        print(
            "    Verdict ceiling capped at 'exploratory / disclosed-deviation' — NEVER 'validated'."
        )
        print(
            "    Conditional name-concentration caveat carried (classic drop-top-10 35%)."
        )
    else:
        fails = []
        if not r.s61_pass:
            fails.append("§6.1")
        if not r.s62_pass:
            fails.append("§6.2-skew")
        if not r.dep_base_pass:
            fails.append("deploy-base")
        if not r.dep_pess_pass:
            fails.append("deploy-pessimistic")
        if not r.s65_pass:
            fails.append("§6.5")
        print(
            f"  §5 ACCEPTANCE: INDEPENDENT NULL — failed HARD gate(s): {', '.join(fails)}."
        )
        print(
            "  Per §13.2 the §6.3 waiver waives nothing else; FINAL_OOS NOT performed, stays pristine."
        )
    print("  FINAL_OOS untouched in R10.2.")
    print(sep)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in (
        "app.backtest_v2",
        "app.core.strategy",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(noisy).setLevel(logging.ERROR)
    logging.getLogger(__name__).setLevel(logging.INFO)

    print("R10.2 — full §6 battery + §5 acceptance on S3 (exploratory, §13 deviation)")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")

    print("Loading prices_adjusted (offline cache)...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices[
        prices["date"] <= pd.Timestamp(DISCOVERY[1])
    ].copy()  # DISCOVERY-only
    print(
        f"  rows={len(prices):,}  ISINs={prices['isin'].nunique():,}"
        f"  (sliced ≤ DISCOVERY end {DISCOVERY[1]})",
        flush=True,
    )

    print("Loading Nifty 50 price index (regime overlay)...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    except Exception as exc:
        print(f"FAIL: regime index unavailable: {exc}", file=sys.stderr)
        return 2

    print(
        "Loading REAL Nifty200 Momentum 30 TRI (deploy bar) + Nifty50 TRI (§6.1)...",
        flush=True,
    )
    try:
        tri_mom30 = benchmark.load_tri(
            benchmark.TRI_MOMENTUM_30, _BENCH_FETCH_START, _BENCH_FETCH_END
        )
        tri_nifty50 = benchmark.load_tri(
            benchmark.TRI_NIFTY_50, _BENCH_FETCH_START, _BENCH_FETCH_END
        )
    except Exception as exc:
        print(f"FAIL: TRI unavailable: {exc}", file=sys.stderr)
        return 2

    ref_v3 = _v3_config(*DISCOVERY)
    print("Precomputing v2 gate cache + 5-factor composite (shared)...", flush=True)
    gate_store = precompute_signals(prices, _engine_cfg(ref_v3, *DISCOVERY))
    gate_ind = gate_store._data
    composite = factors.composite_rank(prices, ref_v3)

    ledger = ConfigLedger()
    r = run_battery(
        prices, index_prices, tri_mom30, tri_nifty50, composite, gate_ind, ledger
    )
    _print_report(r)
    print(
        f"\n  ConfigLedger entries this run (K added): {ledger.n_trials}  | FINAL_OOS untouched."
    )

    if not r.anchor_ok:
        print(
            f"  ANCHOR MISMATCH — base {r.base_calmar:.3f} != {_S3_ANCHOR}",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
