"""
v47_concentration_diagnostic.py — v4 / 05 PRE-V4.8 forensic on the §6.1 survivor.

PURPOSE (not a candidate, not a grid extension — a mechanism probe):
    V4.7 produced the first §6.1 survivor in the v4 family — atr 5.0 / daily /
    neutral 0.75 (pessimistic Calmar ratio 1.27). Before the V4.8 battery we ask the
    discriminating question Arafat raised: is that 1.27 an EDGE, or a LOTTERY? i.e.
    does the wide 5× trail earn its keep broadly, or does it merely keep a handful of
    lottery-ticket winners that the 3× trail clipped early? If the latter, the §6.3
    lone-peak pre-diagnosis and the §6.2 concentration gate stop being separate
    worries and become the SAME worry — and we want to know that going in.

DISCIPLINE (`00` §1/§6, `05` §5-species — non-gating diagnostic):
    - DISCOVERY only. v4-FINAL_OOS is NOT loaded or touched.
    - No threshold changed, no grid level added, no candidate swapped. Re-runs the
      already-scored V4.7 cells (atr5/daily survivor + atr3/daily comparator) at the
      candidate deployment (neutral 0.75), base cost.
    - Adds 0 to K (read-only — no ConfigLedger entries; R3/R4 species).
    - Output is a findings memo. Any structural decision it suggests is argued in the
      V4.8 battery under the LOCKED `05`, not acted on here.

WHY base cost (not pessimistic): the survival claim is pessimistic-cost, but the
    "edge vs lottery" question is about the gross edge STRUCTURE, which is clearest
    before the cost overlay — matching the `03`/v41_forensic convention. Costs scale
    the level; they do not create the concentration. Flagged in the report.

WHAT IT MEASURES (Arafat's pre-V4.8 spec):
    A. Per-config trade-return distribution (win rate, median/mean, p75/p90/p95
       winner, max) — the shape of the return book.
    B. P&L concentration: % of net P&L from the top 5 / 10 / 20 trades; Gini of trade
       profits (generalized on all net P&L, flagged; + a clean winners-only Gini);
       median winner; p95 winner. "How much does it lean on a few names?"
    C. ATR3 → ATR5 matched trade-by-trade (common (iid, entry_date) entries): the
       Δret distribution — what fraction barely moved vs became big winners. Tests the
       "90% unchanged, 10% massive" hypothesis directly.
    D. Verdict framing for V4.8 (does §6.2 become make-or-break?). Non-gating.

Run:
    backend/venv/bin/python -m app.swing_v4.v47_concentration_diagnostic
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.backtest_v2 import benchmark, metrics
from app.backtest_v2.validation import DISCOVERY
from app.data.bhavcopy import store
from app.swing_v4 import engine
from app.swing_v4.config import SwingConfig
from app.swing_v4.regime import RegimeScore
from app.swing_v4.signals import precompute_swing_signals
from app.swing_v4.v41_cost_screen import (
    _BENCH_FETCH_END,
    _BENCH_FETCH_START,
    _candidate_config,
    _run,
)
from app.swing_v4.v41_forensic import Trade, _reconstruct_trades

log = logging.getLogger(__name__)

# The §6.1 survivor and its direct comparator (only atr_mult differs), both at the
# candidate deployment used to screen them (neutral 0.75), daily cadence.
_SURVIVOR_ATR = 5.0
_COMPARATOR_ATR = 3.0
_CADENCE = "daily"
_NEUTRAL = 0.75


def _cfg(atr_mult: float) -> SwingConfig:
    return _candidate_config(
        exit_type=3,
        atr_mult=atr_mult,
        decision_cadence=_CADENCE,
        selector="mom",
    )


def _closed(res: engine.SwingEngineResult) -> list[Trade]:
    trades = _reconstruct_trades(res.fills_log, res.exit_log)
    return [t for t in trades if t.exit_reason != "still_open"]


def _gini(x: np.ndarray) -> float:
    """Generalized Gini via mean-absolute-difference: G = Σᵢ Σⱼ|xᵢ-xⱼ| / (2 n² x̄).

    With negative values (losing trades) and a small mean this can exceed 1 — that is
    a meaningful signal (extreme dependence on a few names), not a bug. Flagged in use.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n == 0:
        return float("nan")
    mean = x.mean()
    if mean == 0:
        return float("nan")
    mad = np.abs(x[:, None] - x[None, :]).sum() / (n * n)
    return float(mad / (2 * mean))


