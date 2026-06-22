"""T06.1 — Build + audit the ISIN-succession map.

When a company changes ISIN (typically a face-value sub-division —
``INE296A01024 → INE296A01032``) the old and new ISINs remain two distinct
instruments in ``prices_adjusted``: the signal/holdings layer (keyed on raw ISIN)
loses momentum history on the new leg and can never sell a position held under the
old leg. ``05_DATA_ADJUSTMENT_REMEDIATION`` fixed the *adjustment* layer (the new
leg's prices are correct); this module produces the *identity* map that
``06_ISIN_SUCCESSION_CONTINUITY`` (T06.2+) uses to stitch old + new into one
continuous instrument.

The map is built from **adjacent same-symbol ISIN pairs** (the old leg's last
trading date immediately precedes the new leg's first), scored by three converging
signals; a link is **asserted** only when **>= 2** agree (mirroring ``05``'s
``unmatched``-audit discipline — singletons/conflicts are surfaced, never inferred):

  * ``sig_consecutive`` — the old leg's ``last_date`` is the trading day immediately
    before the new leg's ``first_date`` (an instrument handover, not a re-listing
    after a gap).
  * ``sig_prefix`` — the two ISINs share the ``INE######01`` issuer prefix
    (``isin[:9]``) and the new leg's two-digit security suffix (``isin[9:11]``)
    strictly increments (the NSE re-issue pattern for a face-value split).
  * ``sig_ca_split`` — a face-value-split CA event is filed under the *old* ISIN
    near the transition date.

Asserted edges are collapsed with union-find so each succession chain (A→B→C) has
one **root** = the oldest ISIN; ``root_isin`` is what T06.2 materialises as the
chain-constant ``instrument_id``.

This module is read-only over the existing store and writes only the two new
artifacts (``successor_map.parquet`` / ``successor_unmatched.parquet``). It makes
no schema change to ``prices_adjusted`` and no engine/signal edits (those are
T06.2/T06.3). The build is idempotent — re-running overwrites the artifacts.
"""

import logging

import numpy as np
import pandas as pd

from app.data.bhavcopy import store
from app.data.bhavcopy.corporate_actions import SPLIT

logger = logging.getLogger(__name__)

# A link is asserted only when at least this many of the three signals agree.
MIN_SIGNALS = 2
# S3 liquidity gate (₹5 cr ADV); an old leg liquid on its last day is ghost-risk.
LIQUID_ADV_THRESHOLD = 5e7
# CA-split signal window: a split filed within this many calendar days either side
# of the transition counts as supporting evidence for the old leg.
CA_SPLIT_WINDOW_DAYS = 15


# --------------------------------------------------------------------------- #
# Candidate generation                                                         #
# --------------------------------------------------------------------------- #
def candidate_pairs(lifetimes: pd.DataFrame) -> pd.DataFrame:
    """Adjacent same-symbol ISIN pairs from ``isin_symbol_map`` (instrument
    lifetimes: ``isin, symbol, first_date, last_date``).

    For each symbol with >1 ISIN, sort by ``first_date`` and emit each
    consecutive ``(old, new)`` pair. These are the succession *candidates* — the
    three signals decide which are real.
    """
    rows: list[dict] = []
    for symbol, grp in lifetimes.groupby("symbol", sort=False):
        grp = grp.sort_values("first_date").reset_index(drop=True)
        if len(grp) < 2:
            continue
        for i in range(len(grp) - 1):
            old = grp.iloc[i]
            new = grp.iloc[i + 1]
            rows.append(
                {
                    "symbol": str(symbol),
                    "old_isin": str(old["isin"]),
                    "new_isin": str(new["isin"]),
                    "old_last": old["last_date"],
                    "new_first": new["first_date"],
                }
            )
    return pd.DataFrame(
        rows, columns=["symbol", "old_isin", "new_isin", "old_last", "new_first"]
    )


# --------------------------------------------------------------------------- #
# Signals                                                                      #
# --------------------------------------------------------------------------- #
def _next_trading_day(day, trading_days: np.ndarray):
    """First trading day strictly after ``day`` (``None`` if ``day`` is the last)."""
    i = np.searchsorted(trading_days, np.datetime64(day), side="right")
    return trading_days[i] if i < len(trading_days) else None


