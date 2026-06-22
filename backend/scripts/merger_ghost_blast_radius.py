"""Blast-radius measurement for the merger/cancellation ghost defect (spec 07 scoping).

A "merger/cancellation ghost" = an ISIN that STOPS trading (terminates) with NO face-value
successor (so 06's successor_map correctly does not cover it) yet was liquid enough for S3 to
hold — so a held position becomes carried-unsellable, exactly like the 3 left in the T06.5
warm-start (HDFC, INOXLEISUR, TATAMTRDVR).

Methodology mirrors 06 §3: derive per-ISIN lifetimes from prices_adjusted, flag terminations
(last_date well before the store edge), exclude asserted succession old-legs (06 handles those)
AND ISINs whose instrument_id chain still trades at the edge, then size by liquidity-at-death.
"""

from __future__ import annotations

import pandas as pd

from app.data.bhavcopy import store


def main() -> None:
    p = store.read_prices_adjusted()
    p["date"] = pd.to_datetime(p["date"])
    edge = p["date"].max()
    # "terminated" = last trade > 15 calendar days before the store edge (delisted/merged/
    # cancelled), NOT a transient suspension that later resumed.
    term_cutoff = edge - pd.Timedelta(days=15)

    life = p.groupby("isin").agg(
        symbol=("symbol", "last"),
        first_date=("date", "min"),
        last_date=("date", "max"),
        instrument_id=("instrument_id", "last"),
    )
    # adv_20 on each ISIN's own last trading day (liquidity-at-death; same defn as 06 §11).
    last_rows = p.sort_values("date").groupby("isin").tail(1).set_index("isin")
    life["adv_last"] = last_rows["adv_20"]

    sm = store.read_successor_map()
    asserted_old = set(sm.loc[sm["asserted"], "old_isin"]) if sm is not None else set()
    # An instrument_id whose chain still trades at the edge is alive (not a ghost).
    alive_iids = set(p.loc[p["date"] >= term_cutoff, "instrument_id"])

    term = life[life["last_date"] < term_cutoff].copy()
    # Drop asserted succession old-legs (06 stitches them) and any whose chain still trades.
    term = term[~term.index.isin(asserted_old)]
    term = term[~term["instrument_id"].isin(alive_iids)]

    CR = 1e7  # adv_20 is stored in RUPEES; the S3 liquidity floor is Rs 5cr = 5e7.
    liquid = term[term["adv_last"] >= 5 * CR]
    recent = liquid[liquid["last_date"] >= pd.Timestamp("2023-01-01")]

    print(f"store edge: {edge.date()}   termination cutoff: {term_cutoff.date()}")
    print(f"distinct ISINs:                        {life.shape[0]:>6}")
    print(f"terminated (no face-value successor):  {term.shape[0]:>6}")
    print(f"  ...liquid at death (adv_last>=Rs5cr):{liquid.shape[0]:>6}  <- ghost-risk")
    print(f"  ...liquid AND recent (>=2023):       {recent.shape[0]:>6}")

    print(
        "\nTop-30 liquid terminations by adv-at-death (the names S3 most likely held):"
    )
    top = liquid.sort_values("adv_last", ascending=False).head(30)
    for isin, r in top.iterrows():
        print(
            f"  {isin}  {r['symbol']:14s}  last={r['last_date'].date()}  "
            f"adv_last={r['adv_last'] / CR:8.1f}cr"
        )

    # The 3 T06.5 ghosts — confirm they are captured here (sanity).
    print("\nThe 3 T06.5 warm-start ghosts (expect all present + liquid):")
    for iid in ["INE001A01036", "INE312H01016", "IN9155A01020"]:
        if iid in liquid.index:
            r = liquid.loc[iid]
            print(
                f"  {iid}  {r['symbol']:14s}  last={r['last_date'].date()}  "
                f"adv_last={r['adv_last'] / CR:.1f}cr  -> captured"
            )
        else:
            inlife = iid in life.index
            print(
                f"  {iid}  NOT in liquid set (in_life={inlife}) — "
                f"last={life.loc[iid, 'last_date'].date() if inlife else '?'}"
            )


if __name__ == "__main__":
    main()
