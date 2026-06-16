"""
T1 — Canonical storage contract for the v2 bhavcopy data layer.

Storage layout decision
-----------------------
The three logical tables of `01_DATA_LAYER.md` §4 are persisted as Parquet under
a single root (default ``<CACHE_DIR or backend/data>/bhavcopy/``). Two access
patterns must both be fast (`01` §9):

  * "full history for ISIN X"  -> `prices_adjusted/` is an Apache Arrow dataset
    **partitioned by ``isin``**. A per-ISIN read touches exactly one partition;
    a date slice prunes further via row-group statistics.
  * "all ISINs tradeable on date D" -> `universe_membership/` is partitioned by
    **``year``** (derived from ``date``). Reading one date scans a single year
    partition. Year (not raw date) granularity avoids ~2,000 tiny per-day files
    over a multi-year build while keeping date scans cheap.

  * `isin_symbol_map.parquet` is a single small file (one row per ISIN).

We deliberately use partitioned Parquet rather than DuckDB: DuckDB is not a
project dependency, whereas ``pyarrow`` already is, and Arrow datasets give us
predicate pushdown + partition pruning with no extra service. Writes use
``existing_data_behavior="delete_matching"`` so re-running the build overwrites
the affected partitions instead of appending duplicates (CLAUDE.md Pipeline
Laws: idempotency).

This module is a thin, typed I/O layer only — schema enforcement and Parquet
round-trips. No business logic (adjustment, liquidity, universe rules) lives
here; those belong to T4–T6.
"""

import os
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as pa_ds
import pyarrow.parquet as pq

# --------------------------------------------------------------------------- #
# Schema constants (must match 01_DATA_LAYER.md §4 exactly)                    #
# --------------------------------------------------------------------------- #
# Each schema maps column name -> pandas dtype. Order is the canonical column
# order written to disk.

PRICES_ADJUSTED_SCHEMA: dict[str, str] = {
    "isin": "string",  # stable identity key (partition column)
    "symbol": "string",  # NSE symbol as of that date (may change for same ISIN)
    "date": "datetime64[ns]",  # trading date, IST calendar, UTC-naive
    "open": "float64",  # split/bonus-adjusted (signal prices)
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "close_raw": "float64",  # unadjusted close, retained for audit
    "close_tr": "float64",  # total-return adjusted close (P&L prices)
    "volume": "int64",  # shares traded
    "traded_value": "float64",  # ₹ turnover for the day
    "adv_20": "float64",  # 20-day rolling median of traded_value
    "adj_factor": "float64",  # cumulative split/bonus back-adjustment factor
    "tr_factor": "float64",  # cumulative split+bonus+dividend factor
    "series": "string",  # EQ (scope per T0 decision)
}

UNIVERSE_MEMBERSHIP_SCHEMA: dict[str, str] = {
    "isin": "string",
    "date": "datetime64[ns]",
}

ISIN_SYMBOL_MAP_SCHEMA: dict[str, str] = {
    "isin": "string",
    "symbol": "string",
    "first_date": "datetime64[ns]",
    "last_date": "datetime64[ns]",
}

# Audit trail for CA events fetched during build (05_DATA_ADJUSTMENT_REMEDIATION §11.2).
# Schema mirrors corporate_actions.CA_EVENT_COLUMNS exactly.
CORPORATE_ACTIONS_SCHEMA: dict[str, str] = {
    "isin": "string",
    "symbol": "string",
    "ex_date": "datetime64[ns]",
    "type": "string",
    "ratio": "float64",
    "dividend": "float64",
    "subject": "string",
}

# Unmatched CA records that could not be classified or parsed.
# Schema mirrors corporate_actions.CA_UNMATCHED_COLUMNS exactly.
CA_UNMATCHED_SCHEMA: dict[str, str] = {
    "isin": "string",
    "symbol": "string",
    "ex_date_raw": "string",
    "subject": "string",
    "reason": "string",
}

# Subdir / file names under the storage root.
_PRICES_DIR = "prices_adjusted"
_MEMBERSHIP_DIR = "universe_membership"
_ISIN_MAP_FILE = "isin_symbol_map.parquet"
_CA_EVENTS_FILE = "corporate_actions.parquet"
_CA_UNMATCHED_FILE = "ca_unmatched.parquet"

