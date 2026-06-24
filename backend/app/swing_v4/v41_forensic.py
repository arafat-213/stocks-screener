"""
v41_forensic.py — V4.1 trade-level forensic (DIAGNOSTIC, 00 §6 species).

PURPOSE (not a candidate, not a grid extension):
    The V4.1 cost screen closed NULL — 0/3 configs cleared §6.1, and every base
    Calmar (≤0.145) already trailed Nifty 50 TRI (0.346) BEFORE costs. This script
    answers *why*, descriptively, by re-running the SAME three configs on the SAME
    DISCOVERY window and dumping per-trade + per-exit-type statistics that the cost
    screen aggregated away.

DISCIPLINE (00 §1/§6):
    - DISCOVERY only. v4-FINAL_OOS is NOT loaded or touched.
    - No threshold changed, no grid level added — this re-runs the locked T1/T2/T3.
    - Adds 0 to K (read-only diagnostic; no ConfigLedger entries).
    - Output is a findings memo. Any structural hypothesis it suggests requires a
      SEPARATE pre-registration, frozen before a new return number — never a swap here.

WHAT IT MEASURES (the root-cause questions):
    1. Per-ROUND-TRIP win rate, avg win/loss %, payoff, expectancy
       (the cost screen's hit_rate is per-ISIN — re-entries are lumped; this splits them).
    2. Holding-period distribution (median / IQR / max) — is the book churning?
    3. Exit-reason attribution (catastrophic_floor / atr_trail / macd_cross_down /
       ema50_close / still_open) and avg return per reason — what is killing trades?
    4. Cost decomposition: gross trading P&L vs net, cost as % of capital — is this a
       cost problem or an edge problem? (gross-positive-but-net-negative ⇒ cost;
       gross-near-zero ⇒ weak edge.)
    5. Regime throttle: distribution of the deployable fraction f over DISCOVERY +
       realized exposure — how much was return foregone to the 0/0.5/1 overlay?

Run:
    backend/venv/bin/python -m app.swing_v4.v41_forensic
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from app.backtest_v2 import benchmark, metrics
from app.backtest_v2.schemas import Fill
from app.backtest_v2.validation import DISCOVERY
from app.data.bhavcopy import store
from app.swing_v4.regime import RegimeScore
from app.swing_v4.signals import precompute_swing_signals
from app.swing_v4.v41_cost_screen import (
    _BENCH_FETCH_END,
    _BENCH_FETCH_START,
    _candidate_config,
    _run,
)

log = logging.getLogger(__name__)

# Same grid as the locked screen — NOTHING added (00 §5 Stage 1).
_GRID = [
    (3, "T3 candidate — ATR 3× trail"),
    (1, "T1 comparator — MACD cross-down"),
    (2, "T2 comparator — close < EMA50"),
]


@dataclass
class Trade:
    """One reconstructed round-trip (entry buy → matching full exit sell)."""

    iid: str
    symbol: str
    entry_date: date
    exit_date: date | None
    buy_notional: float
    sell_notional: float
    cost: float  # buy + sell statutory/slippage charged to this trade
    hold_days: float
    exit_reason: str  # "...": one of the 4 rules, or "still_open"

    @property
    def gross_pnl(self) -> float:
        return self.sell_notional - self.buy_notional

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.cost

    @property
    def ret_pct(self) -> float:
        return (
            self.net_pnl / self.buy_notional if self.buy_notional > 0 else float("nan")
        )

    @property
    def gross_ret_pct(self) -> float:
        return (
            self.gross_pnl / self.buy_notional
            if self.buy_notional > 0
            else float("nan")
        )


def _reconstruct_trades(
    fills: list[Fill], exit_log: list[tuple[date, str, str]]
) -> list[Trade]:
    """Walk fills per instrument_id → clean buy→sell round-trips.

    v4 enters with exactly one buy per name (entry scan skips held/queued names) and
    exits the FULL position in one sell, so per iid the fills are a strict alternating
    buy, sell, buy, sell, ... The k-th exit_log entry for an iid (chronological) pairs
    with the k-th sell — every queued exit produces exactly one (unclamped) sell. A buy
    with no following sell is a position still open at the window edge ("still_open").
    """
    reasons_by_iid: dict[str, list[str]] = {}
    for _d, iid, reason in sorted(exit_log, key=lambda t: (t[1], t[0])):
        reasons_by_iid.setdefault(iid, []).append(reason)

    fills_by_iid: dict[str, list[Fill]] = {}
    for f in fills:
        fills_by_iid.setdefault(f.isin, []).append(f)

    trades: list[Trade] = []
    for iid, flist in fills_by_iid.items():
        flist = sorted(flist, key=lambda f: f.date)
        reasons = list(reasons_by_iid.get(iid, []))
        ri = 0
        open_buy: Fill | None = None
        for f in flist:
            if f.side == "buy":
                open_buy = f
            elif f.side in ("sell", "trim") and open_buy is not None:
                reason = reasons[ri] if ri < len(reasons) else "unknown"
                ri += 1
                trades.append(
                    Trade(
                        iid=iid,
                        symbol=f.symbol,
                        entry_date=open_buy.date,
                        exit_date=f.date,
                        buy_notional=open_buy.qty * open_buy.price,
                        sell_notional=f.qty * f.price,
                        cost=open_buy.cost_rupees + f.cost_rupees,
                        hold_days=float((f.date - open_buy.date).days),
                        exit_reason=reason,
                    )
                )
                open_buy = None
        if open_buy is not None:  # bought, never closed → open at window edge
            trades.append(
                Trade(
                    iid=iid,
                    symbol=open_buy.symbol,
                    entry_date=open_buy.date,
                    exit_date=None,
                    buy_notional=open_buy.qty * open_buy.price,
                    sell_notional=0.0,
                    cost=open_buy.cost_rupees,
                    hold_days=float("nan"),
                    exit_reason="still_open",
                )
            )
    return trades


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%" if x == x else "n/a"


def _forensic_one(
    name: str,
    role: str,
    exit_type: int,
    *,
    prices: pd.DataFrame,
    regime: RegimeScore,
    signal_store,
) -> None:
    cfg = _candidate_config(exit_type=exit_type)
    res = _run(
        cfg,
        prices=prices,
        regime=regime,
        signal_store=signal_store,
        cost_level="base",
        whole_shares=True,
    )
    m = metrics.compute_metrics(res)
    trades = _reconstruct_trades(res.fills_log, res.exit_log)
    closed = [t for t in trades if t.exit_reason != "still_open"]
    opens = [t for t in trades if t.exit_reason == "still_open"]

    print()
    print("=" * 96)
    print(f"  {role}   (base cost, whole-share, ₹3.5L, DISCOVERY)")
    print("=" * 96)
    print(
        f"  headline: Calmar {m.calmar:.3f} | Sharpe {m.sharpe:.2f} | "
        f"maxDD {m.max_drawdown:.1%} | CAGR {m.cagr:.2%} | turnover {m.annualized_turnover:.0%}"
    )
    print(
        f"  fills {m.n_fills} | round-trips {len(closed)} closed + {len(opens)} open at edge"
    )

    # ---- 1. per-trade win/loss ----------------------------------------------
    rets = np.array([t.ret_pct for t in closed], dtype=float)
    wins = rets[rets > 0]
    losses = rets[rets <= 0]
    win_rate = len(wins) / len(rets) if len(rets) else float("nan")
    avg_win = float(np.mean(wins)) if len(wins) else float("nan")
    avg_loss = float(np.mean(losses)) if len(losses) else float("nan")
    payoff = (
        (avg_win / abs(avg_loss))
        if (len(wins) and len(losses) and avg_loss != 0)
        else float("nan")
    )
    expectancy = float(np.mean(rets)) if len(rets) else float("nan")
    gross_rets = np.array([t.gross_ret_pct for t in closed], dtype=float)
    gross_win_rate = float(np.mean(gross_rets > 0)) if len(gross_rets) else float("nan")
    print()
    print("  [1] per-round-trip (net of cost):")
    print(
        f"      win rate {win_rate:.1%}  (gross-of-cost {gross_win_rate:.1%})  | "
        f"avg win {_pct(avg_win)}  avg loss {_pct(avg_loss)}  payoff {payoff:.2f}"
    )
    print(f"      expectancy per trade (net) {_pct(expectancy)}")

    # ---- 2. holding period ---------------------------------------------------
    holds = np.array([t.hold_days for t in closed if t.hold_days == t.hold_days])
    if len(holds):
        print()
        print("  [2] holding period (calendar days, closed trades):")
        print(
            f"      median {np.median(holds):.0f}  | p25 {np.percentile(holds, 25):.0f}  "
            f"p75 {np.percentile(holds, 75):.0f}  | min {holds.min():.0f}  max {holds.max():.0f}  "
            f"mean {holds.mean():.0f}"
        )
        short = float(np.mean(holds <= 10))
        print(f"      share of trades held ≤10 calendar days: {short:.1%}")

    # ---- 3. exit-reason attribution -----------------------------------------
    print()
    print("  [3] exit-reason attribution (count | share | avg net ret | win rate):")
    reasons = sorted({t.exit_reason for t in trades})
    for r in reasons:
        grp = [t for t in trades if t.exit_reason == r]
        grp_rets = np.array(
            [t.ret_pct for t in grp if t.ret_pct == t.ret_pct], dtype=float
        )
        avg = float(np.mean(grp_rets)) if len(grp_rets) else float("nan")
        wr = float(np.mean(grp_rets > 0)) if len(grp_rets) else float("nan")
        share = len(grp) / len(trades) if trades else float("nan")
        print(
            f"      {r:<18} {len(grp):>4} | {share:>5.1%} | {_pct(avg):>9} | "
            f"{(wr * 100 if wr == wr else float('nan')):>5.1f}%"
        )

    # ---- 4. cost decomposition ----------------------------------------------
    gross_total = sum(t.gross_pnl for t in closed)
    cost_total = sum(t.cost for t in trades)
    net_total = gross_total - sum(t.cost for t in closed)
    cap = cfg.starting_capital
    print()
    print("  [4] cost vs edge decomposition (Σ over closed round-trips):")
    print(
        f"      gross P&L ₹{gross_total:,.0f} ({gross_total / cap:+.1%} of ₹3.5L)  | "
        f"costs ₹{cost_total:,.0f} ({cost_total / cap:.1%})  | net ₹{net_total:,.0f} "
        f"({net_total / cap:+.1%})"
    )
    print(
        f"      total transaction cost paid (engine) ₹{m.total_cost_paid:,.0f}  "
        f"({m.total_cost_paid / cap:.1%} of capital)"
    )

    # ---- 5. regime throttle --------------------------------------------------
    snap_dates = [pd.Timestamp(s.date) for s in res.snapshots]
    fracs = np.array([regime.deployable_fraction(d) for d in snap_dates], dtype=float)
    print()
    print("  [5] regime throttle (deployable fraction f over DISCOVERY days):")
    for lvl in (0.0, 0.5, 1.0):
        share = float(np.mean(fracs == lvl)) if len(fracs) else float("nan")
        print(f"      f={lvl:>3}: {share:>6.1%} of days")
    print(
        f"      mean f {fracs.mean():.2f}  | realized: avg exposure {m.avg_exposure:.1%}  "
        f"time-in-cash {m.time_in_cash_pct:.1%}"
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
        "v4 / V4.1 TRADE-LEVEL FORENSIC (diagnostic — DISCOVERY only, FINAL_OOS untouched)"
    )
    print(f"  Window: DISCOVERY {DISCOVERY[0]} → {DISCOVERY[1]}  | adds 0 to K")
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

    print("Precomputing swing signals + regime (shared across grid)...", flush=True)
    ref_cfg = _candidate_config(exit_type=3)
    signal_store = precompute_swing_signals(prices, ref_cfg)
    regime = RegimeScore(px, mi, ref_cfg)

    for exit_type, label in _GRID:
        name = label.split()[0]
        _forensic_one(
            name,
            label,
            exit_type,
            prices=prices,
            regime=regime,
            signal_store=signal_store,
        )

    print()
    print("=" * 96)
    print(
        "  DIAGNOSTIC COMPLETE — findings only. No candidate, no grid change, K unchanged."
    )
    print(
        "  v4-FINAL_OOS untouched. Any hypothesis ⇒ a SEPARATE pre-registration (00 §1/§6)."
    )
    print("=" * 96)
    return 0


if __name__ == "__main__":
    sys.exit(main())
