"""ro1_discovery.py — v5/00 RO1: the locked overlay on DISCOVERY + full §6 diagnostics.

Wires the **real cached** Nifty 50 TRI / Nifty 50 price / Nifty 1D Rate Index / regime
market_internals into the RO0 simulator (``overlay.simulate``) over **DISCOVERY only**
(2018-02-06 → 2023-06-30) and applies the §5c binding bar. FINAL_OOS is never loaded into
the simulate window — every series is sliced ``≤ DISCOVERY[1]`` before anything runs.

One return-generating config (the frozen 5-factor 3-bucket overlay) ⇒ K = 1. Everything
else here (static-matched mix, buy-and-hold, Faber-200DMA, linear ramp, 3-factor ablation,
0%-cash floor) is a §6 diagnostic / anchor / deterministic transform ⇒ each adds 0 to K.

Run: ``backend/venv/bin/python -m app.regime_overlay.ro1_discovery``
Reads only the on-disk niftyindices caches + the market_internals store (no live network).
"""

from __future__ import annotations

import logging
import math
import sys
from datetime import date

import pandas as pd

from app.backtest_v2 import benchmark
from app.backtest_v2.costs import CostConfig
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store
from app.regime_overlay import overlay as ov
from app.regime_overlay.short_rate import load_defensive_index
from app.swing_v4.config import SwingConfig
from app.swing_v4.regime import RegimeScore

# The on-disk cache span (RO0): full 2017→2026 series. We load it then SLICE to
# DISCOVERY end before any simulation — FINAL_OOS (2023-07-01 →) never enters a window.
_FETCH_START = date(2017, 1, 1)
_FETCH_END = date(2026, 6, 12)
_DISC_START, _DISC_END = DISCOVERY  # (2018-02-06, 2023-06-30)


def _slice_le(s: pd.Series, end: date) -> pd.Series:
    """Keep only rows ≤ end (guarantees FINAL_OOS is never in the simulate window)."""
    return s[s.index <= pd.Timestamp(end)].sort_index()


def _load_inputs() -> tuple[pd.Series, pd.Series, pd.Series, pd.DataFrame]:
    """Load + DISCOVERY-slice the four real series (TRI, price, defensive, MI)."""
    tri = _slice_le(
        benchmark.load_tri(benchmark.TRI_NIFTY_50, _FETCH_START, _FETCH_END), _DISC_END
    )
    price = _slice_le(benchmark.load_price_index(_FETCH_START, _FETCH_END), _DISC_END)
    defensive = _slice_le(load_defensive_index(_FETCH_START, _FETCH_END), _DISC_END)
    mi = store.read_market_internals()
    mi["date"] = pd.to_datetime(mi["date"])
    mi = mi[mi["date"] <= pd.Timestamp(_DISC_END)].copy()
    for name, s in (("TRI", tri), ("price", price), ("defensive", defensive)):
        if s.empty or s.index.max() > pd.Timestamp(_DISC_END):
            raise RuntimeError(
                f"{name}: empty or leaks past DISCOVERY end (fail loud)."
            )
    return tri, price, defensive, mi


def _discovery_calendar(tri: pd.Series, mi: pd.DataFrame) -> list[pd.Timestamp]:
    """DISCOVERY trading days that have BOTH a TRI level and a regime score."""
    lo, hi = pd.Timestamp(_DISC_START), pd.Timestamp(_DISC_END)
    tri_days = tri.index[(tri.index >= lo) & (tri.index <= hi)]
    mi_days = pd.DatetimeIndex(mi["date"])
    return sorted(set(tri_days).intersection(mi_days))


# ---------------------------------------------------------------------------
# Per-drawdown decomposition (§6 — single-event guard)
# ---------------------------------------------------------------------------


