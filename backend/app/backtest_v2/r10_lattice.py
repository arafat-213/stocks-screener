"""
r10_lattice.py — R10.1: dense §6.3 plateau lattice around S3, on DISCOVERY only.

Pre-registered in `specs/v3/10_SKEW_REVALIDATION_PREREG.md` §4/§12. The SU2 §6.3
plateau verdict on S3 (stable U=350, B=1.25, 5-factor, M=130) was judged on a SPARSE
2-point U-lattice that `08` §6.3 itself flagged as unreliable ("(350,1.0) was never
enumerated"). A region-vs-spike test is meaningless on 2 points. `10` §2b fixes this
by enumerating the FULL ±1 lattice around S3 on BOTH axes (U and B) — 7 configs:

    U-axis (B=1.25):  U ∈ {250, 300, 350, 400, 450}
    B-axis (U=350):   B ∈ {1.0, 1.25, 1.5}        (center 350/1.25 = S3, shared)

§6.3 plateau predicate (NOT relaxed, `10` §4): S3's FOUR immediate ±1 neighbours —
U=300, U=400 (B=1.25) and B=1.0, B=1.5 (U=350) — must EACH stay ≥ 85% of S3's own
base Calmar. A region in BOTH axes, not a spike.

DISCIPLINE (read before trusting the output — `10` §1/§8):
  - DISCOVERY only. FINAL_OOS is NOT loaded, NOT touched, NOT consumed.
  - This is a PLATEAU CHECK on the pre-specified S3, NOT a search to pick a better
    U/B (picking the best lattice point after seeing the lattice is the v1 sin).
  - C0 (floor, M=130, anchor 0.523) and S3 (center, anchor 0.575) are reproduced as
    sanity anchors — a mismatch FAILS LOUD (Rule 12).
  - All 7 lattice configs logged to ConfigLedger — K is honest.
  - No skew/classic/deploy here (that is R10.2); this stage is base-cost lattice only.

Run:
    backend/venv/bin/python -m app.backtest_v2.r10_lattice
"""

from __future__ import annotations

import gc
import logging
import sys
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.backtest_v2 import engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.diag_turnover_decomp import _decompose_fills
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.stable_universe import build_stable_universe_mask
from app.backtest_v2.v3_config import TRACK_A_BASELINE, V3Config
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# Frozen S3 construction (`10` §3) — only U/B vary across the lattice.
_M = 130
_SMOOTHING = 0
_CADENCE = "monthly"

# §6.3 plateau threshold (`10` §4) — NOT relaxed.
_PLATEAU_FRAC = 0.85

# Anchor reproduction tolerance (sanity, not a gate).
_ANCHOR_TOL = 0.01


@dataclass
class LatConfig:
    name: str
    universe_mode: str  # "stable" | "floor"
    universe_size_U: int
    universe_buffer_B: float
    role: str
    anchor_calmar: float | None = None  # reproduce-or-fail-loud when set

    @property
    def label(self) -> str:
        if self.universe_mode == "floor":
            return "₹5cr floor (daily)"
        return f"stable U={self.universe_size_U} B={self.universe_buffer_B:g}"


# C0 anchor + the 7-config §4 lattice. Center (U=350, B=1.25) IS S3, enumerated once
# and tagged as the lattice center + the 0.575 anchor.
_C0 = LatConfig("C0", "floor", 0, 0.0, "anchor (MD1 M=130)", anchor_calmar=0.523)

_LATTICE: list[LatConfig] = [
    LatConfig("U250", "stable", 250, 1.25, "U-axis −2"),
    LatConfig("U300", "stable", 300, 1.25, "U-axis −1 (S3 neighbour)"),
    LatConfig(
        "S3", "stable", 350, 1.25, "CENTER (S3, anchor 0.575)", anchor_calmar=0.575
    ),
    LatConfig("U400", "stable", 400, 1.25, "U-axis +1 (S3 neighbour)"),
    LatConfig("U450", "stable", 450, 1.25, "U-axis +2"),
    LatConfig("B100", "stable", 350, 1.00, "B-axis −1 (S3 neighbour)"),
    LatConfig("B150", "stable", 350, 1.50, "B-axis +1 (S3 neighbour)"),
]

# The four ±1 neighbours of S3 that the §6.3 predicate gates on.
_NEIGHBOURS = ("U300", "U400", "B100", "B150")


@dataclass
class LatRow:
    name: str
    label: str
    role: str
    base_calmar: float
    base_max_dd: float
    turnover_pct: float
    churn_pct: float
    churn_frac: float
    universe_sizes: str
    anchor_calmar: float | None
    anchor_ok: bool | None


