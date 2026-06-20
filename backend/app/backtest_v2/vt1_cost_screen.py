"""
vt1_cost_screen.py — v3 / 09 VT1: Stage 1 cost screen on the 9-config U×λ grid.

Pre-registration: specs/v3/09_MOMENTUM_VALUE_TILT_PREREG.md §5 (Stage 1) / §13 VT1.

Grid (9 coarse points, fully enumerated — 3 universe × 3 value-tilt; momentum base
held constant at the §3 retention-first 2-factor [mom_12_1, low_vol], N=20, M=130,
sm=0, monthly, regime ON, cat-stop 25%, ₹5cr floor as per-day safety; stable
universe B=1.25 — the `08` churn antidote):

           λ=0 (control)      λ=0.3              λ=0.6
    U=300  C-300              T-300-lo           T-300-hi
    U=350  C-350             *T-350-mid (interior)*  T-350-hi
    U=400  C-400              T-400-lo           T-400-hi

For each config:
  - Base run      → base Calmar, base maxDD, realized turnover, value-tilt activity
                    (held-set divergence vs the same-U λ=0 control).
  - Pessimistic   → §6.1 ratio = C_strat / C_nifty50 (≥ 1.0 clears §6.1).
  - Log both runs to ConfigLedger (K carries — a fresh objective does NOT reset K).

PLUMBING ANCHOR (09 §5/§12.3): a SEPARATE 5-factor U=350 λ=0 base run must reproduce
`08` S3 (base Calmar 0.575) — this verifies the stable-universe mask + engine plumbing
is unchanged from `08`. It is deliberately the 5-factor `08` config, NOT a grid cell:
the grid base is the §12.2-signed 2-factor base, which by construction cannot reproduce
a 5-factor number. (Flagged: 09 §5/§12.3 conflate this plumbing check with the grid's
C-350 control cell; they are different configs. Reconciled here by running both.)

Orthogonality is RECONFIRMED on this window (|ρ| < 0.3, 09 §5 Stage 1) — fail loud if
the value block has drifted since VT0.

DISCOVERY only — FINAL_OOS stays pristine. No §6.2/§6.3/§6.4 here (that is VT2).

Run:
    backend/venv/bin/python -m app.backtest_v2.vt1_cost_screen
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date
from statistics import mean

import numpy as np
import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.engine import _rebalance_dates
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import (
    V3SignalStore,
    _apply_value_tilt,
    build_value_rank,
)
from app.backtest_v2.stable_universe import build_stable_universe_mask
from app.backtest_v2.tbe4_value_block import _build_fund_frames
from app.backtest_v2.v3_config import TRACK_A_BASELINE, V3Config
from app.backtest_v2.validation import DISCOVERY, ConfigLedger
from app.data.bhavcopy import store
from app.db.session import SessionLocal

log = logging.getLogger(__name__)

_BENCH_FETCH_START = date(2017, 1, 1)
_BENCH_FETCH_END = date(2026, 6, 12)

# Held-constant momentum construction (09 §3) — retention-first 2-factor base.
_BASE_FACTORS = ["mom_12_1", "low_vol"]
_M = 130
_SMOOTHING = 0
_CADENCE = "monthly"
_BUFFER_B = 1.25  # the `08` churn antidote, fixed (not a grid lever)

# §5 grid levers.
_U_GRID = [300, 350, 400]
_LAMBDA_GRID = [0.0, 0.3, 0.6]

_ANCHOR_U = 350
_ANCHOR_CALMAR = 0.575  # `08` S3 base Calmar (5-factor) — plumbing-regression target
_ANCHOR_TOL = 0.01
_ORTHO_THRESHOLD = 0.30


@dataclass
class VT1Config:
    """One §5 grid point — universe size U and value-tilt strength λ vary."""

    name: str
    universe_size_U: int
    value_tilt_lambda: float

    @property
    def label(self) -> str:
        return f"U={self.universe_size_U} λ={self.value_tilt_lambda:g}"


def _build_grid() -> list[VT1Config]:
    grid: list[VT1Config] = []
    for u in _U_GRID:
        for lam in _LAMBDA_GRID:
            if lam == 0.0:
                name = f"C-{u}"
            else:
                tag = "lo" if lam == 0.3 else "hi"
                tag = "mid" if (u == 350 and lam == 0.3) else tag
                name = f"T-{u}-{tag}"
            grid.append(VT1Config(name, u, lam))
    return grid


_GRID = _build_grid()


@dataclass
class ScreenRow:
    name: str
    label: str
    base_calmar: float
    base_max_dd: float
    turnover_pct: float
    tilt_activity_pct: float
    universe_sizes: str
    c_strat_pessimistic: float
    c_nifty50: float
    calmar_ratio: float
    passes_s61: bool


# ---------------------------------------------------------------------------
# Config plumbing
# ---------------------------------------------------------------------------


def _v3_config(u: int, lam: float, factors_list: list[str]) -> V3Config:
    return V3Config(
        active_factors=list(factors_list),
        rebalance_cadence=_CADENCE,
        sell_rank_buffer=_M,
        rank_smoothing_months=_SMOOTHING,
        target_positions=TRACK_A_BASELINE.target_positions,
        use_regime_overlay=True,
        catastrophic_stop_pct=25.0,
        liquidity_floor_cr=5.0,
        universe_mode="stable",
        universe_size_U=u,
        universe_buffer_B=_BUFFER_B,
        value_tilt_lambda=lam,
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


def _equity_series(result: engine.EngineResult) -> pd.Series:
    return pd.Series(
        [s.equity for s in result.snapshots],
        index=pd.DatetimeIndex([pd.Timestamp(s.date) for s in result.snapshots]),
    )


def _holdings_timeline(result: engine.EngineResult) -> dict[date, frozenset[str]]:
    """Reconstruct the held-ISIN set at each rebalance date from the fills log.

    Replays buy/sell fills (trims do not change membership) in date order and
    snapshots the held set at each used rebalance date — the REALIZED membership,
    so the tilt-activity metric reflects what the strategy actually held, not the
    raw signal ordering.
    """
    fills = sorted(result.fills_log, key=lambda f: f.date)
    rebals = sorted(result.rebalance_dates_used)
    held: set[str] = set()
    timeline: dict[date, frozenset[str]] = {}
    fi = 0
    for d in rebals:
        while fi < len(fills) and fills[fi].date <= d:
            f = fills[fi]
            if f.side == "buy":
                held.add(f.isin)
            elif f.side == "sell":
                held.discard(f.isin)
            fi += 1
        timeline[d] = frozenset(held)
    return timeline


def _tilt_activity(
    tilted: dict[date, frozenset[str]],
    control: dict[date, frozenset[str]],
) -> float:
    """Mean per-rebalance held-set divergence (Jaccard distance) vs the λ=0 control.

    0% ⇒ the tilt never changed the held set; higher ⇒ the value overlay re-ordered
    more names into/out of the book. Measured on dates present in both runs.
    """
    common = sorted(set(tilted) & set(control))
    dists: list[float] = []
    for d in common:
        a, b = tilted[d], control[d]
        union = a | b
        if union:
            dists.append(len(a ^ b) / len(union))
    return mean(dists) * 100 if dists else 0.0


# ---------------------------------------------------------------------------
# Screen one config
# ---------------------------------------------------------------------------


def _screen_config(
    cfg: VT1Config,
    prices: pd.DataFrame,
    index_prices: pd.Series,
    tri_nifty50: pd.Series,
    ind: dict[str, pd.DataFrame],
    base_composite: pd.DataFrame,
    value_rank: pd.DataFrame,
    masks: dict[int, object],
    ledger: ConfigLedger,
) -> tuple[ScreenRow, dict[date, frozenset[str]]]:
    v3cfg = _v3_config(cfg.universe_size_U, cfg.value_tilt_lambda, _BASE_FACTORS)
    eng = _engine_cfg(v3cfg)

    mask = masks[cfg.universe_size_U]
    sizes = [n for _, n in mask.size_history()]
    universe_sizes = f"{min(sizes)}–{max(sizes)} (n={len(sizes)})" if sizes else "—"

    # Tilted composite (λ=0 ⇒ returns base_composite UNCHANGED — byte-identical).
    composite = _apply_value_tilt(base_composite, value_rank, cfg.value_tilt_lambda)
    ss = V3SignalStore(ind, composite, v3cfg, universe_mask=mask)

    ledger_payload = {
        "config": cfg.name,
        "universe_mode": "stable",
        "U": cfg.universe_size_U,
        "B": _BUFFER_B,
        "lambda": cfg.value_tilt_lambda,
        "M": _M,
        "smoothing": _SMOOTHING,
        "cadence": _CADENCE,
        "base_factors": _BASE_FACTORS,
    }

    # Base run → Calmar, maxDD, turnover, held-set timeline (for tilt activity).
    ledger.add({**ledger_payload, "cost_level": "base"}, stage="VT1_base")
    res_base = engine.run(
        prices, eng, index_prices=index_prices, cost_level="base", signal_store=ss
    )
    m_base = metrics.compute_metrics(res_base)
    turnover_pct = m_base.annualized_turnover * 100
    timeline = _holdings_timeline(res_base)

    # Pessimistic run → §6.1 ratio vs Nifty50 TRI.
    ledger.add({**ledger_payload, "cost_level": "pessimistic"}, stage="VT1_pessimistic")
    res_pess = engine.run(
        prices,
        eng,
        index_prices=index_prices,
        cost_level="pessimistic",
        signal_store=ss,
    )
    trading_cal = [pd.Timestamp(s.date) for s in res_pess.snapshots]
    bench_aligned = benchmark.align_benchmark(
        tri_nifty50, eng.date_from, trading_cal, eng.starting_capital
    )
    bm = metrics.compute_benchmark_metrics(_equity_series(res_pess), bench_aligned)

    row = ScreenRow(
        name=cfg.name,
        label=cfg.label,
        base_calmar=m_base.calmar,
        base_max_dd=m_base.max_drawdown,
        turnover_pct=turnover_pct,
        tilt_activity_pct=float("nan"),  # filled after the λ=0 control is known
        universe_sizes=universe_sizes,
        c_strat_pessimistic=bm.strategy_calmar,
        c_nifty50=bm.benchmark_calmar,
        calmar_ratio=bm.calmar_ratio,
        passes_s61=bm.calmar_ratio >= 1.0,
    )
    return row, timeline


# ---------------------------------------------------------------------------
# Plumbing anchor + orthogonality reconfirm
# ---------------------------------------------------------------------------


def _plumbing_anchor(
    prices: pd.DataFrame,
    index_prices: pd.Series,
    ind: dict[str, pd.DataFrame],
    masks: dict[int, object],
) -> float:
    """5-factor U=350 λ=0 base Calmar — must reproduce `08` S3 (0.575) byte-for-byte."""
    v3cfg = _v3_config(_ANCHOR_U, 0.0, list(TRACK_A_BASELINE.active_factors))
    composite5 = factors.composite_rank(prices, v3cfg)
    ss = V3SignalStore(ind, composite5, v3cfg, universe_mask=masks[_ANCHOR_U])
    res = engine.run(
        prices,
        _engine_cfg(v3cfg),
        index_prices=index_prices,
        cost_level="base",
        signal_store=ss,
    )
    return metrics.compute_metrics(res).calmar


def _reconfirm_orthogonality(
    base_composite: pd.DataFrame, value_rank: pd.DataFrame
) -> tuple[float, int]:
    common = base_composite.columns.intersection(value_rank.columns)
    mom = base_composite.reindex(index=value_rank.index, columns=common)
    val = value_rank.reindex(columns=common)
    mf = mom.to_numpy().ravel()
    vf = val.to_numpy().ravel()
    both = ~(np.isnan(mf) | np.isnan(vf))
    n = int(both.sum())
    rho = float(np.corrcoef(mf[both], vf[both])[0, 1]) if n >= 2 else float("nan")
    return rho, n


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(
    rows: list[ScreenRow],
    anchor_calmar: float,
    rho: float,
    n_pairs: int,
) -> None:
    print()
    print("=" * 110)
    print(
        "  VT1 Stage 1 — 9-config §6.1 cost screen (U×λ)  (DISCOVERY 2018-02-06 → 2023-06-30)"
    )
    print(
        f"  Momentum base held constant: {_BASE_FACTORS}, N=20, M={_M}, sm={_SMOOTHING}, "
        f"{_CADENCE}, regime ON, stable B={_BUFFER_B:g}, ₹5cr floor"
    )
    print("=" * 110)
    print(
        f"  {'Cfg':>9} | {'Universe/λ':>12} | {'Calmar':>7} | {'MaxDD':>7} | "
        f"{'Turn%':>6} | {'Tilt%':>6} | {'C_strat(P)':>10} | {'C_n50':>6} | {'Ratio':>6} | §6.1"
    )
    print("  " + "-" * 106)
    for r in rows:
        mark = "PASS" if r.passes_s61 else "FAIL"
        tilt = (
            "  —  " if np.isnan(r.tilt_activity_pct) else f"{r.tilt_activity_pct:>5.1f}"
        )
        print(
            f"  {r.name:>9} | {r.label:>12} | {r.base_calmar:>7.3f} | "
            f"{r.base_max_dd:>7.1%} | {r.turnover_pct:>6.0f} | {tilt:>6} | "
            f"{r.c_strat_pessimistic:>10.3f} | {r.c_nifty50:>6.3f} | "
            f"{r.calmar_ratio:>6.2f} | {mark}"
        )

    print("\n  Stable-universe realized membership sizes (per semi-annual review):")
    seen = set()
    for r in rows:
        u = r.label.split()[0]
        if u not in seen and r.universe_sizes != "—":
            print(f"    {u}: {r.universe_sizes}")
            seen.add(u)

    print()
    print("=" * 110)
    anchor_ok = abs(anchor_calmar - _ANCHOR_CALMAR) <= _ANCHOR_TOL
    print(
        f"  Plumbing anchor (5-factor U=350 λ=0 base Calmar, target {_ANCHOR_CALMAR}): "
        f"{anchor_calmar:.3f} → {'REPRODUCED' if anchor_ok else 'MISMATCH — FAIL LOUD'}"
    )
    print(
        f"  Orthogonality reconfirm (window |ρ| < {_ORTHO_THRESHOLD}): "
        f"ρ={rho:+.4f} |ρ|={abs(rho):.4f} over {n_pairs:,} cells → "
        f"{'OK' if abs(rho) < _ORTHO_THRESHOLD else 'DRIFTED — FAIL LOUD'}"
    )

    survivors = [r for r in rows if r.passes_s61]
    print(f"  §6.1 survivors (ratio ≥ 1.0): {len(survivors)}/{len(rows)} configs")
    if survivors:
        for r in survivors:
            print(
                f"    → {r.name} ({r.label}) base Calmar {r.base_calmar:.3f}, "
                f"ratio {r.calmar_ratio:.2f}"
            )
    else:
        print(
            "    → NULL — no config clears §6.1. Carry diagnostic to VT2 close (09 §6)."
        )
    print("=" * 110)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in (
        "app.backtest_v2",
        "app.core.strategy",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    print("v3 / 09 VT1 — Stage 1: 9-config §6.1 cost screen (U×λ) on DISCOVERY")
    print(f"  Grid: U∈{_U_GRID} × λ∈{[f'{x:g}' for x in _LAMBDA_GRID]}  (9 points)")
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}")
    print()

    print("Loading prices_adjusted (offline cache)...", flush=True)
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

    print("Loading Nifty 50 price index (regime, offline cache)...", flush=True)
    try:
        index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)
    except Exception as exc:
        print(f"FAIL: regime index unavailable: {exc}", file=sys.stderr)
        return 2

    print("Loading Nifty 50 TRI (§6.1 benchmark, offline cache)...", flush=True)
    try:
        tri_nifty50 = benchmark.load_tri(
            benchmark.TRI_NIFTY_50, _BENCH_FETCH_START, _BENCH_FETCH_END
        )
    except Exception as exc:
        print(f"FAIL: Nifty50 TRI unavailable: {exc}", file=sys.stderr)
        return 2

    # Shared momentum base (identical across the grid) + gate indicator cache.
    ref_v3 = _v3_config(_U_GRID[0], 0.0, _BASE_FACTORS)
    print(
        "Precomputing gate indicator cache + 2-factor composite (shared)...", flush=True
    )
    gate_store = precompute_signals(prices, _engine_cfg(ref_v3))
    ind = gate_store._data
    base_composite = factors.composite_rank(prices, ref_v3)

    # Value block (E/P, B/P) on DISCOVERY monthly rebalances → value_rank.
    disc_prices = prices[
        (prices["date"] >= pd.Timestamp(DISCOVERY[0]))
        & (prices["date"] <= pd.Timestamp(DISCOVERY[1]))
    ]
    calendar = sorted(disc_prices["date"].unique().tolist())
    rebalance_dates = [ts.date() for ts in sorted(_rebalance_dates(calendar, _CADENCE))]
    print(
        f"Building value block (E/P, B/P) over {len(rebalance_dates)} rebalances...",
        flush=True,
    )
    session = SessionLocal()
    try:
        fund_frames = _build_fund_frames(prices, rebalance_dates, session)
    finally:
        session.close()
    value_rank = build_value_rank(fund_frames)

    # Orthogonality reconfirm (09 §5 Stage 1) — fail loud if drifted.
    rho, n_pairs = _reconfirm_orthogonality(base_composite, value_rank)
    if not (abs(rho) < _ORTHO_THRESHOLD):
        print(
            f"FAIL: value block drifted (|ρ|={abs(rho):.4f} ≥ {_ORTHO_THRESHOLD}).",
            file=sys.stderr,
        )
        return 1

    # Stable-universe masks (one per U; identical across λ).
    print("Building stable-universe masks (U ∈ {300, 350, 400})...", flush=True)
    masks = {
        u: build_stable_universe_mask(
            prices,
            u,
            _BUFFER_B,
            ref_v3.universe_rank_lookback_td,
            ref_v3.universe_review_cadence,
        )
        for u in _U_GRID
    }

    ledger = ConfigLedger()
    rows: list[ScreenRow] = []
    timelines: dict[str, dict[date, frozenset[str]]] = {}
    for i, cfg in enumerate(_GRID, 1):
        print(f"[{i}/{len(_GRID)}] {cfg.name} — {cfg.label}...", flush=True)
        row, timeline = _screen_config(
            cfg,
            prices,
            index_prices,
            tri_nifty50,
            ind,
            base_composite,
            value_rank,
            masks,
            ledger,
        )
        rows.append(row)
        timelines[cfg.name] = timeline

    # Fill tilt-activity vs the same-U λ=0 control.
    for cfg, row in zip(_GRID, rows):
        if cfg.value_tilt_lambda == 0.0:
            row.tilt_activity_pct = 0.0
            continue
        control_name = f"C-{cfg.universe_size_U}"
        if control_name in timelines:
            row.tilt_activity_pct = _tilt_activity(
                timelines[cfg.name], timelines[control_name]
            )

    print("\nRunning plumbing anchor (5-factor U=350 λ=0)...", flush=True)
    anchor_calmar = _plumbing_anchor(prices, index_prices, ind, masks)

    _print_report(rows, anchor_calmar, rho, n_pairs)
    print(f"\n  ConfigLedger K (this run): {ledger.n_trials}")
    print(
        "  Cumulative K for deflated Sharpe at VT3 = ledger (≥69 at `08`) + these entries (09 §8)."
    )
    print("  FINAL_OOS untouched — VT2 (full battery) next on the §6.1-clearing set.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
