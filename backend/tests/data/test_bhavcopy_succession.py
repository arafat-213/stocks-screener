"""T06.1 — ISIN-succession map builder tests.

Offline only — synthetic lifetime + CA frames, a tmp store root, no network
(CLAUDE.md Rule 4/5). These tests encode *why* the map matters (Rule 9): a
momentum book must not (a) treat a face-value-split re-issue as a brand-new name
nor (b) carry an unsellable ghost — so a link is asserted only on >=2 converging
signals, multi-hop chains collapse to one root, and a legit termination (merger /
DVR cancel, no successor) must NOT be asserted.
"""

import numpy as np
import pandas as pd

from app.data.bhavcopy import store, succession
from app.data.bhavcopy.corporate_actions import CA_EVENT_COLUMNS

# A dense daily calendar is fine for the consecutive-day signal in tests.
_CAL = np.array(
    pd.date_range("2020-01-01", "2022-12-31", freq="D").values, dtype="datetime64[ns]"
)


def _life(isin: str, symbol: str, first: str, last: str) -> dict:
    return {
        "isin": isin,
        "symbol": symbol,
        "first_date": pd.Timestamp(first),
        "last_date": pd.Timestamp(last),
    }


def _ca_split(isin: str, symbol: str, ex_date: str) -> dict:
    return {
        "isin": isin,
        "symbol": symbol,
        "ex_date": pd.Timestamp(ex_date),
        "type": "split",
        "ratio": 0.2,
        "dividend": np.nan,
        "subject": "Face Value Split From Rs 10/- To Rs 2/-",
    }


def _empty_ca() -> pd.DataFrame:
    return pd.DataFrame(columns=CA_EVENT_COLUMNS)


# --------------------------------------------------------------------------- #
# Signal gating                                                                #
# --------------------------------------------------------------------------- #
def test_two_signals_assert_one_signal_does_not():
    """consecutive + prefix-increment ⇒ asserted; prefix-only (a gap kills the
    consecutive signal) ⇒ 1 signal ⇒ unmatched, not asserted."""
    lifetimes = pd.DataFrame(
        [
            # AAA: consecutive handover + incrementing suffix → 2 signals.
            _life("INE100A01011", "AAA", "2020-01-02", "2020-06-01"),
            _life("INE100A01029", "AAA", "2020-06-02", "2020-12-31"),
            # DDD: incrementing suffix but a multi-week gap → only prefix fires.
            _life("INE400A01010", "DDD", "2020-01-02", "2020-06-01"),
            _life("INE400A01028", "DDD", "2020-08-01", "2020-12-31"),
        ]
    )
    m, um = succession.build_successor_map(lifetimes, _empty_ca(), _CAL)

    aaa = m[m["old_isin"] == "INE100A01011"].iloc[0]
    assert aaa["sig_consecutive"] and aaa["sig_prefix"]
    assert aaa["signals_matched"] == 2 and aaa["asserted"]

    ddd = m[m["old_isin"] == "INE400A01010"].iloc[0]
    assert ddd["sig_prefix"] and not ddd["sig_consecutive"]
    assert ddd["signals_matched"] == 1 and not ddd["asserted"]
    # The single-signal candidate is surfaced for triage, not silently dropped.
    assert "INE400A01010" in set(um["old_isin"])
    assert um[um["old_isin"] == "INE400A01010"].iloc[0]["reason"].startswith("only 1")


def test_ca_split_is_the_second_signal_when_prefix_differs():
    """A re-issue under an unrelated prefix still asserts when the consecutive
    handover coincides with a face-value-split CA filed under the old ISIN."""
    lifetimes = pd.DataFrame(
        [
            _life("INE500A01017", "EEE", "2020-01-02", "2020-06-01"),
            _life("INE999Z01099", "EEE", "2020-06-02", "2020-12-31"),
        ]
    )
    ca = pd.DataFrame([_ca_split("INE500A01017", "EEE", "2020-06-02")])
    m, _ = succession.build_successor_map(lifetimes, ca, _CAL)
    row = m.iloc[0]
    assert row["sig_consecutive"] and not row["sig_prefix"] and row["sig_ca_split"]
    assert row["signals_matched"] == 2 and row["asserted"]


# --------------------------------------------------------------------------- #
# Chain collapse                                                               #
# --------------------------------------------------------------------------- #
def test_multihop_chain_collapses_to_oldest_root():
    """A→B→C (two consecutive face-value splits) ⇒ both edges asserted and every
    leg resolves to the oldest ISIN as root (so T06.2's instrument_id is stable)."""
    lifetimes = pd.DataFrame(
        [
            _life("INE100A01011", "AAA", "2020-01-02", "2020-06-01"),
            _life("INE100A01029", "AAA", "2020-06-02", "2021-06-01"),
            _life("INE100A01037", "AAA", "2021-06-02", "2021-12-31"),
        ]
    )
    m, _ = succession.build_successor_map(lifetimes, _empty_ca(), _CAL)
    assert m["asserted"].all()
    assert set(m["root_isin"]) == {"INE100A01011"}  # the oldest leg


# --------------------------------------------------------------------------- #
# Legit terminations must NOT be asserted                                      #
# --------------------------------------------------------------------------- #
def test_merger_or_cancellation_has_no_pair():
    """A name that simply ends (merger / DVR cancel) has a single ISIN ⇒ no
    candidate pair at all ⇒ never asserted (the HDFC / TATAMTRDVR §2 cases)."""
    lifetimes = pd.DataFrame(
        [
            _life("INE001A01036", "HDFC", "2017-01-02", "2023-07-12"),
            _life("IN9155A01020", "TATAMTRDVR", "2017-01-02", "2021-08-29"),
        ]
    )
    m, um = succession.build_successor_map(lifetimes, _empty_ca(), _CAL)
    assert m.empty and um.empty