def _v3_config(cfg: LatConfig) -> V3Config:
    return V3Config(
        active_factors=list(TRACK_A_BASELINE.active_factors),
        rebalance_cadence=_CADENCE,
        sell_rank_buffer=_M,
        rank_smoothing_months=_SMOOTHING,
        target_positions=TRACK_A_BASELINE.target_positions,
        use_regime_overlay=True,
        catastrophic_stop_pct=25.0,
        liquidity_floor_cr=5.0,
        universe_mode=cfg.universe_mode,
        universe_size_U=cfg.universe_size_U if cfg.universe_mode == "stable" else 200,
        universe_buffer_B=cfg.universe_buffer_B
        if cfg.universe_mode == "stable"
        else 1.25,
        date_from=DISCOVERY[0],
        date_to=DISCOVERY[1],
    )


def _engine_cfg(v3cfg: V3Config) -> MomentumConfig:
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
        date_from=v3cfg.date_from,
        date_to=v3cfg.date_to,
    )


def _churn(result: engine.EngineResult, turnover: float) -> tuple[float, float]:
    """Realized membership churn (entry+exit Δweight) — mirrors su1._churn."""
    dec = _decompose_fills(result)
    total = dec["total"]
    if total <= 0:
        return 0.0, 0.0
    churn_frac = (dec["entry"] + dec["exit"]) / total
    return churn_frac * turnover, churn_frac


def _rss_mb() -> float:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except OSError:
        pass
    return float("nan")


def run_config(
    cfg: LatConfig,
    prices: pd.DataFrame,
    index_prices: pd.Series,
    composite: pd.DataFrame,
    gate_ind,
    ledger: ConfigLedger | None,
) -> LatRow:
    v3cfg = _v3_config(cfg)
    eng = _engine_cfg(v3cfg)

    mask = None
    universe_sizes = "—"
    if v3cfg.universe_mode == "stable":
        mask = build_stable_universe_mask(
            prices,
            v3cfg.universe_size_U,
            v3cfg.universe_buffer_B,
            v3cfg.universe_rank_lookback_td,
            v3cfg.universe_review_cadence,
        )
        sizes = [n for _, n in mask.size_history()]
        if sizes:
            universe_sizes = f"{min(sizes)}–{max(sizes)} (n={len(sizes)})"
    ss = V3SignalStore(gate_ind, composite, v3cfg, universe_mask=mask)

    if ledger is not None:
        ledger.add(
            {
                "config": cfg.name,
                "universe_mode": v3cfg.universe_mode,
                "U": v3cfg.universe_size_U if v3cfg.universe_mode == "stable" else None,
                "B": v3cfg.universe_buffer_B
                if v3cfg.universe_mode == "stable"
                else None,
                "M": _M,
                "factors": list(TRACK_A_BASELINE.active_factors),
                "cost_level": "base",
            },
            stage="R10_lattice_base",
        )

    res = engine.run(
        prices, eng, index_prices=index_prices, cost_level="base", signal_store=ss
    )
    m = metrics.compute_metrics(res)
    turnover = m.annualized_turnover
    churn_ann, churn_frac = _churn(res, turnover)

    anchor_ok: bool | None = None
    if cfg.anchor_calmar is not None:
        anchor_ok = abs(m.calmar - cfg.anchor_calmar) <= _ANCHOR_TOL

    log.info(
        "    %-5s %-22s calmar=%.3f%s  maxdd=%.1f%%  turn=%.0f%%  churn=%.0f%% (%.0f%%)  univ=%s",
        cfg.name,
        cfg.label,
        m.calmar,
        ""
        if cfg.anchor_calmar is None
        else f" (anchor {cfg.anchor_calmar:.3f} {'OK' if anchor_ok else 'MISMATCH'})",
        m.max_drawdown * 100,
        turnover * 100,
        churn_ann * 100,
        churn_frac * 100,
        universe_sizes,
    )
    log.info("    [mem] RSS=%.0f MB", _rss_mb())

    row = LatRow(
        name=cfg.name,
        label=cfg.label,
        role=cfg.role,
        base_calmar=m.calmar,
        base_max_dd=m.max_drawdown,
        turnover_pct=turnover * 100,
        churn_pct=churn_ann * 100,
        churn_frac=churn_frac,
        universe_sizes=universe_sizes,
        anchor_calmar=cfg.anchor_calmar,
        anchor_ok=anchor_ok,
    )
    del res, ss, mask
    gc.collect()
    return row