# Partition columns.
_PRICES_PARTITION = "isin"
_MEMBERSHIP_PARTITION = "year"  # derived from date; not part of the logical schema


# --------------------------------------------------------------------------- #
# Paths                                                                        #
# --------------------------------------------------------------------------- #
def default_root() -> Path:
    """Storage root: ``<CACHE_DIR or backend/data>/bhavcopy/``.

    Mirrors ``OHLCVCache``'s base-dir convention so all v2 batch artifacts live
    under one ``data/`` tree.
    """
    base = os.environ.get(
        "CACHE_DIR",
        str(Path(__file__).resolve().parents[3] / "data"),
    )
    return Path(base) / "bhavcopy"


def _root(root: str | Path | None) -> Path:
    return Path(root) if root is not None else default_root()


# --------------------------------------------------------------------------- #
# Schema enforcement                                                           #
# --------------------------------------------------------------------------- #
def _conform(df: pd.DataFrame, schema: dict[str, str], table: str) -> pd.DataFrame:
    """Validate that ``df`` has exactly the schema's columns and coerce dtypes.

    Fails loud (CLAUDE.md Rule 12) on any missing column. Extra columns are an
    error too — the contract is exact.
    """
    missing = [c for c in schema if c not in df.columns]
    if missing:
        raise ValueError(f"{table}: missing required columns {missing}")
    extra = [c for c in df.columns if c not in schema]
    if extra:
        raise ValueError(f"{table}: unexpected columns {extra}")

    out = df.loc[:, list(schema)].copy()
    for col, dtype in schema.items():
        if dtype.startswith("datetime64"):
            # Coerce to UTC-naive datetime (drop tz if present).
            s = pd.to_datetime(out[col])
            if getattr(s.dtype, "tz", None) is not None:
                s = s.dt.tz_localize(None)
            out[col] = s.astype("datetime64[ns]")
        else:
            out[col] = out[col].astype(dtype)
    return out


def _empty(schema: dict[str, str]) -> pd.DataFrame:
    return _conform(pd.DataFrame({c: [] for c in schema}), schema, "empty")


