"""
v44_selector_screen.py — v4 / 04 V4.4: return-informed selector Stage-1 cost screen.

Pre-registration: specs/v4/04_SELECTOR_PREREG.md §3/§4 (Stage 1) / §5 (deployment
diagnostic) / §6 (acceptance) / §11 (V4.4 execution). DISCOVERY only — v4-FINAL_OOS
stays pristine; no §6.2/§6.3 battery here (that is V4.5).

What this runs (everything except the SELECTOR is byte-frozen at the `00`/Amendment-1
candidate: exit Type-3 ATR 3×, 5-factor regime, stable U=200, target_positions=15,
₹3.5L, whole-share):

  Stage-1 selector grid (§3/§4 — the candidate + the two comparators, NOTHING else):
      MOM  selector="mom"  126-td trailing return       — the registered candidate
      RS   selector="rs"   excess vs Nifty 50 126-td     — comparator (≡ MOM, §3 identity)
      ADV  selector="adv"  adv_20 (closed V4.1 engine)   — liquidity baseline / gap

  For each selector:
    - base cost        → base Calmar, maxDD, Sharpe, turnover, win rate, avg hold
                         + the `03` per-round-trip forensic (win/payoff/expectancy/hold).
    - pessimistic cost → §6.1 ratio = C_strat / C_nifty50  (≥ 1.0 clears §6.1).
    - both logged to ConfigLedger (K accrues — `04` §7; carries from the v4 family ≥6).

  ADV-baseline parity (§11 done-criteria): the ADV selector IS the closed V4.1 T3 engine,
  so its base Calmar must re-derive ~0.083 and its pessimistic ratio ~0.11. Checked + flagged.

  §5 deployment diagnostic (NON-GATING, adds 0 to K — `04` §5): the candidate selector at
  the frozen overlay (D_base) vs a deploy-more overlay (D_more: Neutral 0.5→0.75). Reports
  Calmar + maxDD + CAGR for both; pre-committed read decides whether a SEPARATE future
  amendment is authorized (never changes the candidate this run).

Run:
    backend/venv/bin/python -m app.swing_v4.v44_selector_screen
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

import numpy as np
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
from app.swing_v4.v41_forensic import _reconstruct_trades

log = logging.getLogger(__name__)

# `04` §3/§4 — the selector grid. Candidate first, then the two comparators. Nothing else.
_SELECTORS: list[tuple[str, str, str]] = [
    ("MOM", "mom", "candidate — 126-td trailing return"),
    ("RS", "rs", "comparator — excess vs Nifty 50 (≡ MOM by construction, §3)"),
    ("ADV", "adv", "baseline — closed V4.1 engine (adv_20 liquidity)"),
]

# §11 ADV-baseline parity anchors (the closed V4.1 T3 candidate, `03` headline / `00` §13).
_ADV_PARITY_BASE_CALMAR = 0.083
_ADV_PARITY_PESS_RATIO = 0.11
_PARITY_TOL = 0.01  # absolute Calmar/ratio tolerance for the re-derivation check

# `04` §5 — the D_more deploy-more overlay: Neutral bucket 0.5 → 0.75 (Bear 0, Bull 1).
_DEPLOY_MORE_NEUTRAL = 0.75


# ---------------------------------------------------------------------------
# Engine run (passes nifty50_price so the "rs" selector has its benchmark term)
# ---------------------------------------------------------------------------


def _run_sel(
    cfg: SwingConfig,
    *,
    prices: pd.DataFrame,
    regime: RegimeScore,
    signal_store,
    cost_level: str,
    whole_shares: bool,
    nifty50_price: pd.Series | None = None,
) -> engine.SwingEngineResult:
    return engine.run(
        prices,
        cfg,
        regime=regime,
        signal_store=signal_store,
        cost_level=cost_level,
        whole_shares=whole_shares,
        nifty50_price=nifty50_price,
    )


# ---------------------------------------------------------------------------
# Per-round-trip forensic (the `03` species — reuses its trade reconstructor)
# ---------------------------------------------------------------------------


@dataclass
class TradeForensic:
    n_closed: int
    n_open: int
    win_rate: float
    avg_win: float
    avg_loss: float
    payoff: float
    expectancy: float  # net, per round-trip
    median_hold: float


def _forensic(res: engine.SwingEngineResult) -> TradeForensic:
    trades = _reconstruct_trades(res.fills_log, res.exit_log)
    closed = [t for t in trades if t.exit_reason != "still_open"]
    opens = [t for t in trades if t.exit_reason == "still_open"]
    rets = np.array([t.ret_pct for t in closed], dtype=float)
    wins = rets[rets > 0]
    losses = rets[rets <= 0]
    holds = np.array([t.hold_days for t in closed if t.hold_days == t.hold_days])
    avg_win = float(np.mean(wins)) if len(wins) else float("nan")
    avg_loss = float(np.mean(losses)) if len(losses) else float("nan")
    return TradeForensic(
        n_closed=len(closed),
        n_open=len(opens),
        win_rate=(len(wins) / len(rets)) if len(rets) else float("nan"),
        avg_win=avg_win,
        avg_loss=avg_loss,
        payoff=(avg_win / abs(avg_loss))
        if (len(wins) and len(losses) and avg_loss != 0)
        else float("nan"),
        expectancy=float(np.mean(rets)) if len(rets) else float("nan"),
        median_hold=float(np.median(holds)) if len(holds) else float("nan"),
    )


# ---------------------------------------------------------------------------
# Stage-1 selector screen
# ---------------------------------------------------------------------------


@dataclass
class SelRow:
    name: str
    role: str
    selector: str
    base_calmar: float
    base_max_dd: float
    base_sharpe: float
    base_cagr: float
    turnover_pct: float
    win_rate: float
    avg_hold_days: float
    n_fills: int
    c_strat_pessimistic: float
    c_nifty50: float
    calmar_ratio: float
    passes_s61: bool
    forensic: TradeForensic


def _screen_selectors(
    prices: pd.DataFrame,
    regime: RegimeScore,
    signal_store,
    tri_nifty50: pd.Series,
    px: pd.Series,
    ledger: ConfigLedger,
) -> list[SelRow]:
    rows: list[SelRow] = []
    for i, (name, sel, role) in enumerate(_SELECTORS, 1):
        log.info("[%d/%d] %s (%s)...", i, len(_SELECTORS), name, role)
        cfg = _candidate_config(exit_type=3, selector=sel)
        # "rs" needs the Nifty 50 trailing return; adv/mom never read it (pass None).
        nifty_px = px if sel == "rs" else None
        payload = {"selector": sel, "exit_type": 3, "target_positions": 15}

        ledger.add({**payload, "cost_level": "base"}, stage="V4.4_base")
        res_base = _run_sel(
            cfg,
            prices=prices,
            regime=regime,
            signal_store=signal_store,
            cost_level="base",
            whole_shares=True,
            nifty50_price=nifty_px,
        )
        m = metrics.compute_metrics(res_base)
        fr = _forensic(res_base)

        ledger.add({**payload, "cost_level": "pessimistic"}, stage="V4.4_pessimistic")
        res_pess = _run_sel(
            cfg,
            prices=prices,
            regime=regime,
            signal_store=signal_store,
            cost_level="pessimistic",
            whole_shares=True,
            nifty50_price=nifty_px,
        )
        c_strat, c_n50, ratio = _s61_ratio(res_pess, tri_nifty50, cfg.starting_capital)

        rows.append(
            SelRow(
                name=name,
                role=role,
                selector=sel,
                base_calmar=m.calmar,
                base_max_dd=m.max_drawdown,
                base_sharpe=m.sharpe,
                base_cagr=m.cagr,
                turnover_pct=m.annualized_turnover * 100,
                win_rate=m.hit_rate,
                avg_hold_days=_avg_hold(m),
                n_fills=m.n_fills,
                c_strat_pessimistic=c_strat,
                c_nifty50=c_n50,
                calmar_ratio=ratio,
                passes_s61=ratio >= 1.0,
                forensic=fr,
            )
        )
        log.info(
            "    base calmar=%.3f maxdd=%.1f%% turn=%.0f%% | pess ratio=%.2f %s | "
            "trips=%d exp=%+.2f%% payoff=%.2f",
            m.calmar,
            m.max_drawdown * 100,
            m.annualized_turnover * 100,
            ratio,
            "PASS" if ratio >= 1.0 else "FAIL",
            fr.n_closed,
            fr.expectancy * 100,
            fr.payoff,
        )
    return rows


# ---------------------------------------------------------------------------
# §5 deployment diagnostic (non-gating; adds 0 to K)
# ---------------------------------------------------------------------------


@dataclass
class DeployDiag:
    base_calmar: float
    base_max_dd: float
    base_cagr: float
    more_calmar: float
    more_max_dd: float
    more_cagr: float
    bench_max_dd: float
    read: str


def _deployment_diag(
    prices: pd.DataFrame,
    regime_base: RegimeScore,
    regime_more: RegimeScore,
    signal_store,
    px: pd.Series,
    tri_nifty50: pd.Series,
) -> DeployDiag:
    cfg = _candidate_config(exit_type=3, selector="mom")  # the candidate selector
    res_base = _run_sel(
        cfg,
        prices=prices,
        regime=regime_base,
        signal_store=signal_store,
        cost_level="base",
        whole_shares=True,
    )
    res_more = _run_sel(
        cfg,
        prices=prices,
        regime=regime_more,
        signal_store=signal_store,
        cost_level="base",
        whole_shares=True,
    )
    mb = metrics.compute_metrics(res_base)
    mm = metrics.compute_metrics(res_more)

    # Deployment bar denominator: Nifty 50 TRI maxDD over the same trading calendar.
    trading_cal = [pd.Timestamp(s.date) for s in res_base.snapshots]
    bench = benchmark.align_benchmark(
        tri_nifty50, DISCOVERY[0], trading_cal, cfg.starting_capital
    )
    bench_dd = _equity_max_dd(bench)

    # Pre-committed read (`04` §5 — decided before any number):
    if mm.calmar <= mb.calmar:
        read = "overlay-earns-keep"  # CAGR rose but maxDD rose at least as fast
    elif mm.max_drawdown <= bench_dd:
        read = "deployment-is-a-lever"  # materially better AND maxDD ≤ benchmark
    else:
        read = "ambiguous"  # higher Calmar but maxDD breaches the deploy bar
    return DeployDiag(
        base_calmar=mb.calmar,
        base_max_dd=mb.max_drawdown,
        base_cagr=mb.cagr,
        more_calmar=mm.calmar,
        more_max_dd=mm.max_drawdown,
        more_cagr=mm.cagr,
        bench_max_dd=bench_dd,
        read=read,
    )


def _equity_max_dd(equity: pd.Series) -> float:
    """Peak-to-trough max drawdown of an equity series (positive fraction)."""
    eq = equity.dropna().astype(float)
    if eq.empty:
        return float("nan")
    peak = eq.cummax()
    dd = (peak - eq) / peak
    return float(dd.max())


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _emit(lines: list[str], s: str = "") -> None:
    print(s, flush=True)
    lines.append(s)


def _report(
    rows: list[SelRow],
    diag: DeployDiag,
    parity_ok: bool,
    parity_note: str,
    ledger: ConfigLedger,
) -> list[str]:
    L: list[str] = []
    _emit(L)
    _emit(L, "=" * 110)
    _emit(
        L,
        "  V4.4 Stage 1 — return-informed selector §6.1 cost screen  "
        "(DISCOVERY 2018-02-06 → 2023-06-30)",
    )
    _emit(
        L,
        "  Frozen: entry 4-cond, exit Type-3 ATR 3×, 5-factor regime, stable U=200, "
        "target_positions=15, ₹3.5L, whole-share",
    )
    _emit(L, "=" * 110)
    _emit(
        L,
        f"  {'Sel':>3} | {'Calmar':>7} | {'MaxDD':>6} | {'Sharpe':>6} | {'CAGR':>6} | "
        f"{'Turn%':>6} | {'Win%':>5} | {'Hold':>5} | {'Ratio(P)':>8} | §6.1",
    )
    _emit(L, "  " + "─" * 104)
    for r in rows:
        win = f"{r.win_rate * 100:.0f}" if r.win_rate == r.win_rate else "n/a"
        hold = f"{r.avg_hold_days:.0f}" if r.avg_hold_days == r.avg_hold_days else "n/a"
        _emit(
            L,
            f"  {r.name:>3} | {r.base_calmar:>7.3f} | {r.base_max_dd:>5.1%} | "
            f"{r.base_sharpe:>6.2f} | {r.base_cagr:>5.1%} | {r.turnover_pct:>6.0f} | "
            f"{win:>5} | {hold:>5} | {r.calmar_ratio:>8.2f} | "
            f"{'PASS' if r.passes_s61 else 'FAIL'}",
        )
    _emit(L, "  (roles: " + "; ".join(f"{r.name}={r.role}" for r in rows) + ")")

    # per-round-trip forensic (the `03` species)
    _emit(L)
    _emit(L, "-" * 110)
    _emit(
        L,
        "  per-round-trip forensic (base cost — `03` species; how the selector reshapes the trade population)",
    )
    _emit(L, "-" * 110)
    _emit(
        L,
        f"  {'Sel':>3} | {'trips':>5} | {'open':>4} | {'win%':>5} | {'avgWin':>7} | "
        f"{'avgLoss':>7} | {'payoff':>6} | {'expectancy':>10} | {'medHold':>7}",
    )
    for r in rows:
        f = r.forensic
        _emit(
            L,
            f"  {r.name:>3} | {f.n_closed:>5} | {f.n_open:>4} | "
            f"{f.win_rate * 100:>4.0f}% | {f.avg_win * 100:>+6.2f}% | "
            f"{f.avg_loss * 100:>+6.2f}% | {f.payoff:>6.2f} | "
            f"{f.expectancy * 100:>+9.2f}% | {f.median_hold:>6.0f}d",
        )

    # ADV-baseline parity
    _emit(L)
    _emit(L, "-" * 110)
    _emit(
        L,
        "  ADV-baseline parity check (§11 done-criteria — the closed V4.1 T3 engine must re-derive)",
    )
    _emit(L, "-" * 110)
    _emit(L, f"    {parity_note}")
    _emit(
        L,
        f"    parity: {'OK' if parity_ok else '⚠ DRIFT — investigate before trusting the screen'}",
    )

    # MOM ≡ RS identity check (empirical confirmation of §3)
    mom = next((r for r in rows if r.selector == "mom"), None)
    rs = next((r for r in rows if r.selector == "rs"), None)
    if mom and rs:
        identical = (
            abs(mom.base_calmar - rs.base_calmar) < 1e-9
            and abs(mom.calmar_ratio - rs.calmar_ratio) < 1e-9
            and mom.n_fills == rs.n_fills
        )
        _emit(L)
        _emit(L, "-" * 110)
        _emit(
            L,
            "  MOM ≡ RS identity (§3 — the Nifty term is one per-day constant ⇒ same cross-sectional order)",
        )
        _emit(L, "-" * 110)
        _emit(
            L,
            f"    MOM base Calmar {mom.base_calmar:.4f} / ratio {mom.calmar_ratio:.4f} / fills {mom.n_fills}",
        )
        _emit(
            L,
            f"    RS  base Calmar {rs.base_calmar:.4f} / ratio {rs.calmar_ratio:.4f} / fills {rs.n_fills}",
        )
        _emit(
            L,
            f"    → {'CONFIRMED identical (RS carries no information beyond MOM)' if identical else '⚠ UNEXPECTED divergence — investigate'}",
        )

    # §5 deployment diagnostic
    _emit(L)
    _emit(L, "-" * 110)
    _emit(
        L,
        "  §5 deployment diagnostic (NON-GATING, adds 0 to K — candidate=MOM, base cost)",
    )
    _emit(L, "-" * 110)
    _emit(
        L,
        f"    D_base  (Neutral f=0.50): Calmar {diag.base_calmar:.3f} | maxDD {diag.base_max_dd:.1%} | CAGR {diag.base_cagr:.2%}",
    )
    _emit(
        L,
        f"    D_more  (Neutral f=0.75): Calmar {diag.more_calmar:.3f} | maxDD {diag.more_max_dd:.1%} | CAGR {diag.more_cagr:.2%}",
    )
    _emit(
        L, f"    Nifty 50 TRI maxDD (deploy bar denominator): {diag.bench_max_dd:.1%}"
    )
    if diag.read == "overlay-earns-keep":
        _emit(
            L,
            "    → READ: OVERLAY EARNS ITS KEEP (D_more Calmar ≤ D_base — de-deployment is doing its risk job). Leave frozen.",
        )
    elif diag.read == "deployment-is-a-lever":
        _emit(
            L,
            "    → READ: DEPLOYMENT IS A REAL LEVER (D_more Calmar > D_base AND maxDD ≤ benchmark) — authorizes a SEPARATE future amendment (own K). Candidate UNCHANGED this run.",
        )
    else:
        _emit(
            L,
            "    → READ: AMBIGUOUS (D_more Calmar > D_base but maxDD breaches the deploy bar) — not a clean lever. Leave frozen.",
        )

    # §6.1 survivors
    survivors = [r for r in rows if r.passes_s61]
    _emit(L)
    _emit(L, "=" * 110)
    _emit(
        L,
        f"  §6.1 survivors (pessimistic Calmar ratio ≥ 1.0): {len(survivors)}/{len(rows)}",
    )
    if survivors:
        for r in survivors:
            _emit(
                L,
                f"    → {r.name} ({r.role}) base Calmar {r.base_calmar:.3f}, ratio {r.calmar_ratio:.2f} — carries to V4.5 battery",
            )
        _emit(
            L,
            "  V4.5 (full §6 battery + plateau) runs next on the §6.1-clearing set (`04` §4 Stage 2).",
        )
    else:
        _emit(
            L,
            "    → NULL — no selector clears §6.1. Per `04` §6 pre-accepted null: the return-informed\n"
            "      selector does NOT rescue the thin daily-swing edge; the v4 swing family is FULLY CLOSED\n"
            "      as a research note; v4-FINAL_OOS is NOT touched; no selector added, no threshold loosened.",
        )
    _emit(
        L,
        f"  v4 ConfigLedger K (this run): {ledger.n_trials}  (carries from the v4 family ≥6; §5 diagnostic added 0)",
    )
    _emit(L, "  v4-FINAL_OOS untouched.")
    _emit(L, "=" * 110)
    return L


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


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

    print("v4 / 04 V4.4 — return-informed selector Stage-1 cost screen on DISCOVERY")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
    print("  Selectors: MOM (candidate) | RS (comparator) | ADV (V4.1 baseline)")
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

    print(
        "Loading Nifty 50 price index + market_internals (regime + RS benchmark)...",
        flush=True,
    )
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
    ref_cfg = _candidate_config(exit_type=3)
    signal_store = precompute_swing_signals(prices, ref_cfg)
    regime = RegimeScore(px, mi, ref_cfg)
    regime_more = RegimeScore(px, mi, ref_cfg, neutral_fraction=_DEPLOY_MORE_NEUTRAL)

    ledger = ConfigLedger()
    print(
        "\nScreening the §3/§4 selector grid (base + pessimistic, whole-share, ₹3.5L)...",
        flush=True,
    )
    rows = _screen_selectors(prices, regime, signal_store, tri_nifty50, px, ledger)

    # ADV-baseline parity (the ADV selector IS the closed V4.1 T3 engine).
    adv = next((r for r in rows if r.selector == "adv"), None)
    parity_ok = False
    parity_note = "ADV row missing — cannot check parity."
    if adv is not None:
        d_cal = abs(adv.base_calmar - _ADV_PARITY_BASE_CALMAR)
        d_ratio = abs(adv.calmar_ratio - _ADV_PARITY_PESS_RATIO)
        parity_ok = d_cal <= _PARITY_TOL and d_ratio <= _PARITY_TOL
        parity_note = (
            f"ADV base Calmar {adv.base_calmar:.3f} (V4.1 ~{_ADV_PARITY_BASE_CALMAR}); "
            f"pess ratio {adv.calmar_ratio:.2f} (V4.1 ~{_ADV_PARITY_PESS_RATIO}); "
            f"|Δcalmar|={d_cal:.3f} |Δratio|={d_ratio:.3f} (tol {_PARITY_TOL})"
        )

    print(
        "\nRunning the §5 deployment diagnostic (D_base vs D_more, MOM, base cost)...",
        flush=True,
    )
    diag = _deployment_diag(prices, regime, regime_more, signal_store, px, tri_nifty50)

    lines = _report(rows, diag, parity_ok, parity_note, ledger)

    out_path = "reports/v44_selector_screen.txt"
    try:
        with open(out_path, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"\n(report written to backend/{out_path})", flush=True)
    except OSError as e:  # pragma: no cover — non-fatal
        print(f"\n(could not write report: {e})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
