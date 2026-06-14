"""T3 — Parse layer: parse legacy + UDiFF day files into the unified raw row
schema.

Accepts a downloaded .zip bhavcopy file (from T2's cache) and emits a
DataFrame with the unified raw row schema consumed by every downstream stage:

    (isin, symbol, date, open, high, low, close, volume, traded_value, series)

Two parsers handle the two NSE formats (T0 findings, 01_DATA_LAYER.md §1–§2):

  * Legacy CM bhavcopy (trading dates < 2024-07-08):
    Columns (13+trailing comma): SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, LAST,
      PREVCLOSE, TOTTRDQTY, TOTTRDVAL, TIMESTAMP, TOTALTRADES, ISIN
    TOTTRDVAL is ₹ turnover → traded_value.
    TIMESTAMP format: "04-JUL-2024" (dd-MMM-yyyy).

  * UDiFF CM bhavcopy (trading dates >= 2024-07-08):
    Columns (34): TradDt, BizDt, Sgmt, Src, FinInstrmTp, FinInstrmId, ISIN,
      TckrSymb, SctySrs, XpryDt, FininstrmActlXpryDt, StrkPric, OptnTp,
      FinInstrmNm, OpnPric, HghPric, LwPric, ClsPric, LastPric, PrvsClsgPric,
      UndrlygPric, SttlmPric, OpnIntrst, ChngInOpnIntrst, TtlTradgVol,
      TtlTrfVal, TtlNbOfTxsExctd, SsnId, NewBrdLotQty, Rmks, Rsvd1-4
    Equity filter: FinInstrmTp == STK, XpryDt empty/NaN (not F&O/warrants).
    TtlTrfVal is ₹ turnover → traded_value.
    TradDt format: "2024-07-25" (ISO 8601).

Policy (01_DATA_LAYER.md §7, T0 decision):
  * IN_SCOPE_SERIES = {"EQ"} — BE and other series are excluded from the
    returned DataFrame. Non-EQ rows are parsed but not retained.
  * Suspended/zero-price rows are dropped (OPEN and CLOSE both > 0 required).
  * ISIN is present on every retained row — it is the join key downstream.
  * traded_value is sourced directly from the bhavcopy for both formats; it is
    always present for in-scope rows. A null is left as-is for downstream to
    fall back on close_raw × volume (01 §4), but this should not occur in
    practice.
"""

import io
import logging
import zipfile
from pathlib import Path

import pandas as pd

from app.data.bhavcopy.download import FMT_LEGACY, FMT_UDIFF

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Schema + policy constants                                                     #
# --------------------------------------------------------------------------- #
UNIFIED_RAW_COLUMNS: list[str] = [
    "isin",
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "traded_value",
    "series",
]

# T0 §7 policy: EQ only for the momentum universe.
IN_SCOPE_SERIES: frozenset[str] = frozenset({"EQ"})

# UDiFF XpryDt values that indicate no expiry (equity spot row).
_UDIFF_NO_EXPIRY: frozenset[str] = frozenset({"", "nan", "-"})


# --------------------------------------------------------------------------- #
# Public API                                                                    #
# --------------------------------------------------------------------------- #
def parse_file(path: str | Path, fmt: str) -> pd.DataFrame:
    """Parse a downloaded .zip bhavcopy file → unified raw row DataFrame.

    The ZIP is expected to contain exactly one CSV (the NSE convention). ``fmt``
    must be ``'legacy'`` or ``'udiff'`` (constants from ``download.py``).

    Returns a DataFrame with columns matching ``UNIFIED_RAW_COLUMNS``. Only
    in-scope series (EQ) rows with valid prices are returned. May return an
    empty DataFrame (with correct columns) when no in-scope rows exist.
    """
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"no CSV found in {path}")
        raw_bytes = zf.read(csv_names[0])
    return parse_bytes(raw_bytes, fmt)


def parse_bytes(data: bytes, fmt: str) -> pd.DataFrame:
    """Parse raw CSV bytes (already extracted from a .zip) → unified rows.

    Convenience entry point for tests that want to avoid writing files to disk.
    ``fmt`` is ``'legacy'`` or ``'udiff'``.
    """
    if fmt == FMT_LEGACY:
        return _parse_legacy(data)
    if fmt == FMT_UDIFF:
        return _parse_udiff(data)
    raise ValueError(f"unknown bhavcopy format {fmt!r}; expected 'legacy' or 'udiff'")