# --------------------------------------------------------------------------- #
# Partitioned dataset I/O helpers                                             #
# --------------------------------------------------------------------------- #
def _write_dataset(df: pd.DataFrame, path: Path, partition_cols: list[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_to_dataset(
        table,
        root_path=str(path),
        partition_cols=partition_cols,
        existing_data_behavior="delete_matching",
    )


def _read_dataset(
    path: Path,
    schema: dict[str, str],
    pa_filter: pa_ds.Expression | None,
) -> pd.DataFrame:
    if not path.exists() or not any(path.iterdir()):
        return _empty(schema)
    dataset = pa_ds.dataset(str(path), format="parquet", partitioning="hive")
    table = dataset.to_table(filter=pa_filter)
    df = table.to_pandas()
    return _conform(df, schema, path.name)


# --------------------------------------------------------------------------- #
# prices_adjusted                                                             #
# --------------------------------------------------------------------------- #
def write_prices_adjusted(df: pd.DataFrame, root: str | Path | None = None) -> None:
    df = _conform(df, PRICES_ADJUSTED_SCHEMA, "prices_adjusted")
    _write_dataset(df, _root(root) / _PRICES_DIR, [_PRICES_PARTITION])


def read_prices_adjusted(
    root: str | Path | None = None,
    isins: list[str] | None = None,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Read adjusted prices, optionally filtered by ISIN list and date range.

    ``isins`` prunes by partition; ``start``/``end`` (inclusive) push down on the
    ``date`` column.
    """
    expr = None
    if isins is not None:
        expr = pa_ds.field("isin").isin(list(isins))
    if start is not None:
        e = pa_ds.field("date") >= pa.scalar(pd.Timestamp(start))
        expr = e if expr is None else expr & e
    if end is not None:
        e = pa_ds.field("date") <= pa.scalar(pd.Timestamp(end))
        expr = e if expr is None else expr & e
    return _read_dataset(_root(root) / _PRICES_DIR, PRICES_ADJUSTED_SCHEMA, expr)


# --------------------------------------------------------------------------- #
# universe_membership                                                         #
# --------------------------------------------------------------------------- #
def write_universe_membership(df: pd.DataFrame, root: str | Path | None = None) -> None:
    df = _conform(df, UNIVERSE_MEMBERSHIP_SCHEMA, "universe_membership")
    # Derive the year partition; dropped again on read so it never leaks into
    # the logical schema.
    df = df.assign(year=df["date"].dt.year.astype("int32"))
    _write_dataset(df, _root(root) / _MEMBERSHIP_DIR, [_MEMBERSHIP_PARTITION])


def read_universe_membership(
    root: str | Path | None = None,
    date: str | pd.Timestamp | None = None,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Read point-in-time membership. ``date`` selects one trading day; ``start``
    /``end`` (inclusive) select a range. A year-partition filter is derived so
    only the needed partitions are scanned."""
    path = _root(root) / _MEMBERSHIP_DIR
    if not path.exists() or not any(path.iterdir()):
        return _empty(UNIVERSE_MEMBERSHIP_SCHEMA)

    expr = None
    years: set[int] = set()
    if date is not None:
        d = pd.Timestamp(date)
        expr = pa_ds.field("date") == pa.scalar(d)
        years.add(d.year)
    if start is not None:
        s = pd.Timestamp(start)
        e = pa_ds.field("date") >= pa.scalar(s)
        expr = e if expr is None else expr & e
    if end is not None:
        en = pd.Timestamp(end)
        e = pa_ds.field("date") <= pa.scalar(en)
        expr = e if expr is None else expr & e
    if start is not None and end is not None:
        years.update(range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1))

    if years:
        yexpr = pa_ds.field(_MEMBERSHIP_PARTITION).isin(sorted(years))
        expr = yexpr if expr is None else expr & yexpr

    dataset = pa_ds.dataset(str(path), format="parquet", partitioning="hive")
    df = dataset.to_table(filter=expr).to_pandas()
    df = df.drop(columns=[_MEMBERSHIP_PARTITION], errors="ignore")
    return _conform(df, UNIVERSE_MEMBERSHIP_SCHEMA, "universe_membership")


# --------------------------------------------------------------------------- #
# isin_symbol_map                                                             #
# --------------------------------------------------------------------------- #
def write_isin_symbol_map(df: pd.DataFrame, root: str | Path | None = None) -> None:
    df = _conform(df, ISIN_SYMBOL_MAP_SCHEMA, "isin_symbol_map")
    path = _root(root)
    path.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path / _ISIN_MAP_FILE, index=False)


def read_isin_symbol_map(
    root: str | Path | None = None,
    isins: list[str] | None = None,
) -> pd.DataFrame:
    path = _root(root) / _ISIN_MAP_FILE
    if not path.exists():
        return _empty(ISIN_SYMBOL_MAP_SCHEMA)
    df = pd.read_parquet(path)
    df = _conform(df, ISIN_SYMBOL_MAP_SCHEMA, "isin_symbol_map")
    if isins is not None:
        df = df[df["isin"].isin(list(isins))].reset_index(drop=True)
    return df


# --------------------------------------------------------------------------- #
# corporate_actions (CA events audit trail)                                   #
# --------------------------------------------------------------------------- #
def write_corporate_actions(df: pd.DataFrame, root: str | Path | None = None) -> None:
    df = _conform(df, CORPORATE_ACTIONS_SCHEMA, "corporate_actions")
    path = _root(root)
    path.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path / _CA_EVENTS_FILE, index=False)


def read_corporate_actions(root: str | Path | None = None) -> pd.DataFrame:
    path = _root(root) / _CA_EVENTS_FILE
    if not path.exists():
        return _empty(CORPORATE_ACTIONS_SCHEMA)
    df = pd.read_parquet(path)
    return _conform(df, CORPORATE_ACTIONS_SCHEMA, "corporate_actions")


def write_ca_unmatched(df: pd.DataFrame, root: str | Path | None = None) -> None:
    df = _conform(df, CA_UNMATCHED_SCHEMA, "ca_unmatched")
    path = _root(root)
    path.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path / _CA_UNMATCHED_FILE, index=False)


def read_ca_unmatched(root: str | Path | None = None) -> pd.DataFrame:
    path = _root(root) / _CA_UNMATCHED_FILE
    if not path.exists():
        return _empty(CA_UNMATCHED_SCHEMA)
    df = pd.read_parquet(path)
    return _conform(df, CA_UNMATCHED_SCHEMA, "ca_unmatched")
