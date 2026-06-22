"""
identity.py — chain-constant instrument identity resolution for the sim/signal layer.

`06_ISIN_SUCCESSION_CONTINUITY.md` T06.3. The price store (T06.2) carries a
chain-constant `instrument_id` column: for a face-value-split re-issue
(`INE296A01024 → INE296A01032`) both legs share one `instrument_id` (= the oldest,
root ISIN); a standalone ISIN gets `instrument_id == isin`.

The v2 sim/signal layer keys *everything* on the raw `isin` (02 §"contracts"):
factor history groups by isin, the engine's positions / price lookups / universe
membership are isin-keyed. That makes a succession two unrelated instruments — the
new leg is momentum-blind for ~the lookback window, and a position held on the old
leg becomes an unsellable ghost once it stops trading (06 §1).

`collapse_to_instrument_id` is the **single resolution join** that fixes both: it
relabels the identity column from raw `isin` to `instrument_id` *before* the frame
enters the signal/engine primitives. Because a succession's two legs trade on
strictly **date-disjoint** ranges (06 §3 consecutive-day invariant), relabelling is
all that is needed — on any given date exactly one leg is live, so every per-date
lookup (open/close/close_tr/adv_20) and the universe-membership set resolve to that
live leg automatically, while the per-instrument time series (momentum, EMA) is the
gap-free concatenation of both legs (whose price space `05` already aligned via
`adj_factor`).

Identity for selection/holdings becomes `instrument_id`; execution still happens at
the live leg's prices (resolved by date). Fills are *labelled* with `instrument_id`
rather than the raw live ISIN — economically identical for the backtest; the live
paper book maps back to the tradeable ISIN/symbol downstream (T06.5).

**Byte-identical guarantee (the parity guard, T06.3 success gate c):**
  - a frame with no `instrument_id` column (every pre-T06.2 fixture)  → returned unchanged;
  - a frame whose `instrument_id` equals `isin` for every row (any universe with no
    succession) → returned unchanged (no copy).
So this is a no-op for everything except the succession chains it is meant to fix.
"""

from __future__ import annotations

import pandas as pd


def collapse_to_instrument_id(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Return `prices` with the identity column `isin` relabelled to the chain-constant
    `instrument_id` (T06.2). The original frame is never mutated.

    No-op (returns the input object unchanged) when there is nothing to stitch:
      - the `instrument_id` column is absent (pre-T06.2 store / older fixtures), or
      - `instrument_id == isin` for every row (no succession in this frame).

    Idempotent: collapsing an already-collapsed frame is a no-op (post-collapse
    `isin == instrument_id`), so applying it independently at each signal/engine
    entry point is safe.

    Fails loud (Rule 12) if collapsing produces overlapping `(isin, date)` rows —
    that can only happen if two legs of a chain trade on the same date, violating
    the 06 §3 consecutive-day invariant. A silent overlap would corrupt the
    concatenated momentum series, so we raise rather than let one leg win.
    """
    if "instrument_id" not in prices.columns:
        return prices
    if prices["isin"].equals(prices["instrument_id"]):
        return prices

    out = prices.copy()
    out["isin"] = out["instrument_id"].to_numpy()

    dup = out.duplicated(subset=["isin", "date"])
    if dup.any():
        bad = sorted(out.loc[dup, "isin"].unique().tolist())
        raise ValueError(
            "collapse_to_instrument_id: succession chains produced overlapping "
            f"(instrument_id, date) rows for {bad[:10]} "
            f"({len(bad)} chain(s) total) — chain legs must be date-disjoint "
            "(06 §3 consecutive-day invariant). Re-check the successor map / store."
        )
    return out