def signal_consecutive(pairs: pd.DataFrame, trading_days) -> pd.Series:
    """True where the new leg's first trading day immediately follows the old
    leg's last (no trading-day gap between the two legs)."""
    td = np.sort(
        np.asarray(pd.DatetimeIndex(trading_days).values, dtype="datetime64[ns]")
    )
    nxt = pairs["old_last"].map(lambda d: _next_trading_day(d, td))
    return pd.to_datetime(pd.Series(list(nxt), index=pairs.index)) == pairs["new_first"]


def signal_prefix(pairs: pd.DataFrame) -> pd.Series:
    """True where both ISINs share the ``isin[:9]`` issuer prefix and the new
    leg's ``isin[9:11]`` two-digit security suffix strictly increments."""

    def _ok(old: str, new: str) -> bool:
        if len(old) != 12 or len(new) != 12 or old[:9] != new[:9]:
            return False
        try:
            return int(new[9:11]) > int(old[9:11])
        except ValueError:
            return False

    return pairs.apply(lambda r: _ok(r["old_isin"], r["new_isin"]), axis=1).astype(bool)


def signal_ca_split(
    pairs: pd.DataFrame,
    ca_events: pd.DataFrame,
    window_days: int = CA_SPLIT_WINDOW_DAYS,
) -> pd.Series:
    """True where a face-value-split CA event is filed under the *old* ISIN within
    ``window_days`` of the transition (``05`` files such events under the old ISIN)."""
    if ca_events.empty:
        return pd.Series(False, index=pairs.index, dtype=bool)
    splits = ca_events[ca_events["type"] == SPLIT]
    by_isin = {str(k): g for k, g in splits.groupby("isin", sort=False)}
    window = pd.Timedelta(days=window_days)

    def _ok(row) -> bool:
        s = by_isin.get(row["old_isin"])
        if s is None:
            return False
        lo = row["old_last"] - window
        hi = row["new_first"] + window
        return bool(((s["ex_date"] >= lo) & (s["ex_date"] <= hi)).any())

    return pairs.apply(_ok, axis=1).astype(bool)