def _print_report(c0: LatRow, rows: list[LatRow]) -> bool:
    """Print the lattice table + plateau verdict. Returns the §6.3 plateau PASS bool."""
    sep = "=" * 92
    print(f"\n{sep}")
    print("  R10.1 — DENSE §6.3 PLATEAU LATTICE around S3 (DISCOVERY only, base cost)")
    print(
        f"  DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]} | S3 = stable U=350 B=1.25, 5-factor, M={_M}"
    )
    print(
        f"  plateau predicate: each ±1 neighbour ≥ {_PLATEAU_FRAC:.0%} of S3 base Calmar"
    )
    print(sep)

    print("\n  ANCHORS (reproduce-or-fail-loud):")
    for r in (c0, next(r for r in rows if r.name == "S3")):
        tag = "REPRODUCED" if r.anchor_ok else "MISMATCH — FAIL LOUD"
        print(
            f"    {r.name:<5} {r.label:<22} Calmar {r.base_calmar:.3f} "
            f"(anchor {r.anchor_calmar:.3f}) → {tag}"
        )

    print(
        f"\n  {'cfg':<5} {'universe':<22} {'Calmar':>7} {'maxDD':>7} "
        f"{'turn':>6} {'churn':>7} {'univ size':>14}  role"
    )
    print(f"  {'-' * 88}")
    for r in rows:
        star = "  *" if r.name == "S3" else "   "
        print(
            f"  {r.name:<5} {r.label:<22} {r.base_calmar:>7.3f} {r.base_max_dd:>6.1%} "
            f"{r.turnover_pct:>5.0f}% {r.churn_pct:>6.0f}% {r.universe_sizes:>14}{star}{r.role}"
        )

    s3 = next(r for r in rows if r.name == "S3")
    threshold = _PLATEAU_FRAC * s3.base_calmar
    print(
        f"\n  §6.3 PLATEAU CHECK — S3 base Calmar {s3.base_calmar:.3f}, "
        f"threshold = {_PLATEAU_FRAC:.0%} × {s3.base_calmar:.3f} = {threshold:.3f}"
    )
    all_pass = True
    by_name = {r.name: r for r in rows}
    for nm in _NEIGHBOURS:
        nr = by_name[nm]
        ok = nr.base_calmar >= threshold
        all_pass = all_pass and ok
        frac = nr.base_calmar / s3.base_calmar if s3.base_calmar else float("nan")
        print(
            f"    {nm:<5} {nr.label:<22} Calmar {nr.base_calmar:.3f} "
            f"({frac:.0%} of S3) → {'PASS' if ok else 'FAIL'}"
        )

    verdict = (
        "PASS — S3 sits on a region in BOTH axes"
        if all_pass
        else "FAIL — S3 is a spike, not a region"
    )
    print(
        f"\n  §6.3 dense-lattice plateau: {'PASS' if all_pass else 'FAIL'}  ({verdict})"
    )
    print(sep)
    print(
        "  DISCIPLINE: FINAL_OOS untouched. This is a plateau check on the pre-specified"
    )
    print(
        "  S3, NOT an operating-point search. Next = R10.2 (full battery + §5 acceptance)."
    )
    print(sep)
    return all_pass


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

    print("R10.1 — dense §6.3 plateau lattice around S3")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")

    print("Loading prices_adjusted (offline cache)...", flush=True)
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    # DISCOVERY-only + memory: drop every row after DISCOVERY end (the FINAL_OOS region
    # — not needed here and forbidden to touch). Warmup (pre-2018) is kept.
    prices = prices[prices["date"] <= pd.Timestamp(DISCOVERY[1])].copy()
    print(
        f"  rows={len(prices):,}  ISINs={prices['isin'].nunique():,}"
        f"  range={prices['date'].min().date()} → {prices['date'].max().date()}"
        f"  (sliced ≤ DISCOVERY end {DISCOVERY[1]})",
        flush=True,
    )

    from app.backtest_v2 import benchmark

    print("Loading Nifty 50 price index (regime overlay)...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    except Exception as exc:
        print(f"FAIL: regime index unavailable: {exc}", file=sys.stderr)
        return 2

    # Shared 5-factor gate cache + composite (identical across all configs: same
    # TRACK_A_BASELINE factors; M and universe-mode don't affect precompute/composite).
    ref_v3 = _v3_config(_LATTICE[0])
    print("Precomputing v2 gate cache + 5-factor composite (shared)...", flush=True)
    gate_store = precompute_signals(prices, _engine_cfg(ref_v3))
    gate_ind = gate_store._data
    composite = factors.composite_rank(prices, ref_v3)

    ledger = ConfigLedger()

    # C0 anchor (floor) — reproduction check, NOT a new ledger trial.
    print("\n[anchor] C0 — ₹5cr floor (reproduce MD1 M=130, 0.523)", flush=True)
    c0 = run_config(_C0, prices, index_prices, composite, gate_ind, ledger=None)

    rows: list[LatRow] = []
    for i, cfg in enumerate(_LATTICE, 1):
        print(f"\n[{i}/{len(_LATTICE)}] {cfg.name} — {cfg.label}", flush=True)
        rows.append(run_config(cfg, prices, index_prices, composite, gate_ind, ledger))

    plateau_pass = _print_report(c0, rows)

    # Fail loud on any anchor mismatch (Rule 12).
    anchors = [r for r in [c0, *rows] if r.anchor_calmar is not None]
    bad = [r for r in anchors if not r.anchor_ok]
    print(
        f"\n  ConfigLedger entries this run (K added): {ledger.n_trials}  | FINAL_OOS untouched."
    )
    if bad:
        print(
            "  ANCHOR MISMATCH — "
            + ", ".join(f"{r.name}={r.base_calmar:.3f}" for r in bad),
            file=sys.stderr,
        )
        return 3
    # A FAIL plateau is a valid (null) outcome, not a script error — exit 0 so long as
    # anchors reproduced. The verdict is in the report above.
    _ = plateau_pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
