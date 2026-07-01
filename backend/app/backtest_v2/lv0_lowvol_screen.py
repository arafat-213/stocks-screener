"""
lv0_lowvol_screen.py — EXPLORATORY pre-prereg screen for a frozen low-volatility tilt.

Standing workflow (MEMORY: exploratory-screen-before-prereg): a CHEAP in-sample screen
on the spent DISCOVERY window, against a REAL static bar, that NEVER touches the reserved
FINAL_OOS. In-sample FAIL ⇒ skip the v6 prereg. PASS ⇒ earns a full prereg (own K + fresh
OOS). This screen adds 0 to K (it is not a committed candidate).

The thesis under test (the one wall the momentum/timer graveyard never beat):
  *low-vol is de-risking WITHOUT cash drag* — it stays 100% in equities (the low-beta
  cohort) and so, unlike a Faber/regime timer, does not pay the bull-market opportunity
  cost that let a STATIC index/cash sleeve beat every timer (v5 RO1, MOM30-200DMA screen).

So the BINDING bar mirrors v5/00 §5 exactly, adapted to a fully-invested book:
  the low-vol book vs a RISK-MATCHED static (w·Nifty50-TRI + (1-w)·liquid-fund) sleeve,
  where w is solved so the sleeve's realised annualised vol == the book's. Same two
   asset classes, same average RISK; the only difference is *how* the de-risking is
  achieved (picking low-beta stocks vs holding cash). If the book cannot out-Calmar a
  risk-matched cash sleeve in-sample, the "premium beyond de-risking" is not there and
  v6 is not worth a prereg.

Construction (frozen, return-blind, single config — no search, K-neutral):
  active_factors=[low_vol] only, equal-weight, N=20, M=50, monthly, ₹5cr floor universe,
  use_regime_overlay=False (FULLY INVESTED — the whole point), vol_lookback=126 (default).

Run (DISCOVERY only; FINAL_OOS never loaded):
    backend/venv/bin/python -m app.backtest_v2.lv0_lowvol_screen
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2 import benchmark, engine, factors, metrics
from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.costs import CostConfig
from app.backtest_v2.signals import precompute_signals
from app.backtest_v2.signals_v3 import V3SignalStore
from app.backtest_v2.v3_config import V3Config
from app.backtest_v2.validation import DISCOVERY, FINAL_OOS
from app.data.bhavcopy import store
from app.regime_overlay import overlay as ov
from app.regime_overlay.short_rate import load_defensive_index

log = logging.getLogger(__name__)

_FETCH_START = date(2017, 1, 1)
_FETCH_END = DISCOVERY[1]  # 2023-06-30 — never fetch into FINAL_OOS
_TDPY = 252

# Frozen low-vol book construction (single config — K-neutral screen)
_N, _M = 20, 50
_CADENCE = os.environ.get(
    "LV0_CADENCE", "monthly"
)  # "monthly" | "quarterly" | "semi-annual"
_VOL_LOOKBACK = 126


def _v3_config() -> V3Config:
    return V3Config(
        active_factors=["low_vol"],
        target_positions=_N,
        sell_rank_buffer=_M,
        rebalance_cadence=_CADENCE,
        rank_smoothing_months=0,
        vol_lookback_days=_VOL_LOOKBACK,
        universe_mode="floor",  # ₹5cr daily-liquidity universe (simplest baseline)
        use_regime_overlay=False,  # FULLY INVESTED — no timer (the thesis)
        catastrophic_stop_pct=25.0,
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


def _ann_vol(nav: pd.Series) -> float:
    rets = nav.pct_change().dropna()
    return float(rets.std(ddof=1)) * np.sqrt(_TDPY) if len(rets) > 1 else float("nan")


def _solve_risk_matched_w(
    target_vol: float,
    tri: pd.Series,
    defensive: pd.Series,
    cal: list[pd.Timestamp],
    cost: CostConfig,
) -> float:
    """Binary-search the constant equity weight w whose static monthly sleeve has the
    same realised annualised vol as the low-vol book. Sleeve vol is monotone in w."""
    lo, hi = 0.0, 1.0
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        nav = ov.simulate(
            ov.static_fraction(mid, cal), tri, defensive, cost, rebalance="monthly"
        ).nav
        if _ann_vol(nav) < target_vol:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in (
        "app.backtest_v2",
        "app.core.strategy",
        "pandas_ta_classic",
        "pandas_ta",
    ):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    sep = "=" * 92
    print(sep)
    print("  lv0 — EXPLORATORY low-vol screen (DISCOVERY only; FINAL_OOS NEVER loaded)")
    print(
        f"  DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}  |  book = low_vol-only N={_N} M={_M} {_CADENCE}, NO overlay"
    )
    print(
        "  Binding bar = RISK-MATCHED static Nifty50-TRI / liquid-fund sleeve (v5/00 §5 analog)"
    )
    print(sep)

    # ---- load prices, sliced <= DISCOVERY end (FINAL_OOS guard) ----
    prices = store.read_prices_adjusted()
    if prices.empty:
        print("FAIL: prices_adjusted empty.", file=sys.stderr)
        return 2
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices[prices["date"] <= pd.Timestamp(DISCOVERY[1])].copy()
    if prices["date"].max() > pd.Timestamp(DISCOVERY[1]):
        print("FAIL: prices leak past DISCOVERY end.", file=sys.stderr)
        return 2
    print(
        f"  prices sliced <= {DISCOVERY[1]}: rows={len(prices):,} ISINs={prices['isin'].nunique():,} "
        f"max={prices['date'].max().date()}",
        flush=True,
    )

    # ---- benchmark / defensive series (fetched <= DISCOVERY end only) ----
    tri_n50 = benchmark.load_tri(benchmark.TRI_NIFTY_50, _FETCH_START, _FETCH_END)
    tri_mom30 = benchmark.load_tri(benchmark.TRI_MOMENTUM_30, _FETCH_START, _FETCH_END)
    index_prices = benchmark.load_price_index(_FETCH_START, _FETCH_END)
    defensive = load_defensive_index(_FETCH_START, _FETCH_END)
    for nm, s in (("n50", tri_n50), ("mom30", tri_mom30), ("defensive", defensive)):
        if s.empty or s.index.max() > pd.Timestamp(DISCOVERY[1]):
            print(f"FAIL: {nm} empty or leaks past DISCOVERY end.", file=sys.stderr)
            return 2

    # ---- the low-vol book (base + pessimistic) ----
    v3cfg = _v3_config()
    eng = _engine_cfg(v3cfg)
    print("\nBuilding signals + low_vol composite ...", flush=True)
    gate_store = precompute_signals(prices, eng)
    composite = factors.composite_rank(prices, v3cfg)
    ss = V3SignalStore(gate_store._data, composite, v3cfg, universe_mask=None)

    print("Running low-vol book (base, pessimistic) ...", flush=True)
    res_b = engine.run(
        prices, eng, index_prices=index_prices, cost_level="base", signal_store=ss
    )
    res_p = engine.run(
        prices,
        eng,
        index_prices=index_prices,
        cost_level="pessimistic",
        signal_store=ss,
    )
    m_b = metrics.compute_metrics(res_b)
    m_p = metrics.compute_metrics(res_p)
    book_nav = _equity_series(res_b)
    book_vol = _ann_vol(book_nav)
    print(
        f"  book base  Calmar={m_b.calmar:.3f} maxDD={m_b.max_drawdown:.1%} Sharpe={m_b.sharpe:.3f} "
        f"turn={m_b.annualized_turnover * 100:.0f}% annVol={book_vol:.1%}",
        flush=True,
    )
    print(
        f"  book pess  Calmar={m_p.calmar:.3f} maxDD={m_p.max_drawdown:.1%}", flush=True
    )

    # ---- comparators on the book's own trading calendar ----
    cal = [pd.Timestamp(s.date) for s in res_b.snapshots]
    base, pess = CostConfig.base(), CostConfig.pessimistic()

    # context: buy-and-hold full Nifty50 TRI and Mom30 TRI (f = 1.0)
    f_full = ov.static_fraction(1.0, cal)
    m_n50 = ov.metrics_from_nav(ov.simulate(f_full, tri_n50, defensive, base).nav)
    m_mom30 = ov.metrics_from_nav(ov.simulate(f_full, tri_mom30, defensive, base).nav)

    # BINDING: risk-matched static sleeve (vol-matched to the book), base + pess
    w = _solve_risk_matched_w(book_vol, tri_n50, defensive, cal, base)
    sleeve_b = ov.metrics_from_nav(
        ov.simulate(
            ov.static_fraction(w, cal), tri_n50, defensive, base, rebalance="monthly"
        ).nav
    )
    sleeve_p = ov.metrics_from_nav(
        ov.simulate(
            ov.static_fraction(w, cal), tri_n50, defensive, pess, rebalance="monthly"
        ).nav
    )

    print("\n  Context (DISCOVERY, base):")
    print(
        f"     Buy&Hold Nifty50 TRI : Calmar {m_n50['calmar']:.3f}  maxDD {m_n50['max_dd']:.1%}"
    )
    print(
        f"     Buy&Hold Mom30 TRI   : Calmar {m_mom30['calmar']:.3f}  maxDD {m_mom30['max_dd']:.1%}"
    )
    print(
        f"\n  BINDING bar — risk-matched static sleeve (w={w:.2f} equity / {1 - w:.2f} liquid):"
    )
    print(
        f"     sleeve base : Calmar {sleeve_b['calmar']:.3f}  maxDD {sleeve_b['max_dd']:.1%}  annVol {book_vol:.1%}"
    )
    print(
        f"     sleeve pess : Calmar {sleeve_p['calmar']:.3f}  maxDD {sleeve_p['max_dd']:.1%}"
    )

    # ---- verdict ----
    bind_base = m_b.calmar > sleeve_b["calmar"]
    bind_pess = m_p.calmar > sleeve_p["calmar"]
    derisk_ok = (
        m_b.max_drawdown <= m_n50["max_dd"]
    )  # sanity: it actually de-risks vs index
    passed = bind_base and bind_pess and derisk_ok

    print(f"\n{sep}")
    print("  lv0 SCREEN VERDICT")
    print(sep)
    print(
        f"     binding base: book {m_b.calmar:.3f} vs sleeve {sleeve_b['calmar']:.3f} → {'PASS' if bind_base else 'FAIL'}"
    )
    print(
        f"     binding pess: book {m_p.calmar:.3f} vs sleeve {sleeve_p['calmar']:.3f} → {'PASS' if bind_pess else 'FAIL'}"
    )
    print(
        f"     de-risk sanity: book maxDD {m_b.max_drawdown:.1%} <= Nifty50 {m_n50['max_dd']:.1%} → {'PASS' if derisk_ok else 'FAIL'}"
    )
    print(sep)
    if passed:
        print(
            "  >>> SCREEN PASS — low-vol out-Calmars a risk-matched static cash sleeve at BOTH costs."
        )
        print(
            "      Earns a v6 prereg (own K=1, FRESH OOS — DISCOVERY edge is NOT deployable on its own)."
        )
    else:
        print(
            "  >>> SCREEN FAIL — no premium beyond de-risking; do NOT spend a v6 prereg (Rule 12)."
        )
        print("      'Hold a static index/low-vol sleeve' stands as the earned answer.")
    print(sep)
    print(
        f"\n  FINAL_OOS ({FINAL_OOS[0]} → {FINAL_OOS[1]}) NEVER loaded — pristine. Screen adds 0 to K."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
