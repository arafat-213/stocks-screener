"""
SU0 acceptance tests — stable-universe membership mask (08 §3).

All offline: synthetic frames only, no network / DB / live parquet (Rule 5).

WHY each test group exists:
  review_calendar — semi-annual anchors (Jan 31 / Jul 31) must resolve to the last
                    trading day on or before the anchor, so a holiday on the anchor
                    never silently drops a review.
  top_u           — with no prior members, exactly the top-U by trailing-adv_20
                    liquidity enter the universe (the entry rule).
  hysteresis      — THE load-bearing test: a member that slips out of the top-U but
                    stays within the B*U buffer band must be RETAINED (the churn
                    antidote); a member that falls beyond the band must be DROPPED.
                    If membership just re-took the top-U each review, the buffer is a
                    no-op and the whole redesign is pointless.
  no_lookahead    — membership on a review date must depend only on adv_20 up to and
                    including that date. Corrupting adv_20 strictly AFTER a review
                    must leave that review's set (and all earlier sets) identical.
  min_age         — a name without a full lookback window of history is not
                    rank-eligible (08 §3 minimum-age rule), so a brand-new high-ADV
                    listing cannot jump straight in.
  floor_identity  — 'floor' mode applies NO mask (mask is None), so the C0 control is
                    byte-identical to every pre-08 run; 'stable' mode AND-s the mask
                    into entry_gate and genuinely restricts eligibility.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.backtest_v2.signals_v3 import V3SignalStore, precompute_v3_signals
from app.backtest_v2.stable_universe import (
    StableUniverseMask,
    _review_trading_days,
    build_stable_universe_mask,
)
from app.backtest_v2.v3_config import V3Config

# Small lookback so synthetic frames stay tiny — the rank metric is identical in
# shape to the production 126-td window, just shorter.
_LB = 5


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _adv_frame(
    adv_fn,
    isins: list[str],
    start: str = "2017-01-02",
    n_days: int = 420,
    listing: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Minimal (isin, date, adv_20) long frame — the only columns the mask reads.

    adv_fn(isin, ts) -> float gives the per-(isin, day) adv_20. `listing` optionally
    delays a name's first row (to exercise the minimum-age rule).
    """
    dates = pd.bdate_range(start, periods=n_days)
    listing = listing or {}
    rows = []
    for isin in isins:
        first = pd.Timestamp(listing[isin]) if isin in listing else None
        for ts in dates:
            if first is not None and ts < first:
                continue
            rows.append({"isin": isin, "date": ts, "adv_20": float(adv_fn(isin, ts))})
    return pd.DataFrame(rows)


