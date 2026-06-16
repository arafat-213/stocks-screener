"""
diag_universe_quality.py — Spec 04 §3.3 universe / data-integrity (READ-ONLY).

Changes NO parameter. Runs the SAME pre-committed floor config at BASE cost
(the verdict level) and asks the one gate-relevant question: is the NO-GO a
*data bug* rather than a structural property?

Per 04 §2, only a genuine `prices_adjusted` bug (bad split/bonus/glitch) on a
*held* name justifies a fix + single re-run. "The universe is just broad and
noisy" is a structural finding, not a bug, and does NOT reopen the floor.

Checks, in gate-priority order:

  1. ADJUSTMENT-GLITCH SCAN (decisive) — for every traded ISIN, scan its
     `close_tr` (the P&L price that feeds MTM → the equity curve → Calmar) over
     its hold window for single-day moves beyond ±GLITCH_PCT. A clean split is
     back-adjusted and produces NO jump; a jump is the signature of a bad
     adjustment or a real extreme event. Each flag is classified:
       - held?     date inside [first_buy, last_sell]  (only held flags can
                   distort the verdict's equity curve)
       - direction phantom DOWN on a held name suppresses strat equity →
                   could MASK a GO (the verdict-dangerous direction);
                   phantom UP only makes the NO-GO more conservative.
       - corp-action-coincident?  adj_factor / tr_factor steps on that date
                   (a real action explains the move → not a glitch).

  2. CARRY / SUSPENSION EXPOSURE — traded ISINs missing trading days (vs the
     market calendar) while held: the MTM "carry last price" path. Quantifies
     how much realized P&L sits in names that were ever stale-carried.

  3. UNIVERSE BREADTH (structural, NOT a bug) — ADV decile of traded names and
     P&L concentration. Reported for completeness; per the gate this cannot by
     itself reopen the floor.

Run:
    backend/venv/bin/python -m app.backtest_v2.diag_universe_quality
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from app.backtest_v2 import benchmark, engine, metrics
from app.backtest_v2.floor import (
    _BENCH_FETCH_END,
    _BENCH_FETCH_START,
    build_floor_config,
)
from app.backtest_v2.signals import precompute_signals
from app.data.bhavcopy import store

# A clean split/bonus is back-adjusted to zero jump; circuit limits cap real
# single-day moves well below this. A >50% one-day close_tr move on a held name
# is the signature of a bad adjustment (or a genuine extreme event to classify).
GLITCH_PCT = 0.50

logging.getLogger("app.backtest_v2.engine").setLevel(logging.ERROR)
logging.getLogger("app.backtest_v2.portfolio").setLevel(logging.ERROR)


def _hold_windows(fills_log) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    """{isin -> (first_buy_date, last_sell_date)} over the run."""
    first: dict[str, pd.Timestamp] = {}
    last: dict[str, pd.Timestamp] = {}
    for f in fills_log:
        d = pd.Timestamp(f.date)
        if f.side == "buy":
            if f.isin not in first or d < first[f.isin]:
                first[f.isin] = d
        if f.side in ("sell", "trim"):
            if f.isin not in last or d > last[f.isin]:
                last[f.isin] = d
    out: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for isin, fb in first.items():
        out[isin] = (fb, last.get(isin, pd.Timestamp.max))
    return out


def main() -> int:
    config = build_floor_config()
    print("Spec 04 §3.3 — universe / data-integrity (read-only, same floor config)")
    print(f"  glitch threshold: single-day |close_tr| move > {GLITCH_PCT:.0%}\n")

    prices = store.read_prices_adjusted()
    prices["date"] = pd.to_datetime(prices["date"])
    signal_store = precompute_signals(prices, config)
    index_prices = benchmark.load_price_index(_BENCH_FETCH_START, _BENCH_FETCH_END)

    print("  running base engine (verdict level) ...", flush=True)
    result = engine.run(
        prices,
        config,
        index_prices=index_prices,
        cost_level="base",
        signal_store=signal_store,
    )
    m = metrics.compute_metrics(result)
    pnl = {s.isin: s.realized_pnl for s in m.per_name_stats}
    sym = {s.isin: s.symbol for s in m.per_name_stats}
    traded = set(pnl)
    windows = _hold_windows(result.fills_log)

    # Market calendar = all dates seen in the universe (for carry/gap detection).
    market_days = set(prices["date"].unique())

    # Per-ISIN price frames for the traded names only (keep it cheap).
    sub = prices[prices["isin"].isin(traded)].sort_values(["isin", "date"])
    by_isin = {isin: g for isin, g in sub.groupby("isin", sort=False)}

    # ---- 1. Adjustment-glitch scan over hold windows -------------------
    flags: list[dict] = []
    carry_isins: set[str] = set()
    for isin in traded:
        g = by_isin.get(isin)
        if g is None or len(g) < 2:
            continue
        fb, ls = windows.get(isin, (pd.Timestamp.min, pd.Timestamp.max))
        ctr = g["close_tr"].to_numpy(dtype=float)
        adjf = g["adj_factor"].to_numpy(dtype=float)
        trf = g["tr_factor"].to_numpy(dtype=float)
        dates = g["date"].to_numpy()
        ret = np.zeros_like(ctr)
        ret[1:] = np.where(ctr[:-1] > 0, ctr[1:] / ctr[:-1] - 1.0, 0.0)

        # Carry/gap detection: trading days the market was open but this ISIN
        # is absent while held (proxy for suspension/halt carry).
        held_market_days = {d for d in market_days if fb <= pd.Timestamp(d) <= ls}
        present = set(g["date"].tolist())
        if held_market_days - present:
            carry_isins.add(isin)

        for i in range(1, len(ctr)):
            if abs(ret[i]) <= GLITCH_PCT:
                continue
            d = pd.Timestamp(dates[i])
            held = fb <= d <= ls
            corp = (adjf[i] != adjf[i - 1]) or (trf[i] != trf[i - 1])
            flags.append(
                {
                    "isin": isin,
                    "symbol": sym.get(isin, "?"),
                    "date": d.date(),
                    "move": ret[i],
                    "held": held,
                    "corp": bool(corp),
                    "pnl": pnl.get(isin, 0.0),
                }
            )

    held_flags = [f for f in flags if f["held"]]
    held_noncorp = [f for f in held_flags if not f["corp"]]
    held_down_noncorp = [f for f in held_noncorp if f["move"] < 0]

    print()
    print("=" * 92)
    print("  §3.3.1  ADJUSTMENT-GLITCH SCAN  (close_tr feeds MTM → equity → Calmar)")
    print("=" * 92)
    print(f"  traded names                         : {len(traded)}")
    print(f"  single-day |move| > {GLITCH_PCT:.0%} flags total   : {len(flags)}")
    print(f"    └ during a hold window (held)      : {len(held_flags)}")
    print(f"        └ NOT corp-action-explained    : {len(held_noncorp)}")
    print(f"            └ phantom DOWN (mask-a-GO)  : {len(held_down_noncorp)}")
    if held_noncorp:
        print()
        print("  HELD, non-corp-action flags (verdict-relevant — inspect):")
        hdr = f"  {'symbol':<14}{'date':>12}{'move':>9}{'dir':>6}{'realized_pnl ₹':>18}"
        print(hdr)
        print("  " + "─" * 57)
        for f in sorted(held_noncorp, key=lambda x: abs(x["pnl"]), reverse=True):
            d = "DOWN" if f["move"] < 0 else "UP"
            print(
                f"  {f['symbol']:<14}{str(f['date']):>12}{f['move']:>+9.1%}"
                f"{d:>6}{f['pnl']:>18,.0f}"
            )

    # ---- 2. Carry / suspension exposure --------------------------------
    carry_pnl = sum(pnl.get(i, 0.0) for i in carry_isins)
    gross = sum(abs(v) for v in pnl.values()) or 1.0
    print()
    print("=" * 92)
    print("  §3.3.2  CARRY / SUSPENSION EXPOSURE  (MTM 'carry last price' path)")
    print("=" * 92)
    print(
        f"  traded names ever stale-carried      : {len(carry_isins)} / {len(traded)}"
    )
    print(
        f"  their net realized P&L               : ₹{carry_pnl:,.0f}  "
        f"({carry_pnl / gross:+.1%} of gross |P&L|)"
    )

    # ---- 3. Universe breadth (structural, not a bug) -------------------
    # Median adv_20 over each name's hold window; flag below liquidity floor.
    floor_cr = config.liquidity_floor_cr * 1e7  # crore → ₹
    name_adv: list[tuple[str, float, float]] = []  # (symbol, median_adv, pnl)
    for isin in traded:
        g = by_isin.get(isin)
        if g is None:
            continue
        fb, ls = windows.get(isin, (pd.Timestamp.min, pd.Timestamp.max))
        held = g[(g["date"] >= fb) & (g["date"] <= ls)]
        adv = float(held["adv_20"].median()) if len(held) else float("nan")
        name_adv.append((sym.get(isin, "?"), adv, pnl.get(isin, 0.0)))
    below = [x for x in name_adv if not np.isnan(x[1]) and x[1] < floor_cr]

    print()
    print("=" * 92)
    print(
        "  §3.3.3  UNIVERSE BREADTH  (structural — cannot by itself reopen the floor)"
    )
    print("=" * 92)
    print(
        f"  names whose median hold-window ADV < {config.liquidity_floor_cr:.0f}cr floor : "
        f"{len(below)} / {len(traded)}"
    )
    top = sorted(name_adv, key=lambda x: abs(x[2]), reverse=True)[:10]
    print("  top-10 |P&L| contributors (symbol · median ADV ₹cr · realized P&L ₹):")
    for s, adv, p in top:
        advcr = adv / 1e7 if not np.isnan(adv) else float("nan")
        print(f"    {s:<14}{advcr:>8.2f}cr{p:>16,.0f}")

    print()
    print("=" * 92)
    print("  VERDICT (gate)")
    print("=" * 92)
    if held_down_noncorp:
        print(
            f"  ⚠ {len(held_down_noncorp)} phantom-DOWN held flag(s) without a corp-action — "
            "candidate data bug(s).\n  Inspect listed names: a bad split adjustment here "
            "would suppress strat equity and could MASK a GO.\n  If confirmed a bug: fix "
            "prices_adjusted + single floor re-run (same config). Else: structural."
        )
    else:
        print(
            "  No phantom-DOWN, non-corp-action glitch on any held name. The close_tr "
            "series that\n  feeds the equity curve / Calmar is clean of adjustment "
            "artifacts in the verdict-\n  dangerous direction. NO-GO is NOT a §3.3 data "
            "bug — remaining effects are structural\n  (broad survivorship-free universe), "
            "which the gate does NOT treat as a re-run trigger."
        )
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