def _topk_share(pnl: np.ndarray, k: int) -> float:
    """Fraction of total net P&L contributed by the k largest-P&L trades."""
    total = pnl.sum()
    if total == 0 or len(pnl) == 0:
        return float("nan")
    topk = np.sort(pnl)[::-1][:k].sum()
    return float(topk / total)


def _emit(L: list[str], s: str = "") -> None:
    print(s, flush=True)
    L.append(s)


# ---------------------------------------------------------------------------
# A + B: per-config distribution + concentration
# ---------------------------------------------------------------------------


@dataclass
class ConfigForensic:
    atr_mult: float
    calmar: float
    sharpe: float
    max_dd: float
    cagr: float
    turnover: float
    n_closed: int
    win_rate: float
    rets: np.ndarray  # net ret_pct per closed trade
    pnl: np.ndarray  # net_pnl (₹) per closed trade
    total_net: float


def _run_forensic(atr: float, *, prices, regime, signal_store) -> ConfigForensic:
    res = _run(
        _cfg(atr),
        prices=prices,
        regime=regime,
        signal_store=signal_store,
        cost_level="base",
        whole_shares=True,
    )
    m = metrics.compute_metrics(res)
    closed = _closed(res)
    rets = np.array([t.ret_pct for t in closed], dtype=float)
    pnl = np.array([t.net_pnl for t in closed], dtype=float)
    win_rate = float(np.mean(rets > 0)) if len(rets) else float("nan")
    return ConfigForensic(
        atr_mult=atr,
        calmar=m.calmar,
        sharpe=m.sharpe,
        max_dd=m.max_drawdown,
        cagr=m.cagr,
        turnover=m.annualized_turnover,
        n_closed=len(closed),
        win_rate=win_rate,
        rets=rets,
        pnl=pnl,
        total_net=float(pnl.sum()),
    )


def _report_distribution(L: list[str], f: ConfigForensic) -> None:
    r = f.rets
    wins = r[r > 0]
    p = lambda a, q: float(np.percentile(a, q)) if len(a) else float("nan")  # noqa: E731
    _emit(L)
    _emit(
        L,
        f"  atr {f.atr_mult:.1f} / daily / neutral {_NEUTRAL}  —  Calmar {f.calmar:.3f} "
        f"| Sharpe {f.sharpe:.2f} | maxDD {f.max_dd:.1%} | CAGR {f.cagr:.2%} | turn {f.turnover:.0%}",
    )
    _emit(
        L,
        f"    {f.n_closed} closed round-trips | win rate {f.win_rate:.1%} | "
        f"total net P&L ₹{f.total_net:,.0f}",
    )
    _emit(
        L,
        f"    net ret/trade:  median {p(r, 50):+.2%} | mean {float(np.mean(r)):+.2%} | "
        f"p25 {p(r, 25):+.2%} | p75 {p(r, 75):+.2%}",
    )
    _emit(
        L,
        f"    winners only ({len(wins)}):  median {p(wins, 50):+.2%} | "
        f"p75 {p(wins, 75):+.2%} | p90 {p(wins, 90):+.2%} | "
        f"p95 {p(wins, 95):+.2%} | max {p(wins, 100):+.2%}",
    )


def _report_concentration(
    L: list[str], surv: ConfigForensic, comp: ConfigForensic
) -> None:
    _emit(L)
    _emit(L, "-" * 100)
    _emit(
        L,
        "  [B] P&L concentration — how much does each config lean on its biggest few trades?",
    )
    _emit(L, "-" * 100)
    _emit(
        L,
        f"  {'metric':<40} | {'atr 5.0 (survivor)':>22} | {'atr 3.0 (comparator)':>22}",
    )
    _emit(L, "  " + "─" * 96)

    def row(label: str, sv: str, cv: str) -> None:
        _emit(L, f"  {label:<40} | {sv:>22} | {cv:>22}")

    for k in (5, 10, 20):
        row(
            f"% of net P&L from top {k} trades",
            f"{_topk_share(surv.pnl, k):.1%}",
            f"{_topk_share(comp.pnl, k):.1%}",
        )
    sv_wins = surv.pnl[surv.pnl > 0]
    cv_wins = comp.pnl[comp.pnl > 0]
    row(
        "Gini of net P&L (all trades, generalized)",
        f"{_gini(surv.pnl):.3f}",
        f"{_gini(comp.pnl):.3f}",
    )
    row(
        "Gini of net P&L (winners only, ∈[0,1])",
        f"{_gini(sv_wins):.3f}",
        f"{_gini(cv_wins):.3f}",
    )
    p = lambda a, q: float(np.percentile(a, q)) if len(a) else float("nan")  # noqa: E731
    sv_w = surv.rets[surv.rets > 0]
    cv_w = comp.rets[comp.rets > 0]
    row("median winner (net ret)", f"{p(sv_w, 50):+.2%}", f"{p(cv_w, 50):+.2%}")
    row("p95 winner (net ret)", f"{p(sv_w, 95):+.2%}", f"{p(cv_w, 95):+.2%}")
    row(
        "₹ in single biggest winner",
        f"₹{surv.pnl.max():,.0f}",
        f"₹{comp.pnl.max():,.0f}",
    )
    _emit(L)
    _emit(
        L,
        "  Read: top-k % near or above 100% means losers cancel most of the book and a\n"
        "  handful of names carry it — the lottery signature. A high Gini reinforces it.",
    )


