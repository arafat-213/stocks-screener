"""T06.5 diagnostic — WHY is the warm-started book mostly-cash + 3 ghosts at the edge?

Runs the authoritative from-scratch S3 backtest over the stitched store (the same brain
the warm-start replays) capturing the per-day snapshot trajectory, then reports:
  * n_positions + cash% over time (did the book ever fill to ~20 in risk-on periods?);
  * the regime state at the final date (risk-on/off explains a cash-heavy edge);
  * whether the 4 face-value-succession old ISINs ever end as carried ghosts (T06 target),
    via suspension_log (the engine logs every dropped/carried fill there).
"""

from __future__ import annotations

import logging

import pandas as pd

from app.backtest_v2 import benchmark, engine
from app.backtest_v2.costs import CostConfig, fill_cost
from app.data.bhavcopy import store
from app.paper_v2 import s3_config

logging.basicConfig(level=logging.ERROR)  # mute the MTM/fill-drop warning spam

# The 4 asserted face-value successions from 06 §2 (old legs T06 stitches).
SUCCESSION_OLD = {
    "INE296A01024": "BAJFINANCE",
    "INE745G01035": "MCX",
    "INE418L01021": "NAZARA",
    "INE07O001018": "EASEMYTRIP",
}
# The 3 still-stuck names from the re-warm-start (all merger/cancellation terminations).
MERGER_GHOSTS = {
    "INE001A01036": "HDFC (->HDFCBANK merger 2023)",
    "IN9155A01020": "TATAMTRDVR (DVR cancelled 2024)",
    "INE312H01016": "INOXLEISUR (->PVRINOX merger 2023)",
}


def main() -> None:
    prices = store.read_prices_adjusted()
    prices["date"] = pd.to_datetime(prices["date"])
    inception = prices["date"].min().date()
    target = prices["date"].max().date()
    index_prices = benchmark.load_price_index(inception, target)

    v3cfg = s3_config.make_s3_v3config()
    eng_cfg = s3_config.make_s3_engine_cfg(v3cfg)
    ss = s3_config.build_s3_signal_store(prices, v3cfg)
    result = engine.run(
        prices,
        eng_cfg,
        cost_fn=fill_cost,
        cost_cfg=CostConfig(),
        index_prices=index_prices,
        signal_store=ss,
    )

    snaps = result.snapshots
    npos = [s.n_positions for s in snaps]
    print(
        f"snapshots={len(snaps)}  peak_n_positions={max(npos)}  "
        f"final_n_positions={npos[-1]}  days_with>=18_names={sum(n >= 18 for n in npos)}"
    )

    print("\n date         equity        cash      cash%  n_pos")
    for probe in [
        "2018-06-29",
        "2020-03-31",
        "2021-12-31",
        "2023-12-29",
        "2024-06-28",
        "2025-06-30",
        "2025-12-31",
        str(target),
    ]:
        pdp = pd.Timestamp(probe).date()
        cand = [s for s in snaps if _d(s.date) <= pdp]
        if not cand:
            continue
        s = cand[-1]
        print(
            f" {_d(s.date)}  {s.equity:12,.0f}  {s.cash:12,.0f}  "
            f"{100.0 * s.cash / s.equity if s.equity else 0:5.1f}  {s.n_positions:3d}"
        )

    # succession-ghost check via suspension_log (isin -> [carried dates]).
    susp = result.suspension_log
    print(
        "\nsuccession OLD legs in suspension_log (T06 target — want NONE persisting):"
    )
    for iid, sym in SUCCESSION_OLD.items():
        ds = susp.get(iid, [])
        tail = f"{min(ds)}..{max(ds)} ({len(ds)})" if ds else "—"
        print(f"   {iid} {sym:12s}: {tail}")
    print(
        "\nthe 3 still-stuck names in suspension_log (merger/cancel — OUT of T06 scope):"
    )
    for iid, sym in MERGER_GHOSTS.items():
        ds = susp.get(iid, [])
        tail = f"{min(ds)}..{max(ds)} ({len(ds)})" if ds else "—"
        print(f"   {iid} {sym}: {tail}")

    # regime at the edge.
    idx = index_prices.sort_index()
    dma200 = idx.rolling(200).mean()
    on = idx.iloc[-1] > dma200.iloc[-1]
    print(
        f"\nREGIME at {idx.index[-1].date()}: index={idx.iloc[-1]:.1f} "
        f"200DMA={dma200.iloc[-1]:.1f} => {'RISK-ON' if on else 'RISK-OFF'}"
    )
    print(
        f"  risk-off days in last 60 trading days: "
        f"{int((idx.iloc[-60:] < dma200.iloc[-60:]).sum())}/60"
    )


def _d(x):
    return x.date() if hasattr(x, "date") else x


if __name__ == "__main__":
    main()
