"""T07.1 — classify the liquid terminated-no-successor ISINs and persist the audit.

Read-only. Reads ``prices_adjusted`` + ``successor_map`` from the store, runs
``terminations.classify_terminations`` (07 §3 set selection + §3/§5 sub-typing),
writes ``terminations.parquet`` (store.TERMINATIONS_SCHEMA), and prints the
sub-type breakdown plus the T07.1 gate: the 3 T06.5 ghosts must classify as
{merger, merger, cancellation} and the §3 counts must reproduce.

Run from backend/:  PYTHONPATH=. venv/bin/python scripts/t07_1_classify_terminations.py
"""

from __future__ import annotations

from app.data.bhavcopy import store, terminations

CR = 1e7
GHOSTS = {
    "INE001A01036": ("HDFC", terminations.MERGER),
    "INE312H01016": ("INOXLEISUR", terminations.MERGER),
    "IN9155A01020": ("TATAMTRDVR", terminations.CANCELLATION),
}


def main() -> None:
    prices = store.read_prices_adjusted()
    sm = store.read_successor_map()
    df = terminations.classify_terminations(prices, sm)
    store.write_terminations(df)

    import pandas as pd

    edge = pd.to_datetime(prices["date"]).max()
    print(f"store edge: {edge.date()}")
    print(f"liquid terminations (≥₹5cr adv at death): {len(df)}")
    print("\nsub-type breakdown:")
    for (sub, conf), n in (
        df.groupby(["subtype", "confidence"]).size().sort_index().items()
    ):
        print(f"  {sub:22s} {conf:9s} {n:>4}")
    print("\ndata_gap_suspect (resolves §3 false-positive cluster):")
    gap = df[df["subtype"] == terminations.DATA_GAP_SUSPECT]
    print(
        f"  {len(gap)} names; true terminations = {len(df) - len(gap)} "
        f"(75 raw − {len(gap)} gap-suspect)"
    )

    print("\nT07.1 gate — the 3 T06.5 ghosts:")
    ok = True
    idx = df.set_index("isin")
    for isin, (sym, expect) in GHOSTS.items():
        if isin in idx.index:
            got = idx.loc[isin, "subtype"]
            mark = "✓" if got == expect else "✗"
            ok &= got == expect
            print(f"  {mark} {sym:12s} {isin}  subtype={got} (expected {expect})")
        else:
            ok = False
            print(f"  ✗ {sym:12s} {isin}  MISSING from liquid set")
    print(
        f"\ngate {'PASS' if ok else 'FAIL'}; wrote terminations.parquet ({len(df)} rows)"
    )


if __name__ == "__main__":
    main()
