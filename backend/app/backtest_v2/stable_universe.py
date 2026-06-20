"""
stable_universe.py — SU0 point-in-time stable-universe membership mask.

Pre-registered in `specs/v3/08_STABLE_UNIVERSE_PREREG.md` §3. Replaces the
per-rebalance ₹5cr liquidity-floor "universe" — the source of the ~90 % membership
churn that tripped §6.1/§6.2 (turnover-decomp-churn-dominant) — with a stable,
slow-reviewed, buffered membership set:

  - **Review cadence:** semi-annual (Jan 31 / Jul 31), each resolved to the last
    trading day on or before that calendar date, and frozen between reviews.
  - **Ranking metric:** at each review date D, rank names by the **median adv_20
    over the `lookback_td` (126) trading days ending at D** — causal, no lookahead,
    reusing the existing adv_20 series.
  - **Hysteresis:** a name *enters* if its review-date rank is in the top `U`; a name
    already *in* the set *stays* until its rank falls below `B * U` (the buffer band).
  - **Minimum age:** the 126-td median uses `min_periods = lookback_td`, so a name
    is rank-eligible only once it has a full lookback window of history — the
    "new listings need a minimum age" rule (08 §3, `01_DATA_LAYER §5.5`).

This is a **signal-layer artefact only**: the mask is AND-ed into
`V3SignalStore.entry_gate` (signals_v3.py), no engine edit (08 §3). The ₹5cr adv_20
floor is retained *separately* as a per-day tradeability safety inside entry_gate —
a name whose liquidity collapses is not held even if "in" the stable set.

No-lookahead guarantee: membership on day d is the set from the latest review whose
effective (trading) date is <= d; that review's ranking reads only adv_20 up to and
including D. Corrupting any adv_20 strictly after D cannot change the set at D — this
is asserted directly in the SU0 tests.
"""

from __future__ import annotations

import bisect
from datetime import date

import pandas as pd


class StableUniverseMask:
    """
    Immutable point-in-time membership oracle.

    Built once by `build_stable_universe_mask`; queried O(log R) per (day) by
    `V3SignalStore.entry_gate` (R = number of review dates, ~2/year). Holds the
    review schedule as parallel sorted lists of effective timestamps and the
    frozen member set that takes effect on each.
    """

    def __init__(self, schedule: list[tuple[pd.Timestamp, frozenset[str]]]) -> None:
        # schedule must be sorted ascending by effective date.
        self._eff: list[pd.Timestamp] = [t for t, _ in schedule]
        self._sets: list[frozenset[str]] = [s for _, s in schedule]

    def members(self, day: pd.Timestamp | date) -> frozenset[str]:
        """Frozen member set in force on `day` (empty before the first review)."""
        ts = pd.Timestamp(day)
        i = bisect.bisect_right(self._eff, ts) - 1
        if i < 0:
            return frozenset()
        return self._sets[i]

    def is_member(self, day: pd.Timestamp | date, isin: str) -> bool:
        """True iff `isin` is in the stable universe in force on `day`."""
        return isin in self.members(day)

    @property
    def review_dates(self) -> list[pd.Timestamp]:
        """The resolved (trading-day) review effective dates, ascending."""
        return list(self._eff)

    def size_history(self) -> list[tuple[pd.Timestamp, int]]:
        """(effective_date, |members|) per review — a diagnostic for SU1 churn reporting."""
        return [(t, len(s)) for t, s in zip(self._eff, self._sets)]


def _review_trading_days(cal: pd.DatetimeIndex, cadence: str) -> list[pd.Timestamp]:
    """
    Resolve the semi-annual review calendar to actual trading days.

    For each year in the calendar's span, the Jan-31 and Jul-31 review anchors are
    each mapped to the last trading day on or before that anchor. Anchors before the
    first trading day are skipped. Returns a sorted, de-duplicated list.
    """
    if cadence != "semi-annual":
        raise ValueError(
            f"stable_universe: only 'semi-annual' cadence is supported (08 §3); got {cadence!r}"
        )
    if len(cal) == 0:
        return []
    anchors: list[pd.Timestamp] = []
    for year in range(cal[0].year, cal[-1].year + 1):
        for month, dom in ((1, 31), (7, 31)):
            anchors.append(pd.Timestamp(year=year, month=month, day=dom))
    out: list[pd.Timestamp] = []
    for anchor in anchors:
        prior = cal[cal <= anchor]
        if len(prior) == 0:
            continue
        out.append(prior[-1])
    return sorted(set(out))


def build_stable_universe_mask(
    prices: pd.DataFrame,
    universe_size_U: int,
    universe_buffer_B: float,
    lookback_td: int = 126,
    cadence: str = "semi-annual",
) -> StableUniverseMask:
    """
    Build the point-in-time stable-universe mask from the long-format price frame.

    Args:
        prices: long (isin, date, adv_20, ...) frame — `store.read_prices_adjusted`.
        universe_size_U: top-U by trailing liquidity enter the universe (08 §4).
        universe_buffer_B: hysteresis multiple; a member stays until rank > B*U.
        lookback_td: trading-day window for the median-adv_20 rank metric (126).
        cadence: review cadence — 'semi-annual' only (08 §3).

    Returns:
        StableUniverseMask answering membership at any day with no lookahead.
    """
    if universe_size_U <= 0:
        raise ValueError(f"universe_size_U must be > 0; got {universe_size_U}")
    if universe_buffer_B < 1.0:
        raise ValueError(
            f"universe_buffer_B must be >= 1.0 (buffer cannot be tighter than a "
            f"hard review, else a just-entered name could drop instantly); got {universe_buffer_B}"
        )
    if lookback_td <= 0:
        raise ValueError(f"lookback_td must be > 0; got {lookback_td}")

    cols = prices[["isin", "date", "adv_20"]].copy()
    cols["date"] = pd.to_datetime(cols["date"])
    cal = pd.DatetimeIndex(sorted(cols["date"].unique()))

    # 126-td median of adv_20 per ISIN, causal, min_periods = full window so a name
    # is rank-eligible only with a full lookback of history (the minimum-age rule).
    cols = cols.sort_values(["isin", "date"])
    cols["liq"] = cols.groupby("isin", sort=False)["adv_20"].transform(
        lambda s: s.rolling(lookback_td, min_periods=lookback_td).median()
    )

    review_days = _review_trading_days(cal, cadence)
    band = universe_buffer_B * universe_size_U

    # Index review-date snapshots once: {review_ts -> DataFrame(isin, liq) for that day}.
    by_date = {d: g for d, g in cols.groupby("date", sort=False)}

    members: set[str] = set()
    schedule: list[tuple[pd.Timestamp, frozenset[str]]] = []
    for review_ts in review_days:
        snap = by_date.get(review_ts)
        if snap is None:
            # Review day has no rows at all (should not happen — it is a calendar
            # trading day) — carry the previous set forward unchanged.
            schedule.append((review_ts, frozenset(members)))
            continue
        snap = snap.dropna(subset=["liq"]).sort_values("liq", ascending=False)
        # 1-based liquidity rank (rank 1 = most liquid).
        rank_of: dict[str, int] = {
            isin: i + 1 for i, isin in enumerate(snap["isin"].tolist())
        }
        # Stay-in: existing members whose rank is still within the buffer band.
        kept = {isin for isin in members if rank_of.get(isin, 1 << 30) <= band}
        # Enter: top-U by liquidity rank.
        entered = {isin for isin, r in rank_of.items() if r <= universe_size_U}
        members = kept | entered
        schedule.append((review_ts, frozenset(members)))

    return StableUniverseMask(schedule)
