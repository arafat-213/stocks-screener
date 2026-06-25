"""
v47_turnover_screen.py — v4 / 05 V4.7: turnover-first Stage-1 cost screen on DISCOVERY.

Pre-registration: specs/v4/05_TURNOVER_TREND_PREREG.md §3/§4 (Stage 1) / §5 (anti-thrash
diagnostic) / §6.1 (cost survival) / §11 (V4.7). DISCOVERY only — v4-FINAL_OOS stays
pristine; no §6.2/§6.3/§6.4 battery here (that is V4.8, and only on a §6.1 survivor).

What this runs (everything except the four `05` §3 levers is byte-frozen at the
`00`/Amendment-1/`04` candidate: MOM selector, 5-factor regime, stable U=200,
target_positions=15, ₹3.5L, whole-share, −25% floor):

  Stage-1 grid (§4 — at the CANDIDATE deployment neutral_fraction=0.75, the fix-(a)
  decision: §6.1 gates the actual deployed candidate, not the deploy-stripped 0.5 book):
      atr_mult ∈ {3.0, 4.0, 5.0}  ×  decision_cadence ∈ {daily, weekly}  = 6 configs
      candidate = atr_mult 4.0 / weekly. For each: base + pessimistic cost.
      §6.1 ratio = C_strat(pess) / C_nifty50 ≥ 1.0 clears. K accrues ×1 per config (R1).

  Anchors (R3 → 0 to K — parity / diagnostic, NOT new trials):
      MOM-0.5 anchor: MOM / atr 3.0 / daily / neutral 0.5  → must re-derive V4.4 ~0.179.
      ADV   anchor:   adv / atr 3.0 / daily / neutral 0.5  → must re-derive V4.1 ~0.083.

  §5 anti-thrash diagnostic (NON-GATING, 0 to K): the Stage-1 candidate (atr 4.0 / weekly
  / 0.75) with vs without min_hold_td=10 + reentry_cooldown_td=10 (base cost). Reports
  turnover / median hold / fills / expectancy; pre-committed read decides whether a
  SEPARATE future amendment is authorized (never changes the candidate this run).

Run:
    backend/venv/bin/python -m app.swing_v4.v47_turnover_screen
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

import pandas as pd

from app.backtest_v2 import benchmark, metrics
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store
from app.swing_v4 import engine
from app.swing_v4.config import SwingConfig
from app.swing_v4.regime import RegimeScore
from app.swing_v4.signals import precompute_swing_signals
from app.swing_v4.v41_cost_screen import (
    _BENCH_FETCH_END,
    _BENCH_FETCH_START,
    _avg_hold,
    _candidate_config,
    _s61_ratio,
)
from app.swing_v4.v44_selector_screen import TradeForensic, _forensic

log = logging.getLogger(__name__)

# `05` §3.1/§3.2/§4 — the Stage-1 turnover grid (at the candidate deployment 0.75).
_ATR_MULTS = [3.0, 4.0, 5.0]
_CADENCES = ["daily", "weekly"]
_CANDIDATE_ATR = 4.0
_CANDIDATE_CADENCE = "weekly"
_CANDIDATE_NEUTRAL = 0.75  # fix (a): Stage-1 §6.1 gates the candidate deployment
_FROZEN_NEUTRAL = 0.5  # the V4.4/V4.1 anchor deployment

# `05` §7.1 parity anchors (R3 → 0 to K).
_MOM_PARITY_BASE_CALMAR = 0.179  # V4.4 MOM/atr3/daily/0.5 base Calmar
_ADV_PARITY_BASE_CALMAR = 0.083  # V4.1 ADV/atr3/daily/0.5 base Calmar
_ADV_PARITY_PESS_RATIO = 0.11
_PARITY_TOL = 0.015  # absolute Calmar/ratio tolerance for re-derivation

# `05` §5 anti-thrash diagnostic bundle (10 td each, per §5).
_MIN_HOLD_TD = 10
_REENTRY_COOLDOWN_TD = 10


def _cfg(
    *, atr_mult: float, cadence: str, selector: str = "mom", **overrides
) -> SwingConfig:
    """The frozen `05` candidate scoped to DISCOVERY, with only the named §3 levers
    overridden. neutral_fraction is NOT a SwingConfig field — it lives on the RegimeScore."""
    return _candidate_config(
        exit_type=3,
        atr_mult=atr_mult,
        decision_cadence=cadence,
        selector=selector,
        **overrides,
    )


def _run(
    cfg: SwingConfig, *, prices, regime, signal_store, cost_level: str
) -> engine.SwingEngineResult:
    return engine.run(
        prices,
        cfg,
        regime=regime,
        signal_store=signal_store,
        cost_level=cost_level,
        whole_shares=True,
    )


@dataclass
class GridRow:
    atr_mult: float
    cadence: str
    base_calmar: float
    base_max_dd: float
    base_sharpe: float
    base_cagr: float
    turnover_pct: float
    win_rate: float
    avg_hold_days: float
    n_fills: int
    calmar_ratio: float
    passes_s61: bool
    is_candidate: bool
    forensic: TradeForensic


def _screen(
    prices, regime, signal_store, tri_nifty50, ledger: ConfigLedger
) -> tuple[list[GridRow], engine.SwingEngineResult | None]:
    rows: list[GridRow] = []
    candidate_base: engine.SwingEngineResult | None = None
    n = len(_ATR_MULTS) * len(_CADENCES)
    i = 0
    for atr in _ATR_MULTS:
        for cad in _CADENCES:
            i += 1
            is_cand = atr == _CANDIDATE_ATR and cad == _CANDIDATE_CADENCE
            log.info(
                "[%d/%d] atr=%.1f cadence=%s%s ...",
                i,
                n,
                atr,
                cad,
                "  (candidate)" if is_cand else "",
            )
            cfg = _cfg(atr_mult=atr, cadence=cad)
            # R1: ONE ledger entry per config — base + pessimistic score the SAME strategy
            # under two cost models (cost is an evaluation assumption, not a trial, §7.0).
            ledger.add(
                {
                    "atr_mult": atr,
                    "decision_cadence": cad,
                    "neutral_fraction": _CANDIDATE_NEUTRAL,
                    "selector": "mom",
                },
                stage="V4.7_stage1",
            )

            res_base = _run(
                cfg,
                prices=prices,
                regime=regime,
                signal_store=signal_store,
                cost_level="base",
            )
            m = metrics.compute_metrics(res_base)
            fr = _forensic(res_base)
            if is_cand:
                candidate_base = res_base

            res_pess = _run(
                cfg,
                prices=prices,
                regime=regime,
                signal_store=signal_store,
                cost_level="pessimistic",
            )
            _c_strat, _c_n50, ratio = _s61_ratio(
                res_pess, tri_nifty50, cfg.starting_capital
            )

            rows.append(
                GridRow(
                    atr_mult=atr,
                    cadence=cad,
                    base_calmar=m.calmar,
                    base_max_dd=m.max_drawdown,
                    base_sharpe=m.sharpe,
                    base_cagr=m.cagr,
                    turnover_pct=m.annualized_turnover * 100,
                    win_rate=m.hit_rate,
                    avg_hold_days=_avg_hold(m),
                    n_fills=m.n_fills,
                    calmar_ratio=ratio,
                    passes_s61=ratio >= 1.0,
                    is_candidate=is_cand,
                    forensic=fr,
                )
            )
            log.info(
                "    base calmar=%.3f maxdd=%.1f%% turn=%.0f%% | pess ratio=%.2f %s | "
                "trips=%d medHold=%.0fd exp=%+.2f%%",
                m.calmar,
                m.max_drawdown * 100,
                m.annualized_turnover * 100,
                ratio,
                "PASS" if ratio >= 1.0 else "FAIL",
                fr.n_closed,
                fr.median_hold,
                fr.expectancy * 100,
            )
    return rows, candidate_base


@dataclass
class AntiThrash:
    base_turnover: float
    base_median_hold: float
    base_fills: int
    base_expectancy: float
    base_calmar: float
    on_turnover: float
    on_median_hold: float
    on_fills: int
    on_expectancy: float
    on_calmar: float
    read: str


def _anti_thrash(
    prices, regime, signal_store, candidate_base: engine.SwingEngineResult
) -> AntiThrash:
    """§5 NON-GATING anti-thrash diagnostic on the Stage-1 candidate (base cost)."""
    m_off = metrics.compute_metrics(candidate_base)
    fr_off = _forensic(candidate_base)

    cfg_on = _cfg(
        atr_mult=_CANDIDATE_ATR,
        cadence=_CANDIDATE_CADENCE,
        min_hold_td=_MIN_HOLD_TD,
        reentry_cooldown_td=_REENTRY_COOLDOWN_TD,
    )
    res_on = _run(
        cfg_on,
        prices=prices,
        regime=regime,
        signal_store=signal_store,
        cost_level="base",
    )
    m_on = metrics.compute_metrics(res_on)
    fr_on = _forensic(res_on)

    # Pre-committed read (`05` §5, decided before any number): a meaningful turnover cut
    # AND a held/improved Calmar authorizes a SEPARATE future amendment; otherwise inert.
    turn_cut = (m_off.annualized_turnover - m_on.annualized_turnover) / max(
        m_off.annualized_turnover, 1e-9
    )
    if turn_cut >= 0.10 and m_on.calmar >= m_off.calmar:
        read = (
            "anti-thrash-is-a-lever"  # authorizes a separate future amendment (own K)
        )
    else:
        read = "anti-thrash-inert"  # confirms `03` (no whipsaw to suppress); leave off
    return AntiThrash(
        base_turnover=m_off.annualized_turnover * 100,
        base_median_hold=fr_off.median_hold,
        base_fills=m_off.n_fills,
        base_expectancy=fr_off.expectancy * 100,
        base_calmar=m_off.calmar,
        on_turnover=m_on.annualized_turnover * 100,
        on_median_hold=fr_on.median_hold,
        on_fills=m_on.n_fills,
        on_expectancy=fr_on.expectancy * 100,
        on_calmar=m_on.calmar,
        read=read,
    )


def _emit(lines: list[str], s: str = "") -> None:
    print(s, flush=True)
    lines.append(s)


def _report(
    rows: list[GridRow],
    anti: AntiThrash,
    mom_parity: str,
    mom_ok: bool,
    adv_parity: str,
    adv_ok: bool,
    ledger: ConfigLedger,
) -> list[str]:
    L: list[str] = []
    _emit(L)
    _emit(L, "=" * 112)
    _emit(
        L,
        "  V4.7 Stage 1 — turnover-first §6.1 cost screen  (DISCOVERY "
        f"{DISCOVERY[0]} → {DISCOVERY[1]})",
    )
    _emit(
        L,
        "  Frozen: MOM selector, entry 4-cond, 5-factor regime, stable U=200, "
        "target_positions=15, ₹3.5L, whole-share, −25% floor",
    )
    _emit(
        L,
        f"  Levers: atr_mult{{3,4,5}} × cadence{{daily,weekly}} at neutral_fraction="
        f"{_CANDIDATE_NEUTRAL} (fix-(a): gate the deployed candidate)",
    )
    _emit(L, "=" * 112)
    _emit(
        L,
        f"  {'atr':>4} {'cadence':>7} | {'Calmar':>7} | {'MaxDD':>6} | {'Sharpe':>6} | "
        f"{'CAGR':>6} | {'Turn%':>6} | {'Win%':>5} | {'Hold':>5} | {'Ratio(P)':>8} | §6.1",
    )
    _emit(L, "  " + "─" * 106)
    for r in rows:
        win = f"{r.win_rate * 100:.0f}" if r.win_rate == r.win_rate else "n/a"
        hold = f"{r.avg_hold_days:.0f}" if r.avg_hold_days == r.avg_hold_days else "n/a"
        mark = " *" if r.is_candidate else "  "
        _emit(
            L,
            f"  {r.atr_mult:>4.1f} {r.cadence:>7} | {r.base_calmar:>7.3f} | "
            f"{r.base_max_dd:>5.1%} | {r.base_sharpe:>6.2f} | {r.base_cagr:>5.1%} | "
            f"{r.turnover_pct:>6.0f} | {win:>5} | {hold:>5} | {r.calmar_ratio:>8.2f} | "
            f"{'PASS' if r.passes_s61 else 'FAIL'}{mark}",
        )
    _emit(L, "  (* = §4 candidate: atr 4.0 / weekly / neutral 0.75)")

    # per-round-trip forensic
    _emit(L)
    _emit(L, "-" * 112)
    _emit(
        L,
        "  per-round-trip forensic (base cost — `03` species: does a lever cut cost faster than it gives back edge?)",
    )
    _emit(L, "-" * 112)
    _emit(
        L,
        f"  {'atr':>4} {'cadence':>7} | {'trips':>5} | {'open':>4} | {'win%':>5} | "
        f"{'avgWin':>7} | {'avgLoss':>7} | {'payoff':>6} | {'expectancy':>10} | {'medHold':>7}",
    )
    for r in rows:
        f = r.forensic
        _emit(
            L,
            f"  {r.atr_mult:>4.1f} {r.cadence:>7} | {f.n_closed:>5} | {f.n_open:>4} | "
            f"{f.win_rate * 100:>4.0f}% | {f.avg_win * 100:>+6.2f}% | "
            f"{f.avg_loss * 100:>+6.2f}% | {f.payoff:>6.2f} | "
            f"{f.expectancy * 100:>+9.2f}% | {f.median_hold:>6.0f}d",
        )

    # parity anchors (R3 → 0 to K)
    _emit(L)
    _emit(L, "-" * 112)
    _emit(
        L,
        "  parity anchors (R3 → 0 to K — the frozen-deployment cells must re-derive V4.4/V4.1)",
    )
    _emit(L, "-" * 112)
    _emit(L, f"    MOM-0.5 (atr3/daily/0.5): {mom_parity}")
    _emit(
        L,
        f"      → {'OK' if mom_ok else '⚠ DRIFT — investigate before trusting the screen'}",
    )
    _emit(L, f"    ADV     (atr3/daily/0.5): {adv_parity}")
    _emit(
        L,
        f"      → {'OK' if adv_ok else '⚠ DRIFT — investigate before trusting the screen'}",
    )

    # §5 anti-thrash diagnostic
    _emit(L)
    _emit(L, "-" * 112)
    _emit(
        L,
        "  §5 anti-thrash diagnostic (NON-GATING, 0 to K — candidate atr4/weekly/0.75, base cost)",
    )
    _emit(L, "-" * 112)
    _emit(
        L,
        f"    OFF (min_hold=0,  cooldown=0):  turn {anti.base_turnover:>5.0f}% | "
        f"medHold {anti.base_median_hold:>3.0f}d | fills {anti.base_fills:>4} | "
        f"exp {anti.base_expectancy:>+5.2f}% | Calmar {anti.base_calmar:.3f}",
    )
    _emit(
        L,
        f"    ON  (min_hold={_MIN_HOLD_TD}, cooldown={_REENTRY_COOLDOWN_TD}): "
        f"turn {anti.on_turnover:>5.0f}% | medHold {anti.on_median_hold:>3.0f}d | "
        f"fills {anti.on_fills:>4} | exp {anti.on_expectancy:>+5.2f}% | "
        f"Calmar {anti.on_calmar:.3f}",
    )
    if anti.read == "anti-thrash-is-a-lever":
        _emit(
            L,
            "    → READ: ANTI-THRASH IS A LEVER (≥10% turnover cut AND Calmar held/improved) — authorizes a SEPARATE future amendment (own K). Candidate UNCHANGED.",
        )
    else:
        _emit(
            L,
            "    → READ: ANTI-THRASH INERT (confirms `03`: median hold ~42d, ~3.9% ≤10d — no whipsaw to suppress). Leave off.",
        )

    # §6.1 survivors / verdict
    survivors = [r for r in rows if r.passes_s61]
    _emit(L)
    _emit(L, "=" * 112)
    _emit(
        L,
        f"  §6.1 survivors (pessimistic Calmar ratio ≥ 1.0 vs Nifty 50 TRI): {len(survivors)}/{len(rows)}",
    )
    if survivors:
        for r in survivors:
            _emit(
                L,
                f"    → atr {r.atr_mult} / {r.cadence}: base Calmar {r.base_calmar:.3f}, "
                f"ratio {r.calmar_ratio:.2f} — carries to V4.8 battery",
            )
        _emit(
            L,
            "  V4.8 (full §6 battery + 0.5 deploy plateau-neighbor) runs next on the §6.1-clearing set (`05` §4 Stage 2).",
        )
    else:
        _emit(
            L,
            "    → NULL — no turnover config clears §6.1. Per `05` §6 pre-accepted null: the\n"
            "      turnover lever does NOT rescue the thin trend edge; the v4 family is\n"
            "      PERMANENTLY closed as a research note; v4-FINAL_OOS is NOT touched; no\n"
            "      grid level added, no threshold loosened. Redirect (cheaper execution regime\n"
            "      / different premise) per `05` §8 — NOT another knob, NOT a re-grid.",
        )
    _emit(L)
    _emit(
        L,
        f"  v4 ledger K (this run): {ledger.n_trials} new (cost ×1 per config, R1; anchors + "
        f"anti-thrash = 0). Carried v4 K = 4 ⇒ K so far ≈ {4 + ledger.n_trials} (Stage 2 adds the 0.5 plateau).",
    )
    _emit(L, "  v4-FINAL_OOS untouched.")
    _emit(L, "=" * 112)
    return L


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in (
        "app.backtest_v2.portfolio",
        "app.backtest_v2",
        "app.swing_v4.engine",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    print("v4 / 05 V4.7 — turnover-first Stage-1 cost screen on DISCOVERY")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
    print(
        "  Grid: atr_mult{3,4,5} × cadence{daily,weekly} at neutral_fraction=0.75 (MOM frozen)"
    )
    print()

    print(
        "Loading prices_adjusted (offline cache, full history for warmup)...",
        flush=True,
    )
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(
        f"  rows={len(prices):,} ISINs={prices['isin'].nunique():,} "
        f"range={prices['date'].min().date()} → {prices['date'].max().date()}",
        flush=True,
    )

    print("Loading Nifty 50 price index + market_internals (regime)...", flush=True)
    px = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    mi = store.read_market_internals()
    if mi.empty:
        print("FAIL: market_internals empty.", file=sys.stderr)
        return 2
    print("Loading Nifty 50 TRI (§6.1 benchmark)...", flush=True)
    tri_nifty50 = benchmark.load_tri(
        benchmark.TRI_NIFTY_50, _BENCH_FETCH_START, _BENCH_FETCH_END
    )

    print("Precomputing swing signals (mom column shared across grid)...", flush=True)
    ref_cfg = _cfg(atr_mult=_CANDIDATE_ATR, cadence=_CANDIDATE_CADENCE)
    signal_store = precompute_swing_signals(prices, ref_cfg)
    regime_075 = RegimeScore(px, mi, ref_cfg, neutral_fraction=_CANDIDATE_NEUTRAL)
    regime_05 = RegimeScore(px, mi, ref_cfg, neutral_fraction=_FROZEN_NEUTRAL)

    ledger = ConfigLedger()
    print(
        "\nScreening the §4 turnover grid (base + pessimistic, whole-share, ₹3.5L)...",
        flush=True,
    )
    rows, candidate_base = _screen(
        prices, regime_075, signal_store, tri_nifty50, ledger
    )

    # Parity anchors (R3 → 0 to K): re-derive the frozen-deployment V4.4/V4.1 cells.
    print("\nRe-deriving parity anchors (MOM-0.5, ADV-0.5 — R3, 0 to K)...", flush=True)
    mom_anchor = _run(
        _cfg(atr_mult=3.0, cadence="daily"),
        prices=prices,
        regime=regime_05,
        signal_store=signal_store,
        cost_level="base",
    )
    mom_cal = metrics.compute_metrics(mom_anchor).calmar
    mom_ok = abs(mom_cal - _MOM_PARITY_BASE_CALMAR) <= _PARITY_TOL
    mom_parity = f"base Calmar {mom_cal:.3f} (V4.4 ~{_MOM_PARITY_BASE_CALMAR}); |Δ|={abs(mom_cal - _MOM_PARITY_BASE_CALMAR):.3f} (tol {_PARITY_TOL})"

    adv_base = _run(
        _cfg(atr_mult=3.0, cadence="daily", selector="adv"),
        prices=prices,
        regime=regime_05,
        signal_store=signal_store,
        cost_level="base",
    )
    adv_cal = metrics.compute_metrics(adv_base).calmar
    adv_pess = _run(
        _cfg(atr_mult=3.0, cadence="daily", selector="adv"),
        prices=prices,
        regime=regime_05,
        signal_store=signal_store,
        cost_level="pessimistic",
    )
    _cs, _cn, adv_ratio = _s61_ratio(
        adv_pess, tri_nifty50, adv_base.config.starting_capital
    )
    adv_ok = (
        abs(adv_cal - _ADV_PARITY_BASE_CALMAR) <= _PARITY_TOL
        and abs(adv_ratio - _ADV_PARITY_PESS_RATIO) <= _PARITY_TOL
    )
    adv_parity = (
        f"base Calmar {adv_cal:.3f} (V4.1 ~{_ADV_PARITY_BASE_CALMAR}); "
        f"pess ratio {adv_ratio:.2f} (V4.1 ~{_ADV_PARITY_PESS_RATIO}); "
        f"|Δcalmar|={abs(adv_cal - _ADV_PARITY_BASE_CALMAR):.3f}"
    )

    print(
        "\nRunning the §5 anti-thrash diagnostic (candidate ± min-hold/cooldown)...",
        flush=True,
    )
    if candidate_base is None:
        print("FAIL: candidate base run missing.", file=sys.stderr)
        return 2
    anti = _anti_thrash(prices, regime_075, signal_store, candidate_base)

    lines = _report(rows, anti, mom_parity, mom_ok, adv_parity, adv_ok, ledger)

    out_path = "reports/v47_turnover_screen.txt"
    try:
        with open(out_path, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"\n(report written to backend/{out_path})", flush=True)
    except OSError as e:  # pragma: no cover — non-fatal
        print(f"\n(could not write report: {e})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