def _bh_drawdown_episodes(
    nav: pd.Series, min_depth: float = 0.08
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, float]]:
    """Peak→trough→recovery episodes of the B&H NAV with depth ≥ min_depth.

    Returns (peak_date, trough_date, recovery_or_last_date, depth<0). An unrecovered
    final drawdown is closed at the last day. These are the crashes the timer is meant
    to dodge — the windows we attribute the overlay's edge across.
    """
    vals = nav.to_numpy(dtype=float)
    days = list(nav.index)
    eps: list[tuple] = []
    peak_v, peak_d = vals[0], days[0]
    trough_v, trough_d = vals[0], days[0]
    in_dd = False
    for v, d in zip(vals[1:], days[1:]):
        if v >= peak_v:  # new high == recovery of any open drawdown
            if in_dd:
                depth = trough_v / peak_v - 1.0
                if abs(depth) >= min_depth:
                    eps.append((peak_d, trough_d, d, depth))
                in_dd = False
            peak_v, peak_d, trough_v, trough_d = v, d, v, d
        else:
            in_dd = True
            if v < trough_v:
                trough_v, trough_d = v, d
    if in_dd:  # final unrecovered drawdown — close at the last day
        depth = trough_v / peak_v - 1.0
        if abs(depth) >= min_depth:
            eps.append((peak_d, trough_d, days[-1], depth))
    return eps