def _full_frame(
    adv_by_isin: dict[str, float],
    start: str = "2017-01-02",
    n_days: int = 420,
    seed: int = 11,
) -> pd.DataFrame:
    """Full engine-column frame (for the precompute_v3_signals integration test)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    rows = []
    for isin, adv in adv_by_isin.items():
        price = 100.0
        for i, ts in enumerate(dates):
            price = max(price * (1.0 + rng.normal(0.0006, 0.015)), 0.01)
            rows.append(
                {
                    "isin": isin,
                    "symbol": isin,
                    "date": ts,
                    "open": price * 0.999,
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price,
                    "close_tr": price * 1.0005**i,
                    "volume": 100_000,
                    "adv_20": float(adv),
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# review_calendar
# ---------------------------------------------------------------------------


def test_review_anchors_resolve_to_last_trading_day_on_or_before():
    # A calendar that INCLUDES 2017-01-31 (Tue) but is MISSING 2017-07-31 (Mon).
    cal = pd.bdate_range("2017-01-02", periods=200)
    cal = pd.DatetimeIndex([d for d in cal if d != pd.Timestamp("2017-07-31")])
    reviews = _review_trading_days(cal, "semi-annual")
    assert pd.Timestamp("2017-01-31") in reviews  # anchor itself is a trading day
    # 2017-07-31 absent → resolves backward to the prior trading day (2017-07-28 Fri).
    assert pd.Timestamp("2017-07-31") not in reviews
    assert pd.Timestamp("2017-07-28") in reviews
    assert reviews == sorted(reviews)


def test_unsupported_cadence_fails_loud():
    cal = pd.bdate_range("2017-01-02", periods=50)
    try:
        _review_trading_days(cal, "monthly")
        raise AssertionError("expected ValueError for unsupported cadence")
    except ValueError as exc:
        assert "semi-annual" in str(exc)


# ---------------------------------------------------------------------------
# top_u
# ---------------------------------------------------------------------------


def test_top_u_entry_no_prior_members():
    # Constant, strictly-ordered liquidity A>B>C>D>E>F.
    adv = {"A": 6e7, "B": 5e7, "C": 4e7, "D": 3e7, "E": 2e7, "F": 1e7}
    frame = _adv_frame(lambda i, ts: adv[i], list(adv), n_days=40)
    mask = build_stable_universe_mask(
        frame, universe_size_U=3, universe_buffer_B=1.25, lookback_td=_LB
    )
    # First review = last trading day <= 2017-01-31.
    first_review = mask.review_dates[0]
    members = mask.members(first_review)
    assert members == frozenset({"A", "B", "C"})  # exactly top-3
    assert mask.is_member(first_review, "A")
    assert not mask.is_member(first_review, "D")


def test_members_empty_before_first_review():
    adv = {"A": 6e7, "B": 5e7}
    frame = _adv_frame(lambda i, ts: adv[i], list(adv), n_days=40)
    mask = build_stable_universe_mask(
        frame, universe_size_U=2, universe_buffer_B=1.25, lookback_td=_LB
    )
    assert mask.members("2017-01-03") == frozenset()  # before any review


# ---------------------------------------------------------------------------
# hysteresis (the load-bearing test)
# ---------------------------------------------------------------------------


def test_buffer_retains_within_band_and_drops_beyond():
    # U=2, B=2.0 -> band = 4. Enter on rank<=2; stay-in on rank<=4; drop on rank>4.
    # Phase 1 (<= 2017-06-30): A>B>C>D>E  -> review#1 (Jan) top-2 = {A, B}.
    # Phase 2 (>= 2017-07-01): C>D>A>E>B  -> review#2 (Jul) ranks C1 D2 A3 E4 B5.
    #   enter top-2 {C, D}; stay-in prev {A,B}: A rank3<=4 KEPT, B rank5>4 DROPPED.
    switch = pd.Timestamp("2017-07-01")
    p1 = {"A": 10e7, "B": 9e7, "C": 8e7, "D": 7e7, "E": 6e7}
    p2 = {"C": 10e7, "D": 9e7, "A": 8e7, "E": 7e7, "B": 6e7}

    def adv_fn(i, ts):
        return (p1 if ts < switch else p2)[i]

    frame = _adv_frame(adv_fn, list(p1), n_days=200)  # spans Jan + Jul reviews
    mask = build_stable_universe_mask(
        frame, universe_size_U=2, universe_buffer_B=2.0, lookback_td=_LB
    )

    jan, jul = mask.review_dates[0], mask.review_dates[1]
    assert mask.members(jan) == frozenset({"A", "B"})
    jul_members = mask.members(jul)
    assert "C" in jul_members and "D" in jul_members  # entered (top-2)
    assert "A" in jul_members  # rank 3 <= band 4 -> RETAINED by buffer
    assert "B" not in jul_members  # rank 5 > band 4 -> DROPPED
    assert jul_members == frozenset({"A", "C", "D"})


def test_hard_review_b_equals_one_has_no_buffer():
    # B=1.0 -> band == U: a name slipping out of the top-U is dropped immediately.
    switch = pd.Timestamp("2017-07-01")
    p1 = {"A": 10e7, "B": 9e7, "C": 8e7}
    p2 = {"B": 10e7, "C": 9e7, "A": 8e7}  # A falls to rank 3

    def adv_fn(i, ts):
        return (p1 if ts < switch else p2)[i]

    frame = _adv_frame(adv_fn, list(p1), n_days=200)
    mask = build_stable_universe_mask(
        frame, universe_size_U=2, universe_buffer_B=1.0, lookback_td=_LB
    )
    jul = mask.review_dates[1]
    # top-2 at Jul = {B, C}; A (rank3) gets no buffer -> dropped.
    assert mask.members(jul) == frozenset({"B", "C"})


# ---------------------------------------------------------------------------
# no_lookahead
# ---------------------------------------------------------------------------


def test_no_lookahead_future_adv_cannot_change_past_membership():
    adv = {"A": 6e7, "B": 5e7, "C": 4e7, "D": 3e7, "E": 2e7}
    frame = _adv_frame(lambda i, ts: adv[i], list(adv), n_days=200)
    base = build_stable_universe_mask(
        frame, universe_size_U=2, universe_buffer_B=1.25, lookback_td=_LB
    )
    jan, jul = base.review_dates[0], base.review_dates[1]

    # Corrupt adv_20 STRICTLY AFTER the Jan review: reverse the ordering wildly.
    corrupt = frame.copy()
    post = corrupt["date"] > jan
    rev = {"A": 1e7, "B": 2e7, "C": 3e7, "D": 4e7, "E": 99e7}
    corrupt.loc[post, "adv_20"] = corrupt.loc[post, "isin"].map(rev)
    after = build_stable_universe_mask(
        corrupt, universe_size_U=2, universe_buffer_B=1.25, lookback_td=_LB
    )

    # Jan membership (and everything at/just-before it) must be byte-identical.
    assert after.members(jan) == base.members(jan)
    assert after.members(jan - pd.Timedelta(days=1)) == base.members(
        jan - pd.Timedelta(days=1)
    )
    # And the corruption must be REAL — the later (Jul) review must differ, else
    # the test is vacuous.
    assert after.members(jul) != base.members(jul)


# ---------------------------------------------------------------------------
# min_age
# ---------------------------------------------------------------------------


def test_new_listing_not_eligible_until_full_lookback():
    # 'NEW' has the HIGHEST adv but lists only ~2 td before the Jan review — fewer
    # than _LB days of history, so its rank metric is NaN and it cannot enter.
    adv = {"A": 5e7, "B": 4e7, "C": 3e7, "NEW": 99e7}
    frame = _adv_frame(
        lambda i, ts: adv[i],
        list(adv),
        n_days=200,
        listing={"NEW": "2017-01-27"},  # ~2 trading days before 2017-01-31
    )
    mask = build_stable_universe_mask(
        frame, universe_size_U=2, universe_buffer_B=1.25, lookback_td=_LB
    )
    jan, jul = mask.review_dates[0], mask.review_dates[1]
    assert "NEW" not in mask.members(jan)  # too young at Jan review
    assert mask.members(jan) == frozenset({"A", "B"})
    assert "NEW" in mask.members(jul)  # has full lookback by Jul -> enters top-2


# ---------------------------------------------------------------------------
# floor_identity (integration with the signal store)
# ---------------------------------------------------------------------------


def test_floor_mode_applies_no_mask():
    frame = _full_frame({"A": 5e7, "B": 4e7, "C": 3e7})
    store = precompute_v3_signals(frame, V3Config())  # default == floor
    assert store._universe_mask is None


def test_stable_mode_builds_mask_and_restricts_eligibility():
    adv = {f"I{i:02d}": (50 - i) * 1e7 for i in range(10)}  # I00 most liquid
    frame = _full_frame(adv, n_days=420)
    cfg = V3Config(
        active_factors=["mom_12_1"],
        universe_mode="stable",
        universe_size_U=3,
        universe_buffer_B=1.25,
        universe_rank_lookback_td=_LB,
        use_regime_overlay=False,
    )
    store = precompute_v3_signals(frame, cfg)
    assert store._universe_mask is not None
    # On a warmed-up review day, only stable members can pass the gate.
    review = store._universe_mask.review_dates[-1]
    members = store._universe_mask.members(review)
    assert 0 < len(members) <= 3  # capped at U (plus buffer, but no churn here)
    non_member = next(i for i in adv if i not in members)
    assert store.entry_gate(review, non_member) is False


def test_mask_anded_into_gate_only_blocks_non_members():
    # Direct V3SignalStore construction: prove the mask is a pure AND — a member is
    # admitted exactly as floor mode would; a non-member is blocked.
    day = pd.Timestamp("2020-01-02")
    ind = {
        "MEM": pd.DataFrame(
            {
                "close": [110.0],
                "EMA_200": [100.0],
                "adv_20": [9e7],
                "momentum_12_1": [0.2],
            },
            index=pd.DatetimeIndex([day]),
        ),
        "OUT": pd.DataFrame(
            {
                "close": [110.0],
                "EMA_200": [100.0],
                "adv_20": [9e7],
                "momentum_12_1": [0.2],
            },
            index=pd.DatetimeIndex([day]),
        ),
    }
    composite = pd.DataFrame(
        {"MEM": [0.9], "OUT": [0.8]}, index=pd.DatetimeIndex([day])
    )
    cfg = V3Config(active_factors=["mom_12_1"])
    mask = StableUniverseMask([(day, frozenset({"MEM"}))])

    floor_store = V3SignalStore(ind, composite, cfg)  # no mask
    stable_store = V3SignalStore(ind, composite, cfg, universe_mask=mask)

    # Floor admits both (passes close>EMA, adv floor, mom>0).
    assert floor_store.entry_gate(day, "MEM") is True
    assert floor_store.entry_gate(day, "OUT") is True
    # Stable admits the member identically, blocks the non-member.
    assert stable_store.entry_gate(day, "MEM") is True
    assert stable_store.entry_gate(day, "OUT") is False