# --------------------------------------------------------------------------- #
# Per-format parsers                                                            #
# --------------------------------------------------------------------------- #
def _parse_legacy(raw_bytes: bytes) -> pd.DataFrame:
    """Legacy CM bhavcopy CSV → unified raw rows.

    The NSE legacy header ends with a trailing comma, which produces an
    "Unnamed" column — that column is dropped before any processing.
    """
    df = pd.read_csv(io.BytesIO(raw_bytes))
    # Column names may have leading/trailing whitespace; NSE header has trailing comma.
    df.columns = [c.strip() for c in df.columns]
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")].copy()

    # Series filter first (cheap; reduces work for subsequent steps).
    df = df[df["SERIES"].str.strip().isin(IN_SCOPE_SERIES)].copy()
    if df.empty:
        return _empty_unified()

    # ISIN is the join key — rows without it are unusable downstream.
    df = df.dropna(subset=["ISIN"])

    # Numeric coercion (non-numeric cells become NaN, caught by dropna below).
    for col in ("OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY", "TOTTRDVAL"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop suspended / empty rows (zero or null prices).
    df = df.dropna(subset=["OPEN", "HIGH", "LOW", "CLOSE"])
    df = df[(df["OPEN"] > 0) & (df["CLOSE"] > 0)].copy()
    if df.empty:
        return _empty_unified()

    # TIMESTAMP is usually "04-JUL-2024" but NSE occasionally emits 2-digit years
    # (e.g. "13-Jul-20" on 2020-07-13). format="mixed" infers per-row, handling both.
    date_col = pd.to_datetime(
        df["TIMESTAMP"].str.strip(), format="mixed", dayfirst=True
    )

    return pd.DataFrame(
        {
            "isin": df["ISIN"].str.strip(),
            "symbol": df["SYMBOL"].str.strip(),
            "date": date_col,
            "open": df["OPEN"].astype("float64"),
            "high": df["HIGH"].astype("float64"),
            "low": df["LOW"].astype("float64"),
            "close": df["CLOSE"].astype("float64"),
            "volume": df["TOTTRDQTY"].astype(float).astype("int64"),
            "traded_value": df["TOTTRDVAL"].astype("float64"),
            "series": df["SERIES"].str.strip(),
        }
    ).reset_index(drop=True)


def _parse_udiff(raw_bytes: bytes) -> pd.DataFrame:
    """UDiFF CM bhavcopy CSV → unified raw rows."""
    df = pd.read_csv(io.BytesIO(raw_bytes))
    df.columns = [c.strip() for c in df.columns]

    # Equity filter: FinInstrmTp must be STK (excludes FUT, OPT, EQ-warrants, etc.)
    df = df[df["FinInstrmTp"] == "STK"].copy()

    # Equities have no expiry date; F&O and warrants have one.
    xpry = df["XpryDt"].astype(str).str.strip()
    df = df[xpry.isin(_UDIFF_NO_EXPIRY)].copy()

    # Series filter.
    df = df[df["SctySrs"].str.strip().isin(IN_SCOPE_SERIES)].copy()
    if df.empty:
        return _empty_unified()

    # ISIN is the join key.
    df = df.dropna(subset=["ISIN"])

    # Numeric coercion.
    for col in ("OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol", "TtlTrfVal"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop suspended / empty rows.
    df = df.dropna(subset=["OpnPric", "HghPric", "LwPric", "ClsPric"])
    df = df[(df["OpnPric"] > 0) & (df["ClsPric"] > 0)].copy()
    if df.empty:
        return _empty_unified()

    # TradDt: "2024-07-25" → Timestamp.
    date_col = pd.to_datetime(df["TradDt"].str.strip())

    return pd.DataFrame(
        {
            "isin": df["ISIN"].str.strip(),
            "symbol": df["TckrSymb"].str.strip(),
            "date": date_col,
            "open": df["OpnPric"].astype("float64"),
            "high": df["HghPric"].astype("float64"),
            "low": df["LwPric"].astype("float64"),
            "close": df["ClsPric"].astype("float64"),
            # TtlTradgVol may be stored as float in the CSV (e.g. "48235.0").
            "volume": df["TtlTradgVol"].astype(float).round().astype("int64"),
            "traded_value": df["TtlTrfVal"].astype("float64"),
            "series": df["SctySrs"].str.strip(),
        }
    ).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #
def _empty_unified() -> pd.DataFrame:
    return pd.DataFrame({c: [] for c in UNIFIED_RAW_COLUMNS})
