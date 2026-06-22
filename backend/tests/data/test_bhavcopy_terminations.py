"""T07.1 — tests for terminated-no-successor sub-type classification.

All feeds are synthetic (CLAUDE.md §5: never touch live data). The tests encode
*why* each rule matters (Rule 9): a merger ghost must be force-exitable, an ingest
gap must NOT be mistaken for a delisting, an illiquid death is not S3-relevant.
"""

from __future__ import annotations

import pandas as pd

from app.data.bhavcopy import store, terminations

EDGE = pd.Timestamp("2025-01-31")
FLOOR = terminations.LIQUIDITY_FLOOR


def _rows(isin, symbol, dates, closes, adv, iid=None):
    iid = iid or isin
    return [
        {
            "isin": isin,
            "symbol": symbol,
            "date": pd.Timestamp(d),
            "close_raw": c,
            "adv_20": adv,
            "instrument_id": iid,
        }
        for d, c in zip(dates, closes)
    ]


def _prices():
    """One ISIN per sub-type, plus the three exclusion cases."""
    rows: list[dict] = []
    # alive at the edge — excluded (its chain still trades).
    rows += _rows(
        "INEALIVE0001", "ALIVE", ["2025-01-20", "2025-01-31"], [100, 110], 1e8
    )
    # curated merger ghost (HDFC) — value preserved, in KNOWN_FATES.
    rows += _rows("INE001A01036", "HDFC", ["2023-06-01", "2023-07-12"], [100, 91], 1e8)
    # DVR cancellation — value preserved, symbol suffix drives the label.
    rows += _rows(
        "INEDVR00001Z", "FOODVR", ["2024-01-01", "2024-06-01"], [100, 97], 1e8
    )
    # value-destroyed → delisting/insolvency.
    rows += _rows("INEINSOLV001", "GONE", ["2024-01-01", "2024-08-01"], [100, 10], 1e8)
    # value-preserved, isolated last_date → heuristic merger.
    rows += _rows("INEMERGE001", "TAKEN", ["2024-02-01", "2024-09-01"], [100, 90], 1e8)
    # five ISINs sharing one near-edge last_date → data-gap cluster (overrides the
    # value heuristic even though each is value-preserved).
    for i in range(5):
        rows += _rows(
            f"INEGAP0000{i}", f"GAP{i}", ["2025-01-02", "2025-01-05"], [100, 95], 1e8
        )
    # illiquid death (adv < floor) → excluded from the ghost-risk set.
    rows += _rows("INEILLIQ001", "TINY", ["2024-01-01", "2024-05-01"], [100, 95], 1e6)
    return pd.DataFrame(rows)


def _classify():
    return terminations.classify_terminations(
        _prices(), store._empty(store.SUCCESSOR_MAP_SCHEMA), edge=EDGE
    )


def test_subtype_partition():
    df = _classify().set_index("isin")
    # The four §3 buckets, by the right mechanism.
    assert df.loc["INE001A01036", "subtype"] == terminations.MERGER
    assert df.loc["INE001A01036", "confidence"] == "curated"
    assert df.loc["INE001A01036", "acquirer"] == "HDFCBANK"
    assert df.loc["INEDVR00001Z", "subtype"] == terminations.CANCELLATION
    assert df.loc["INEINSOLV001", "subtype"] == terminations.DELISTING_INSOLVENCY
    assert df.loc["INEMERGE001", "subtype"] == terminations.MERGER
    assert df.loc["INEMERGE001", "confidence"] == "heuristic"


def test_data_gap_cluster_overrides_value_heuristic():
    """A shared near-edge last_date is an ingest-gap fingerprint, NOT five
    simultaneous real delistings — must not leak into a real sub-type."""
    df = _classify().set_index("isin")
    gap = [f"INEGAP0000{i}" for i in range(5)]
    assert (df.loc[gap, "subtype"] == terminations.DATA_GAP_SUSPECT).all()
    assert (df.loc[gap, "cluster_size"] == 5).all()


def test_exclusions():
    """Alive-at-edge and illiquid-at-death are not ghost-risk and must be absent."""
    isins = set(_classify()["isin"])
    assert "INEALIVE0001" not in isins  # chain still trades at the edge
    assert "INEILLIQ001" not in isins  # adv < ₹5cr floor


def test_asserted_succession_old_leg_excluded():
    """06 stitches face-value successions; their old leg is not a 07 ghost."""
    prices = _prices()
    # Make the curated HDFC row an asserted old leg of a (synthetic) successor.
    sm = pd.DataFrame(
        [
            {
                "old_isin": "INE001A01036",
                "new_isin": "INE999Z01011",
                "transition_date": pd.Timestamp("2023-07-13"),
                "sig_consecutive": True,
                "sig_prefix": True,
                "sig_ca_split": False,
                "signals_matched": 2,
                "asserted": True,
                "root_isin": "INE001A01036",
                "liquid_old_leg": True,
            }
        ]
    )
    df = terminations.classify_terminations(prices, sm, edge=EDGE)
    assert "INE001A01036" not in set(df["isin"])


def test_store_round_trip(tmp_path):
    df = _classify()
    store.write_terminations(df, root=tmp_path)
    got = store.read_terminations(root=tmp_path)
    pd.testing.assert_frame_equal(
        got, store._conform(df, store.TERMINATIONS_SCHEMA, "terminations")
    )
    assert store.read_terminations(root=tmp_path / "nope").empty


def test_idempotent():
    """Re-classifying the same feed is byte-for-byte identical (read-only audit)."""
    pd.testing.assert_frame_equal(_classify(), _classify())