# ---------------------------------------------------------------------------
# C: matched trade-by-trade ATR3 -> ATR5
# ---------------------------------------------------------------------------


def _matched_pairs(
    prices, regime, signal_store
) -> tuple[list[tuple[Trade, Trade]], int, int]:
    """Pair atr3 and atr5 closed trades on identical (iid, entry_date).

    Entry logic is byte-identical across the two configs (only the exit width differs),
    so trades coincide until the first hold-length divergence frees a slot at a
    different time. Exact (iid, entry_date) matching cleanly covers that overlapping
    subset; we report the matched fraction rather than forcing a full alignment.
    """
    res3 = _run(
        _cfg(_COMPARATOR_ATR),
        prices=prices,
        regime=regime,
        signal_store=signal_store,
        cost_level="base",
        whole_shares=True,
    )
    res5 = _run(
        _cfg(_SURVIVOR_ATR),
        prices=prices,
        regime=regime,
        signal_store=signal_store,
        cost_level="base",
        whole_shares=True,
    )
    c3 = _closed(res3)
    c5 = _closed(res5)
    by_key3 = {(t.iid, t.entry_date): t for t in c3}
    by_key5 = {(t.iid, t.entry_date): t for t in c5}
    keys = set(by_key3) & set(by_key5)
    pairs = [(by_key3[k], by_key5[k]) for k in keys]
    return pairs, len(c3), len(c5)


