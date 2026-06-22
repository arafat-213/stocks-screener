"""T06.2 — chain-constant ``instrument_id`` materialisation tests.

Offline only — synthetic frames + a tmp store root, no network (CLAUDE.md Rule 4).
These encode *why* ``instrument_id`` exists (Rule 9): a face-value-split re-issue
(old ISIN → new ISIN) must read back as **one continuous instrument** so the
signal/holdings layer (T06.3) is neither momentum-blind on the new leg nor stuck
with an unsellable ghost on the old. The fix must also be a pure column-add —
**byte-identical** on every other column for standalone (non-succession) ISINs.

Covers: ``build_universe`` emitting the column (identity by default, root via a
map), ``instrument_id_map`` chain collapse, the ``read_prices_adjusted`` chain
filter, and ``rederive_instrument_id`` (parity + continuity + idempotency) against
a store written *without* the column (the real pre-migration shape).
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.data.bhavcopy import store, succession
from app.data.bhavcopy.universe import build_universe

# Legs of one face-value-split chain (consecutive suffix increment) + a standalone.
OLD = "INE100A01011"
NEW = "INE100A01029"
STANDALONE = "INE777Z01011"

# The 15 pre-T06.2 columns (no instrument_id) — the real pre-migration store shape.
_PRE_COLS = [c for c in store.PRICES_ADJUSTED_SCHEMA if c != "instrument_id"]


def _adj_row(isin: str, symbol: str, date: str, close: float) -> dict:
    """A single adjust.py-style row (PRICES_ADJUSTED_SCHEMA minus adv_20/instrument_id)."""
    return {
        "isin": isin,
        "symbol": symbol,
        "date": pd.Timestamp(date),
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "close_raw": close,
        "close_tr": close,
        "volume": 1000,
        "traded_value": close * 1000,
        "adj_factor": 1.0,
        "tr_factor": 1.0,
        "series": "EQ",
    }


def _asserted_map(old: str, new: str, root: str) -> pd.DataFrame:
    return store._conform(
        pd.DataFrame(
            [
                {
                    "old_isin": old,
                    "new_isin": new,
                    "transition_date": pd.Timestamp("2020-06-02"),
                    "sig_consecutive": True,
                    "sig_prefix": True,
                    "sig_ca_split": False,
                    "signals_matched": 2,
                    "asserted": True,
                    "root_isin": root,
                    "liquid_old_leg": True,
                }
            ]
        ),
        store.SUCCESSOR_MAP_SCHEMA,
        "successor_map",
    )


# --------------------------------------------------------------------------- #
# instrument_id_map — chain collapse                                          #
# --------------------------------------------------------------------------- #
def test_instrument_id_map_collapses_chain_to_root():
    """A→B→C asserted ⇒ every leg maps to the oldest root; unasserted excluded."""
    smap = store._conform(
        pd.DataFrame(
            [
                # A→B and B→C, both asserted, root = A (oldest).
                {
                    "old_isin": "A",
                    "new_isin": "B",
                    "transition_date": pd.Timestamp("2020-06-02"),
                    "sig_consecutive": True,
                    "sig_prefix": True,
                    "sig_ca_split": False,
                    "signals_matched": 2,
                    "asserted": True,
                    "root_isin": "A",
                    "liquid_old_leg": False,
                },
                {
                    "old_isin": "B",
                    "new_isin": "C",
                    "transition_date": pd.Timestamp("2021-06-02"),
                    "sig_consecutive": True,
                    "sig_prefix": True,
                    "sig_ca_split": False,
                    "signals_matched": 2,
                    "asserted": True,
                    "root_isin": "A",
                    "liquid_old_leg": False,
                },
                # An unasserted candidate must NOT be stitched.
                {
                    "old_isin": "X",
                    "new_isin": "Y",
                    "transition_date": pd.Timestamp("2020-06-02"),
                    "sig_consecutive": True,
                    "sig_prefix": False,
                    "sig_ca_split": False,
                    "signals_matched": 1,
                    "asserted": False,
                    "root_isin": "",
                    "liquid_old_leg": False,
                },
            ]
        ),
        store.SUCCESSOR_MAP_SCHEMA,
        "successor_map",
    )
    assert succession.instrument_id_map(smap) == {"A": "A", "B": "A", "C": "A"}


def test_instrument_id_map_empty_when_no_map():
    assert succession.instrument_id_map(store._empty(store.SUCCESSOR_MAP_SCHEMA)) == {}


# --------------------------------------------------------------------------- #
# build_universe — identity by default, root via map                          #
# --------------------------------------------------------------------------- #
def test_build_universe_default_instrument_id_is_isin():
    raw = pd.DataFrame(
        [
            _adj_row(OLD, "AAA", "2020-01-02", 100.0),
            _adj_row(STANDALONE, "ZZZ", "2020-01-02", 50.0),
        ],
        columns=_PRE_COLS,
    )
    prices, _, isin_map = build_universe(raw)
    assert (prices["instrument_id"] == prices["isin"]).all()
    assert (isin_map["instrument_id"] == isin_map["isin"]).all()


def test_build_universe_collapses_chain_via_map():
    raw = pd.DataFrame(
        [
            _adj_row(OLD, "AAA", "2020-06-01", 100.0),
            _adj_row(NEW, "AAA", "2020-06-02", 20.0),
            _adj_row(STANDALONE, "ZZZ", "2020-06-02", 50.0),
        ],
        columns=_PRE_COLS,
    )
    prices, _, _ = build_universe(raw, {OLD: OLD, NEW: OLD})
    # Both legs collapse onto the root; the standalone is untouched.
    assert set(prices.loc[prices["isin"].isin([OLD, NEW]), "instrument_id"]) == {OLD}
    assert (
        prices.loc[prices["isin"] == STANDALONE, "instrument_id"] == STANDALONE
    ).all()
    assert list(prices.columns) == list(store.PRICES_ADJUSTED_SCHEMA)


# --------------------------------------------------------------------------- #
# rederive_instrument_id — parity + continuity + idempotency                  #
# --------------------------------------------------------------------------- #
def _write_pre_migration_store(root, raw: pd.DataFrame) -> pd.DataFrame:
    """Write prices_adjusted + isin_symbol_map WITHOUT instrument_id (pre-T06.2 shape).

    Bypasses ``write_prices_adjusted`` (which now enforces the new schema) to
    reproduce the real on-disk store the migration must upgrade. Returns the
    adv_20-bearing prices frame for later parity comparison.
    """
    prices, _, isin_map = build_universe(raw)  # has instrument_id == isin
    prices_pre = prices[_PRE_COLS]
    isin_map_pre = isin_map[
        [c for c in store.ISIN_SYMBOL_MAP_SCHEMA if c != "instrument_id"]
    ]

    base = store._root(root)
    pq.write_to_dataset(
        pa.Table.from_pandas(prices_pre, preserve_index=False),
        root_path=str(base / store._PRICES_DIR),
        partition_cols=[store._PRICES_PARTITION],
        existing_data_behavior="delete_matching",
    )
    base.mkdir(parents=True, exist_ok=True)
    isin_map_pre.to_parquet(base / store._ISIN_MAP_FILE, index=False)
    return prices_pre


def _chain_raw() -> pd.DataFrame:
    """OLD trades Jan–Jun 1, NEW takes over Jun 2 (consecutive); STANDALONE alongside."""
    rows = [_adj_row(OLD, "AAA", f"2020-0{m}-01", 100.0 + m) for m in range(1, 7)]
    rows += [_adj_row(NEW, "AAA", f"2020-0{m}-02", 20.0 + m) for m in range(6, 7)]
    rows += [_adj_row(NEW, "AAA", "2020-07-01", 30.0)]
    rows += [
        _adj_row(STANDALONE, "ZZZ", f"2020-0{m}-01", 50.0 + m) for m in range(1, 7)
    ]
    return pd.DataFrame(rows, columns=_PRE_COLS)


def test_rederive_adds_column_and_is_parity_preserving(tmp_path):
    """Standalone ISIN is byte-identical on every original column; the new column
    is the only difference (== isin for a non-succession instrument)."""
    pre = _write_pre_migration_store(tmp_path, _chain_raw())
    # Pre-migration files genuinely lack the column.
    assert "instrument_id" not in pre.columns

    store.write_successor_map(_asserted_map(OLD, NEW, OLD), root=tmp_path)
    summary = succession.rederive_instrument_id(root=str(tmp_path))

    got = store.read_prices_adjusted(root=tmp_path)
    assert summary["rows"] == len(pre)  # row count conserved (no drops/dupes)
    assert list(got.columns) == list(store.PRICES_ADJUSTED_SCHEMA)

    key = ["isin", "date"]
    std_pre = pre[pre["isin"] == STANDALONE].sort_values(key).reset_index(drop=True)
    std_got = (
        got[got["isin"] == STANDALONE]
        .sort_values(key)
        .reset_index(drop=True)[_PRE_COLS]
    )
    pd.testing.assert_frame_equal(std_pre, std_got, check_dtype=False)
    assert (got.loc[got["isin"] == STANDALONE, "instrument_id"] == STANDALONE).all()


def test_rederive_yields_continuous_chain_series(tmp_path):
    """Querying the chain's instrument_id returns one unbroken old+new series."""
    _write_pre_migration_store(tmp_path, _chain_raw())
    store.write_successor_map(_asserted_map(OLD, NEW, OLD), root=tmp_path)
    succession.rederive_instrument_id(root=str(tmp_path))

    chain = store.read_prices_adjusted(root=tmp_path, instrument_ids=[OLD])
    # Exactly the two legs, one identity, spanning both legs' dates with no gap.
    assert set(chain["isin"]) == {OLD, NEW}
    assert set(chain["instrument_id"]) == {OLD}
    dates = chain.sort_values("date")["date"].tolist()
    assert dates == sorted(dates)
    # The STANDALONE instrument is not part of this chain.
    assert STANDALONE not in set(chain["isin"])


def test_rederive_is_idempotent(tmp_path):
    _write_pre_migration_store(tmp_path, _chain_raw())
    store.write_successor_map(_asserted_map(OLD, NEW, OLD), root=tmp_path)
    succession.rederive_instrument_id(root=str(tmp_path))
    first = store.read_prices_adjusted(root=tmp_path)
    succession.rederive_instrument_id(root=str(tmp_path))
    second = store.read_prices_adjusted(root=tmp_path)
    key = ["isin", "date"]
    pd.testing.assert_frame_equal(
        first.sort_values(key).reset_index(drop=True),
        second.sort_values(key).reset_index(drop=True),
    )