# --------------------------------------------------------------------------- #
# Chain resolution (union-find)                                                #
# --------------------------------------------------------------------------- #
def _resolve_roots(
    asserted: pd.DataFrame, first_date_by_isin: dict[str, pd.Timestamp]
) -> dict[str, str]:
    """Union-find over asserted ``old→new`` edges → ``isin → root_isin`` where the
    root is the **oldest** ISIN (earliest ``first_date``) of each chain. Collapses
    multi-hop chains (A→B→C) onto a single root."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        # Keep the oldest ISIN as the component root.
        fa = first_date_by_isin.get(ra, pd.Timestamp.max)
        fb = first_date_by_isin.get(rb, pd.Timestamp.max)
        if fb < fa:
            ra, rb = rb, ra
        parent[rb] = ra

    for r in asserted.itertuples(index=False):
        union(r.old_isin, r.new_isin)

    return {isin: find(isin) for isin in parent}


# --------------------------------------------------------------------------- #
# Build                                                                        #
# --------------------------------------------------------------------------- #
def build_successor_map(
    lifetimes: pd.DataFrame,
    ca_events: pd.DataFrame,
    trading_days,
    old_leg_adv_last: pd.Series | dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the succession map + the unmatched-audit frame.

    Parameters
    ----------
    lifetimes:
        ``isin_symbol_map`` rows — ``isin, symbol, first_date, last_date``.
    ca_events:
        Parsed CA events (``store.read_corporate_actions``); the split rows feed
        ``sig_ca_split``.
    trading_days:
        The trading calendar (any datetime-like sequence) for the consecutive-day
        signal.
    old_leg_adv_last:
        Optional ``old_isin -> adv_20-on-last-day``. Used only to flag
        ``liquid_old_leg`` (ghost-risk); absent → all False.

    Returns
    -------
    ``(successor_map, successor_unmatched)`` conforming to the store schemas. The
    map holds **every** candidate (``asserted`` flags the >=2-signal links);
    ``unmatched`` is the triage subset (singletons + conflicts) with a ``reason``.
    """
    pairs = candidate_pairs(lifetimes)
    if pairs.empty:
        return (
            store._empty(store.SUCCESSOR_MAP_SCHEMA),
            store._empty(store.SUCCESSOR_UNMATCHED_SCHEMA),
        )

    pairs = pairs.copy()
    pairs["sig_consecutive"] = signal_consecutive(pairs, trading_days)
    pairs["sig_prefix"] = signal_prefix(pairs)
    pairs["sig_ca_split"] = signal_ca_split(pairs, ca_events)
    pairs["signals_matched"] = (
        pairs[["sig_consecutive", "sig_prefix", "sig_ca_split"]].sum(axis=1).astype(int)
    )
    pairs["asserted"] = pairs["signals_matched"] >= MIN_SIGNALS

    # Conflict guard: an old or new ISIN must take part in at most one asserted
    # edge. A fork (same old → two new, or two old → same new) is ambiguous —
    # demote both sides to unmatched rather than guess.
    asserted = pairs[pairs["asserted"]]
    dup_old = asserted["old_isin"].duplicated(keep=False)
    dup_new = asserted["new_isin"].duplicated(keep=False)
    conflict_idx = asserted.index[dup_old.values | dup_new.values]
    pairs["conflict"] = False
    pairs.loc[conflict_idx, "conflict"] = True
    if len(conflict_idx):
        pairs.loc[conflict_idx, "asserted"] = False
        logger.warning(
            "succession: %d candidate pair(s) demoted — ambiguous successor (fork)",
            len(conflict_idx),
        )

    # Resolve chain roots over the (post-conflict) asserted edges.
    first_date_by_isin = lifetimes.groupby("isin")["first_date"].min().to_dict()
    roots = _resolve_roots(pairs[pairs["asserted"]], first_date_by_isin)
    pairs["root_isin"] = pairs["old_isin"].map(roots).fillna("")
    pairs.loc[~pairs["asserted"], "root_isin"] = ""

    # Liquidity (ghost-risk) flag on the old leg.
    if old_leg_adv_last is not None:
        adv = pd.Series(old_leg_adv_last)
        pairs["liquid_old_leg"] = (
            pairs["old_isin"].map(adv).fillna(0.0) >= LIQUID_ADV_THRESHOLD
        )
    else:
        pairs["liquid_old_leg"] = False

    successor_map = pairs.rename(columns={"new_first": "transition_date"})[
        list(store.SUCCESSOR_MAP_SCHEMA)
    ].reset_index(drop=True)

    # Unmatched audit: non-asserted candidates, with a reason.
    def _reason(row) -> str:
        if row["conflict"]:
            return "conflict: ambiguous successor (fork)"
        return f"only {int(row['signals_matched'])} signal(s) (need >= {MIN_SIGNALS})"

    um = pairs[~pairs["asserted"]].copy()
    um["reason"] = um.apply(_reason, axis=1) if not um.empty else pd.Series(dtype=str)
    successor_unmatched = um.rename(columns={"new_first": "transition_date"})[
        list(store.SUCCESSOR_UNMATCHED_SCHEMA)
    ].reset_index(drop=True)

    return successor_map, successor_unmatched


def run_succession_build(root: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the existing store, build the map, and persist both artifacts.

    Idempotent: overwrites ``successor_map.parquet`` / ``successor_unmatched.parquet``.
    Returns the two frames for inspection/logging.
    """
    lifetimes = store.read_isin_symbol_map(root)
    ca_events = store.read_corporate_actions(root)

    # Trading calendar: distinct dates from universe_membership (cheaper than a
    # full prices read).
    um = store.read_universe_membership(root)
    trading_days = np.sort(um["date"].unique())

    # adv_20 on each old leg's last trading day → ghost-risk flag.
    pairs = candidate_pairs(lifetimes)
    old_leg_adv_last: dict[str, float] = {}
    if not pairs.empty:
        old_isins = pairs["old_isin"].unique().tolist()
        px = store.read_prices_adjusted(root, isins=old_isins)
        if not px.empty:
            last = px.sort_values("date").groupby("isin").tail(1)
            old_leg_adv_last = dict(zip(last["isin"], last["adv_20"]))

    successor_map, successor_unmatched = build_successor_map(
        lifetimes, ca_events, trading_days, old_leg_adv_last
    )

    store.write_successor_map(successor_map, root)
    store.write_successor_unmatched(successor_unmatched, root)

    n_assert = int(successor_map["asserted"].sum())
    n_liquid = int((successor_map["asserted"] & successor_map["liquid_old_leg"]).sum())
    logger.info(
        "succession: %d candidates, %d asserted (%d liquid ghost-risk), %d unmatched",
        len(successor_map),
        n_assert,
        n_liquid,
        len(successor_unmatched),
    )
    return successor_map, successor_unmatched