# --------------------------------------------------------------------------- #
# Conflict guard                                                               #
# --------------------------------------------------------------------------- #
def test_fork_is_demoted_to_unmatched():
    """Two old legs that both claim the same successor (a fork) are ambiguous —
    both are demoted to unmatched with a conflict reason rather than guessed."""
    shared = "INE100A01029"
    lifetimes = pd.DataFrame(
        [
            # F1 → SHARED via consecutive + prefix-increment.
            _life("INE100A01011", "FORKA", "2020-01-02", "2020-06-01"),
            _life(shared, "FORKA", "2020-06-02", "2020-12-31"),
            # F2 → SHARED via consecutive + CA split (prefix differs).
            _life("INE300A01016", "FORKB", "2020-01-02", "2020-06-01"),
            _life(shared, "FORKB", "2020-06-02", "2020-12-31"),
        ]
    )
    ca = pd.DataFrame([_ca_split("INE300A01016", "FORKB", "2020-06-02")])
    m, um = succession.build_successor_map(lifetimes, ca, _CAL)
    # Both edges had >=2 raw signals but neither survives the conflict guard.
    assert not m[m["new_isin"] == shared]["asserted"].any()
    reasons = set(um[um["new_isin"] == shared]["reason"])
    assert reasons == {"conflict: ambiguous successor (fork)"}


# --------------------------------------------------------------------------- #
# Liquidity (ghost-risk) flag                                                  #
# --------------------------------------------------------------------------- #
def test_liquid_old_leg_flag_uses_adv_threshold():
    lifetimes = pd.DataFrame(
        [
            _life("INE100A01011", "AAA", "2020-01-02", "2020-06-01"),
            _life("INE100A01029", "AAA", "2020-06-02", "2020-12-31"),
        ]
    )
    # Above the ₹5cr S3 gate → ghost-risk.
    m, _ = succession.build_successor_map(
        lifetimes, _empty_ca(), _CAL, {"INE100A01011": 6e7}
    )
    assert bool(m.iloc[0]["liquid_old_leg"])
    # Below the gate → not flagged.
    m2, _ = succession.build_successor_map(
        lifetimes, _empty_ca(), _CAL, {"INE100A01011": 1e7}
    )
    assert not bool(m2.iloc[0]["liquid_old_leg"])


# --------------------------------------------------------------------------- #
# Store round-trip + idempotent wrapper                                        #
# --------------------------------------------------------------------------- #
def test_store_roundtrip(tmp_path):
    m = pd.DataFrame(
        [
            {
                "old_isin": "INE100A01011",
                "new_isin": "INE100A01029",
                "transition_date": pd.Timestamp("2020-06-02"),
                "sig_consecutive": True,
                "sig_prefix": True,
                "sig_ca_split": False,
                "signals_matched": 2,
                "asserted": True,
                "root_isin": "INE100A01011",
                "liquid_old_leg": True,
            }
        ]
    )
    store.write_successor_map(m, root=tmp_path)
    got = store.read_successor_map(root=tmp_path)
    pd.testing.assert_frame_equal(
        got, store._conform(m, store.SUCCESSOR_MAP_SCHEMA, "successor_map")
    )
    # Empty read on a fresh root returns the typed empty frame.
    assert store.read_successor_unmatched(root=tmp_path / "nope").empty


def test_run_build_is_idempotent(tmp_path):
    """Wrapper reads the store, persists both artifacts, and a re-run produces a
    byte-for-byte identical map (no duplicate rows)."""
    lifetimes = pd.DataFrame(
        [
            _life("INE100A01011", "AAA", "2020-01-02", "2020-06-01"),
            _life("INE100A01029", "AAA", "2020-06-02", "2020-12-31"),
        ]
    )
    # isin_symbol_map now carries instrument_id (T06.2); succession build does not
    # consume it (it keys on isin), but the store writer enforces the column.
    lifetimes = lifetimes.assign(instrument_id=lifetimes["isin"])
    store.write_isin_symbol_map(lifetimes, root=tmp_path)
    store.write_corporate_actions(
        pd.DataFrame(columns=store.CORPORATE_ACTIONS_SCHEMA.keys()).astype(
            {"ex_date": "datetime64[ns]"}
        ),
        root=tmp_path,
    )
    # Minimal membership (trading calendar) + prices (adv lookup).
    mem = pd.DataFrame(
        {"isin": "INE100A01011", "date": pd.to_datetime(["2020-06-01", "2020-06-02"])}
    )
    store.write_universe_membership(mem, root=tmp_path)
    prices = pd.DataFrame(
        [
            {
                "isin": "INE100A01011",
                "symbol": "AAA",
                "date": pd.Timestamp("2020-06-01"),
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "close_raw": 1.0,
                "close_tr": 1.0,
                "volume": 1,
                "traded_value": 1.0,
                "adv_20": 6e7,
                "adj_factor": 1.0,
                "tr_factor": 1.0,
                "series": "EQ",
                "instrument_id": "INE100A01011",
            }
        ]
    )
    store.write_prices_adjusted(prices, root=tmp_path)

    m1, _ = succession.run_succession_build(root=str(tmp_path))
    m2, _ = succession.run_succession_build(root=str(tmp_path))
    assert len(m1) == 1 and m1.iloc[0]["asserted"]
    assert bool(m1.iloc[0]["liquid_old_leg"])  # adv 6e7 ≥ 5cr from the store
    pd.testing.assert_frame_equal(
        store.read_successor_map(root=tmp_path),
        store.read_successor_map(root=tmp_path),
    )
    pd.testing.assert_frame_equal(m1, m2)