def _report_matched(L: list[str], pairs, n3: int, n5: int) -> None:
    _emit(L)
    _emit(L, "-" * 100)
    _emit(
        L,
        "  [C] ATR3 → ATR5 matched trade-by-trade (same (iid, entry_date)) — what did the wider trail change?",
    )
    _emit(L, "-" * 100)
    _emit(
        L,
        f"  matched {len(pairs)} common entries  "
        f"(of {n3} atr3 closed / {n5} atr5 closed — coverage {len(pairs) / max(n3, 1):.0%} of atr3)",
    )
    if not pairs:
        _emit(
            L, "  (no common entries — configs diverged completely; nothing to compare)"
        )
        return
    d = np.array([p5.ret_pct - p3.ret_pct for p3, p5 in pairs], dtype=float)
    unchanged = float(np.mean(np.abs(d) <= 0.02))  # within ±2 pts ≈ same outcome
    improved = float(np.mean(d > 0.02))
    worsened = float(np.mean(d < -0.02))
    big = float(
        np.mean(d >= 0.30)
    )  # atr5 added ≥30 pts vs atr3 = "became a big winner"
    _emit(
        L,
        f"    Δret (atr5 − atr3) on matched trades:  median {np.median(d):+.2%} | "
        f"mean {d.mean():+.2%} | max {d.max():+.2%} | min {d.min():+.2%}",
    )
    _emit(
        L,
        f"    ≈unchanged (|Δ|≤2pts) {unchanged:.0%} | improved (>2pts) {improved:.0%} | "
        f"worsened (<−2pts) {worsened:.0%} | BIG-WINNER (Δ≥30pts) {big:.0%}",
    )
    # the names that became big winners — where the edge (if any) lives
    big_pairs = sorted(
        [
            (p3, p5, p5.ret_pct - p3.ret_pct)
            for p3, p5 in pairs
            if (p5.ret_pct - p3.ret_pct) >= 0.30
        ],
        key=lambda t: t[2],
        reverse=True,
    )
    _emit(L)
    _emit(
        L,
        f"    trades the wide trail turned into big winners (Δ≥30pts) — {len(big_pairs)} of {len(pairs)}:",
    )
    if big_pairs:
        _emit(
            L,
            f"      {'symbol':<14} {'entry':>10} | {'atr3 ret':>9} {'atr3 hold':>9} | "
            f"{'atr5 ret':>9} {'atr5 hold':>9} | {'Δret':>8}",
        )
        for p3, p5, dr in big_pairs[:20]:
            _emit(
                L,
                f"      {p3.symbol[:14]:<14} {str(p3.entry_date):>10} | "
                f"{p3.ret_pct:>+8.1%} {p3.hold_days:>8.0f}d | "
                f"{p5.ret_pct:>+8.1%} {p5.hold_days:>8.0f}d | {dr:>+7.1%}",
            )
        if len(big_pairs) > 20:
            _emit(L, f"      ... (+{len(big_pairs) - 20} more)")
    # how concentrated is the *gain* from going 3->5 across the matched book?
    gain = d.sum()
    if gain != 0:
        top_gain = np.sort(d)[::-1]
        share5 = top_gain[:5].sum() / gain
        _emit(L)
        _emit(
            L,
            f"    of the total Δret the wide trail added across matched trades, the top 5 "
            f"improvements account for {share5:.0%}.",
        )


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

    print(
        "v4 / 05 PRE-V4.8 concentration diagnostic — is the atr5/daily survivor edge or lottery?"
    )
    print(
        f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}  | base cost | adds 0 to K | FINAL_OOS untouched"
    )
    print()

    print("Loading prices_adjusted...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    print(f"  rows={len(prices):,} ISINs={prices['isin'].nunique():,}", flush=True)

    print(
        "Loading regime inputs (Nifty 50 price index + market_internals)...", flush=True
    )
    px = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    mi = store.read_market_internals()
    if mi.empty:
        print("FAIL: market_internals empty.", file=sys.stderr)
        return 2

    print("Precomputing swing signals + regime (neutral 0.75, shared)...", flush=True)
    ref_cfg = _cfg(_SURVIVOR_ATR)
    signal_store = precompute_swing_signals(prices, ref_cfg)
    regime = RegimeScore(px, mi, ref_cfg, neutral_fraction=_NEUTRAL)

    print(
        "\nRunning survivor (atr5/daily) + comparator (atr3/daily), base cost...",
        flush=True,
    )
    surv = _run_forensic(
        _SURVIVOR_ATR, prices=prices, regime=regime, signal_store=signal_store
    )
    comp = _run_forensic(
        _COMPARATOR_ATR, prices=prices, regime=regime, signal_store=signal_store
    )

    print("Matching trades for the ATR3 → ATR5 trade-by-trade...", flush=True)
    pairs, n3, n5 = _matched_pairs(prices, regime, signal_store)

    L: list[str] = []
    _emit(L)
    _emit(L, "=" * 100)
    _emit(
        L,
        "  V4.7 → PRE-V4.8 MECHANISM DIAGNOSTIC — edge vs lottery on the §6.1 survivor",
    )
    _emit(
        L,
        f"  DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]} | base cost | non-gating (0 to K) | FINAL_OOS untouched",
    )
    _emit(L, "=" * 100)
    _emit(L)
    _emit(L, "  [A] trade-return distribution (per config, net of base cost)")
    _emit(L, "-" * 100)
    _report_distribution(L, surv)
    _report_distribution(L, comp)
    _report_concentration(L, surv, comp)
    _report_matched(L, pairs, n3, n5)
    _emit(L)
    _emit(L, "=" * 100)
    _emit(
        L,
        "  DIAGNOSTIC COMPLETE — findings only. No candidate, no grid change, K unchanged.",
    )
    _emit(
        L,
        "  Interpretation feeds the V4.8 §6 battery argument (esp. §6.2); it does not pre-empt it.",
    )
    _emit(L, "=" * 100)

    out_path = "reports/v47_concentration_diagnostic.txt"
    try:
        with open(out_path, "w") as fh:
            fh.write("\n".join(L) + "\n")
        print(f"\n(report written to backend/{out_path})", flush=True)
    except OSError as e:  # pragma: no cover — non-fatal
        print(f"\n(could not write report: {e})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