def _edge_over(
    window_a: pd.Timestamp,
    window_b: pd.Timestamp,
    overlay_nav: pd.Series,
    static_nav: pd.Series,
) -> float:
    """Overlay-minus-static log return across [window_a, window_b] (the episode edge)."""
    o = math.log(overlay_nav.loc[window_b] / overlay_nav.loc[window_a])
    s = math.log(static_nav.loc[window_b] / static_nav.loc[window_a])
    return o - s


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _fmt(m: dict[str, float]) -> str:
    return (
        f"Calmar {m['calmar']:.3f}  maxDD {m['max_dd'] * 100:5.1f}%  "
        f"CAGR {m['cagr'] * 100:5.2f}%  Sharpe {m['sharpe']:.3f}"
    )


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    lines: list[str] = []

    def out(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    out("v5 / 00 RO1 — regime overlay on DISCOVERY (2018-02-06 → 2023-06-30)")
    out(f"  FINAL_OOS ({DISCOVERY[1]} <) NEVER loaded into a window. K = 1.")
    out("")

    tri, price, defensive, mi = _load_inputs()
    cal = _discovery_calendar(tri, mi)
    out(f"DISCOVERY trading days: {len(cal)}  [{cal[0].date()} → {cal[-1].date()}]")

    cfg = SwingConfig()
    regime = RegimeScore(price, mi, cfg, neutral_fraction=0.5)  # frozen 5-factor
    base, pess = CostConfig.base(), CostConfig.pessimistic()

    # --- the candidate (K=1) ---
    f_overlay = ov.overlay_fraction(regime, cal)
    r_ov_base = ov.simulate(f_overlay, tri, defensive, base)
    r_ov_pess = ov.simulate(f_overlay, tri, defensive, pess)
    w_star = r_ov_base.realized_avg_fraction
    m_ov_base = ov.metrics_from_nav(r_ov_base.nav)
    m_ov_pess = ov.metrics_from_nav(r_ov_pess.nav)

    # --- static exposure-matched mix (BINDING comparator) ---
    f_static = ov.static_fraction(w_star, cal)
    r_st_base = ov.simulate(f_static, tri, defensive, base, rebalance="monthly")
    r_st_pess = ov.simulate(f_static, tri, defensive, pess, rebalance="monthly")
    m_st_base = ov.metrics_from_nav(r_st_base.nav)
    m_st_pess = ov.metrics_from_nav(r_st_pess.nav)

    # --- reported context comparators ---
    f_bh = pd.Series(1.0, index=pd.DatetimeIndex(cal), name="bh")
    r_bh_base = ov.simulate(f_bh, tri, defensive, base)
    r_bh_pess = ov.simulate(f_bh, tri, defensive, pess)
    m_bh_base = ov.metrics_from_nav(r_bh_base.nav)
    m_bh_pess = ov.metrics_from_nav(r_bh_pess.nav)

    f_faber = ov.faber_fraction(price, cal)
    r_fb_base = ov.simulate(f_faber, tri, defensive, base)
    r_fb_pess = ov.simulate(f_faber, tri, defensive, pess)
    m_fb_base = ov.metrics_from_nav(r_fb_base.nav)
    m_fb_pess = ov.metrics_from_nav(r_fb_pess.nav)

    out("")
    out(f"w* (overlay realized avg deployed fraction) = {w_star:.4f}")
    out("")
    out("METRIC TABLE (base | pessimistic)")
    out(
        f"  Overlay (CANDIDATE) base : {_fmt(m_ov_base)}  "
        f"flips {r_ov_base.n_rebalances}  switch ₹{r_ov_base.total_switch_cost:,.0f}"
    )
    out(
        f"  Overlay (CANDIDATE) pess : {_fmt(m_ov_pess)}  "
        f"flips {r_ov_pess.n_rebalances}  switch ₹{r_ov_pess.total_switch_cost:,.0f}"
    )
    out(
        f"  Static w*-mix  BIND base : {_fmt(m_st_base)}  "
        f"rebal {r_st_base.n_rebalances}  switch ₹{r_st_base.total_switch_cost:,.0f}"
    )
    out(
        f"  Static w*-mix  BIND pess : {_fmt(m_st_pess)}  "
        f"rebal {r_st_pess.n_rebalances}  switch ₹{r_st_pess.total_switch_cost:,.0f}"
    )
    out(f"  Buy&Hold TRI    ctx base : {_fmt(m_bh_base)}")
    out(f"  Buy&Hold TRI    ctx pess : {_fmt(m_bh_pess)}")
    out(
        f"  Faber-200DMA    ctx base : {_fmt(m_fb_base)}  flips {r_fb_base.n_rebalances}"
    )
    out(
        f"  Faber-200DMA    ctx pess : {_fmt(m_fb_pess)}  flips {r_fb_pess.n_rebalances}"
    )

    # --- §5c binding bar ---
    flips_per_yr = r_ov_base.n_rebalances / (len(cal) / 252.0)
    bar_base = m_ov_base["calmar"] > m_st_base["calmar"]
    bar_pess = m_ov_pess["calmar"] > m_st_pess["calmar"]
    bar_dd = m_ov_base["max_dd"] <= m_bh_base["max_dd"]
    binding_pass = bar_base and bar_pess and bar_dd
    out("")
    out("§5c BINDING BAR (overlay Calmar > static at base AND pess; maxDD ≤ B&H):")
    out(
        f"  base : overlay {m_ov_base['calmar']:.3f} {'>' if bar_base else '≤'} "
        f"static {m_st_base['calmar']:.3f}  → {'PASS' if bar_base else 'FAIL'}"
    )
    out(
        f"  pess : overlay {m_ov_pess['calmar']:.3f} {'>' if bar_pess else '≤'} "
        f"static {m_st_pess['calmar']:.3f}  → {'PASS' if bar_pess else 'FAIL'}"
    )
    out(
        f"  maxDD: overlay {m_ov_base['max_dd'] * 100:.1f}% "
        f"{'≤' if bar_dd else '>'} B&H {m_bh_base['max_dd'] * 100:.1f}%  "
        f"→ {'PASS' if bar_dd else 'FAIL'}"
    )
    out(f"  ⇒ BINDING BAR: {'PASS' if binding_pass else 'FAIL'}")

    # --- per-drawdown decomposition (§6 single-event guard, on base NAVs) ---
    out("")
    out("PER-DRAWDOWN DECOMPOSITION (overlay edge over static, base, by B&H crash):")
    eps = _bh_drawdown_episodes(r_bh_base.nav, min_depth=0.08)
    edges = []
    for peak_d, trough_d, recov_d, depth in eps:
        e = _edge_over(peak_d, recov_d, r_ov_base.nav, r_st_base.nav)
        edges.append(e)
        out(
            f"  {peak_d.date()}→{recov_d.date()}  B&H depth {depth * 100:6.1f}%  "
            f"overlay edge {e * 100:+6.2f}%"
        )
    pos = [e for e in edges if e > 0]
    total_pos = sum(pos) if pos else 0.0
    single_share = (max(pos) / total_pos) if total_pos > 0 else float("nan")
    total_adv = math.log(r_ov_base.nav.iloc[-1] / r_ov_base.nav.iloc[0]) - math.log(
        r_st_base.nav.iloc[-1] / r_st_base.nav.iloc[0]
    )
    out(
        f"  Σ positive episode edges {total_pos * 100:+.2f}%  | "
        f"total overlay−static log-edge {total_adv * 100:+.2f}%"
    )
    fragile = (not math.isnan(single_share)) and single_share > 0.90
    out(
        f"  largest single-episode share of positive edge: "
        f"{single_share * 100:.1f}%  ⇒ {'FRAGILE/single-event LABEL' if fragile else 'not single-event'}"
    )

    # --- diagnostics: linear ramp, 3-factor, 0%-cash floor ---
    out("")
    out("DIAGNOSTICS (non-gating, each adds 0 to K):")
    f_ramp = ov.linear_ramp_fraction(regime, cal)
    m_ramp = ov.metrics_from_nav(ov.simulate(f_ramp, tri, defensive, base).nav)
    out(f"  Linear ramp (score/5)  base : {_fmt(m_ramp)}")

    regime3 = RegimeScore(price, mi, cfg, n_factors=3, neutral_fraction=0.5)
    f_ov3 = ov.overlay_fraction(regime3, cal)
    m_ov3 = ov.metrics_from_nav(ov.simulate(f_ov3, tri, defensive, base).nav)
    out(f"  3-factor ablation      base : {_fmt(m_ov3)}")

    flat = pd.Series(1.0, index=defensive.index, name="zero_cash")  # 0% return leg
    m_ov_zero = ov.metrics_from_nav(ov.simulate(f_overlay, tri, flat, base).nav)
    out(
        f"  0%-cash floor overlay  base : {_fmt(m_ov_zero)}  "
        f"(vs real-rate {m_ov_base['calmar']:.3f})"
    )

    # --- ledger (K=1) + verdict ---
    ledger = ConfigLedger()
    ledger.add(
        "v5_overlay_frozen_3bucket",
        neutral_fraction=0.5,
        n_factors=5,
        map="3bucket_0_50_100",
        w_star=round(w_star, 4),
        calmar_base=round(m_ov_base["calmar"], 4),
    )
    out("")
    out(f"ConfigLedger K = {ledger.n_trials} (the single frozen overlay; §7).")
    out(
        f"Whipsaw: {r_ov_base.n_rebalances} flips over DISCOVERY "
        f"(~{flips_per_yr:.1f}/yr), switch ₹{r_ov_base.total_switch_cost:,.0f} base."
    )

    out("")
    if not binding_pass:
        verdict = (
            "RESEARCH-NOTE NULL — fails §5c binding bar ⇒ RO2 N/A, FINAL_OOS pristine."
        )
    elif fragile:
        verdict = "CLEARS BAR but FRAGILE/single-event LABEL — RO2 gated, label carried to §9."
    else:
        verdict = "CLEARS §5c BINDING BAR (no single-event flag) — RO2 (one-shot OOS) authorized."
    out(f"§5/§9 VERDICT: {verdict}")
    out("FINAL_OOS untouched (all series sliced ≤ DISCOVERY end).")

    try:
        with open("reports/ro1_discovery.txt", "w") as fh:
            fh.write("\n".join(lines) + "\n")
        out("(report written to backend/reports/ro1_discovery.txt)")
    except OSError as e:  # pragma: no cover
        out(f"(could not write report: {e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
