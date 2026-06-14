"""T3 parse-layer tests.

Offline only — in-memory ZIP fixtures, no network (CLAUDE.md Rule 4).
Fixture CSV strings are committed below; they serve as the golden inputs for
the parse layer and document the exact NSE column layouts verified in T0/T2.

Covers:
  * Legacy + UDiFF parsers → identical unified schema columns and dtypes.
  * Series filter: BE (legacy) and SM (UDiFF) rows excluded; EQ rows retained.
  * UDiFF instrument filters: FUT rows excluded; STK+XpryDt rows excluded.
  * Zero-price / suspended rows excluded.
  * ISIN present on every retained row.
  * parse_file() reads correctly from a real .zip on disk.
  * All-filtered input returns an empty DataFrame with correct columns.
"""

import io
import zipfile

import pandas as pd
import pytest

from app.data.bhavcopy import parse as p
from app.data.bhavcopy.download import FMT_LEGACY, FMT_UDIFF

# --------------------------------------------------------------------------- #
# Committed fixture data (golden inputs, T0-verified column layouts)           #
# --------------------------------------------------------------------------- #

# Legacy CM bhavcopy — 13 columns + trailing comma (captured in T2 session log:
#   SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,
#   TIMESTAMP,TOTALTRADES,ISIN,)
# Rows: 2 EQ (retained), 1 BE (excluded by series), 1 zero-price EQ (excluded).
_LEGACY_CSV = (
    "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,"
    "TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
    "RELIANCE,EQ,2800.00,2850.00,2790.00,2840.00,2840.00,2800.00,"
    "1000000,2840000000.00,04-JUL-2024,50000,INE002A01018,\n"
    "TCS,EQ,3500.00,3600.00,3450.00,3550.00,3550.00,3480.00,"
    "500000,1775000000.00,04-JUL-2024,30000,INE467B01029,\n"
    "DUMMYBE,BE,150.00,160.00,145.00,155.00,155.00,148.00,"
    "5000,775000.00,04-JUL-2024,200,INE000B01001,\n"
    "SUSPENDED,EQ,0.00,0.00,0.00,0.00,0.00,100.00,"
    "0,0.00,04-JUL-2024,0,INE000Z00000,\n"
)

# UDiFF CM bhavcopy — 34 columns (layout from 01_DATA_LAYER.md §2 verbatim row).
# Rows: 2 STK+EQ (retained), 1 FUT (excluded by FinInstrmTp), 1 STK+SM series
#       (excluded by series filter), 1 STK+EQ+XpryDt (excluded by expiry filter).
_UDIFF_HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,"
    "XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,"
    "LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,"
    "ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,"
    "Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4"
)
_UDIFF_COLS = _UDIFF_HEADER.split(",")


def _udiff_row(**overrides: str) -> str:
    """Build one UDiFF CSV data row from defaults + keyword overrides."""
    defaults: dict[str, str] = {
        "TradDt": "2024-07-25",
        "BizDt": "2024-07-25",
        "Sgmt": "CM",
        "Src": "NSE",
        "FinInstrmTp": "STK",
        "FinInstrmId": "1",
        "ISIN": "INE000A00000",
        "TckrSymb": "DUMMY",
        "SctySrs": "EQ",
        "XpryDt": "",
        "FininstrmActlXpryDt": "",
        "StrkPric": "",
        "OptnTp": "",
        "FinInstrmNm": "DUMMY LTD",
        "OpnPric": "100.00",
        "HghPric": "105.00",
        "LwPric": "98.00",
        "ClsPric": "103.00",
        "LastPric": "103.00",
        "PrvsClsgPric": "100.00",
        "UndrlygPric": "",
        "SttlmPric": "103.00",
        "OpnIntrst": "",
        "ChngInOpnIntrst": "",
        "TtlTradgVol": "10000",
        "TtlTrfVal": "1030000.00",
        "TtlNbOfTxsExctd": "500",
        "SsnId": "F1",
        "NewBrdLotQty": "1",
        "Rmks": "",
        "Rsvd1": "",
        "Rsvd2": "",
        "Rsvd3": "",
        "Rsvd4": "",
    }
    defaults.update(overrides)
    return ",".join(defaults[c] for c in _UDIFF_COLS)


_UDIFF_CSV = (
    "\n".join(
        [
            _UDIFF_HEADER,
            # BASF — verbatim from 01_DATA_LAYER.md §2 sample (2024-07-25), retained.
            _udiff_row(
                FinInstrmId="368",
                ISIN="INE373A01013",
                TckrSymb="BASF",
                FinInstrmNm="BASF INDIA LTD",
                OpnPric="5898.00",
                HghPric="6200.00",
                LwPric="5819.50",
                ClsPric="6172.95",
                TtlTradgVol="48235",
                TtlTrfVal="292169028.65",
            ),
            # RELIANCE — retained.
            _udiff_row(
                FinInstrmId="999",
                ISIN="INE002A01018",
                TckrSymb="RELIANCE",
                FinInstrmNm="RELIANCE INDUSTRIES LTD",
                OpnPric="2800.00",
                HghPric="2850.00",
                LwPric="2790.00",
                ClsPric="2840.00",
                TtlTradgVol="1000000",
                TtlTrfVal="2840000000.00",
            ),
            # FUT row — excluded: FinInstrmTp != STK.
            _udiff_row(
                FinInstrmTp="FUT",
                ISIN="",
                TckrSymb="NIFTY",
                SctySrs="",
                XpryDt="2024-07-25",
                FinInstrmNm="NIFTY 25 JUL 2024",
            ),
            # DUMMYSME — excluded: SctySrs == SM (out-of-scope series).
            _udiff_row(
                FinInstrmId="998",
                ISIN="INE000B01001",
                TckrSymb="DUMMYSME",
                SctySrs="SM",
            ),
            # DUMMYWRNT — excluded: STK + EQ but XpryDt is set (warrant with expiry).
            _udiff_row(
                FinInstrmId="997",
                ISIN="INE000C01001",
                TckrSymb="DUMMYWRNT",
                XpryDt="2024-07-25",
            ),
        ]
    )
    + "\n"
)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #
def _make_zip(csv_content: str, inner_filename: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_filename, csv_content.encode("utf-8"))
    return buf.getvalue()


def _legacy_zip_bytes() -> bytes:
    return _make_zip(_LEGACY_CSV, "cm04JUL2024bhav.csv")


def _udiff_zip_bytes() -> bytes:
    return _make_zip(_UDIFF_CSV, "BhavCopy_NSE_CM_0_0_0_20240725_F_0000.csv")


# --------------------------------------------------------------------------- #
# Schema identity                                                               #
# --------------------------------------------------------------------------- #
def test_legacy_parses_to_unified_schema():
    df = p.parse_bytes(_LEGACY_CSV.encode(), FMT_LEGACY)
    assert list(df.columns) == p.UNIFIED_RAW_COLUMNS
    assert df.dtypes["date"] == "datetime64[ns]"
    assert df.dtypes["open"] == "float64"
    assert df.dtypes["volume"] == "int64"


def test_udiff_parses_to_unified_schema():
    df = p.parse_bytes(_UDIFF_CSV.encode(), FMT_UDIFF)
    assert list(df.columns) == p.UNIFIED_RAW_COLUMNS
    assert df.dtypes["date"] == "datetime64[ns]"
    assert df.dtypes["open"] == "float64"
    assert df.dtypes["volume"] == "int64"


def test_both_formats_produce_identical_column_set():
    """Column names and dtypes must match regardless of source format."""
    leg = p.parse_bytes(_LEGACY_CSV.encode(), FMT_LEGACY)
    udiff = p.parse_bytes(_UDIFF_CSV.encode(), FMT_UDIFF)
    assert list(leg.columns) == list(udiff.columns)
    assert dict(leg.dtypes) == dict(udiff.dtypes)


# --------------------------------------------------------------------------- #
# Golden values — legacy                                                        #
# --------------------------------------------------------------------------- #
def test_legacy_retained_row_count():
    df = p.parse_bytes(_LEGACY_CSV.encode(), FMT_LEGACY)
    # RELIANCE + TCS retained; BE and zero-price excluded.
    assert len(df) == 2


def test_legacy_golden_reliance():
    df = p.parse_bytes(_LEGACY_CSV.encode(), FMT_LEGACY)
    row = df[df["symbol"] == "RELIANCE"].iloc[0]
    assert row["isin"] == "INE002A01018"
    assert row["date"] == pd.Timestamp("2024-07-04")
    assert row["open"] == pytest.approx(2800.00)
    assert row["high"] == pytest.approx(2850.00)
    assert row["low"] == pytest.approx(2790.00)
    assert row["close"] == pytest.approx(2840.00)
    assert row["volume"] == 1_000_000
    assert row["traded_value"] == pytest.approx(2_840_000_000.00)
    assert row["series"] == "EQ"


def test_legacy_golden_tcs():
    df = p.parse_bytes(_LEGACY_CSV.encode(), FMT_LEGACY)
    row = df[df["symbol"] == "TCS"].iloc[0]
    assert row["isin"] == "INE467B01029"
    assert row["close"] == pytest.approx(3550.00)
    assert row["volume"] == 500_000


# --------------------------------------------------------------------------- #
# Golden values — UDiFF                                                         #
# --------------------------------------------------------------------------- #
def test_udiff_retained_row_count():
    df = p.parse_bytes(_UDIFF_CSV.encode(), FMT_UDIFF)
    # BASF + RELIANCE retained; FUT, SM-series, and XpryDt rows excluded.
    assert len(df) == 2


def test_udiff_golden_basf():
    """Verbatim row from 01_DATA_LAYER.md §2 sample."""
    df = p.parse_bytes(_UDIFF_CSV.encode(), FMT_UDIFF)
    row = df[df["symbol"] == "BASF"].iloc[0]
    assert row["isin"] == "INE373A01013"
    assert row["date"] == pd.Timestamp("2024-07-25")
    assert row["open"] == pytest.approx(5898.00)
    assert row["high"] == pytest.approx(6200.00)
    assert row["low"] == pytest.approx(5819.50)
    assert row["close"] == pytest.approx(6172.95)
    assert row["volume"] == 48_235
    assert row["traded_value"] == pytest.approx(292_169_028.65)
    assert row["series"] == "EQ"


def test_udiff_golden_reliance():
    df = p.parse_bytes(_UDIFF_CSV.encode(), FMT_UDIFF)
    row = df[df["symbol"] == "RELIANCE"].iloc[0]
    assert row["isin"] == "INE002A01018"
    assert row["close"] == pytest.approx(2840.00)
    assert row["volume"] == 1_000_000


# --------------------------------------------------------------------------- #
# Series filter                                                                 #
# --------------------------------------------------------------------------- #
def test_legacy_be_series_excluded():
    df = p.parse_bytes(_LEGACY_CSV.encode(), FMT_LEGACY)
    assert "DUMMYBE" not in df["symbol"].values


def test_udiff_sm_series_excluded():
    df = p.parse_bytes(_UDIFF_CSV.encode(), FMT_UDIFF)
    assert "DUMMYSME" not in df["symbol"].values


def test_only_eq_series_retained_in_output():
    leg = p.parse_bytes(_LEGACY_CSV.encode(), FMT_LEGACY)
    udiff = p.parse_bytes(_UDIFF_CSV.encode(), FMT_UDIFF)
    assert set(leg["series"].unique()) == {"EQ"}
    assert set(udiff["series"].unique()) == {"EQ"}


# --------------------------------------------------------------------------- #
# UDiFF-specific instrument filters                                             #
# --------------------------------------------------------------------------- #
def test_udiff_fut_excluded_by_instrument_type():
    df = p.parse_bytes(_UDIFF_CSV.encode(), FMT_UDIFF)
    assert "NIFTY" not in df["symbol"].values


def test_udiff_expiry_date_row_excluded():
    """STK+EQ rows with an XpryDt set (warrants) must be excluded."""
    df = p.parse_bytes(_UDIFF_CSV.encode(), FMT_UDIFF)
    assert "DUMMYWRNT" not in df["symbol"].values


# --------------------------------------------------------------------------- #
# Suspended / zero-price exclusion                                              #
# --------------------------------------------------------------------------- #
def test_legacy_zero_price_row_excluded():
    df = p.parse_bytes(_LEGACY_CSV.encode(), FMT_LEGACY)
    assert "SUSPENDED" not in df["symbol"].values


def test_zero_open_or_close_is_dropped():
    """A row with OPEN=0 (or CLOSE=0) must not appear in the output."""
    zero_open_csv = (
        "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,"
        "TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
        "ZEROOPEN,EQ,0.00,100.00,90.00,95.00,95.00,94.00,"
        "1000,95000.00,04-JUL-2024,50,INE999A00001,\n"
    )
    df = p.parse_bytes(zero_open_csv.encode(), FMT_LEGACY)
    assert df.empty


# --------------------------------------------------------------------------- #
# ISIN presence                                                                 #
# --------------------------------------------------------------------------- #
def test_isin_present_on_all_retained_legacy_rows():
    df = p.parse_bytes(_LEGACY_CSV.encode(), FMT_LEGACY)
    assert df["isin"].notna().all()
    assert (df["isin"].str.len() > 0).all()


def test_isin_present_on_all_retained_udiff_rows():
    df = p.parse_bytes(_UDIFF_CSV.encode(), FMT_UDIFF)
    assert df["isin"].notna().all()
    assert (df["isin"].str.len() > 0).all()


# --------------------------------------------------------------------------- #
# parse_file — reads from real .zip on disk                                     #
# --------------------------------------------------------------------------- #
def test_parse_file_legacy_from_zip(tmp_path):
    zip_path = tmp_path / "cm04JUL2024bhav.csv.zip"
    zip_path.write_bytes(_legacy_zip_bytes())
    df = p.parse_file(zip_path, FMT_LEGACY)
    assert list(df.columns) == p.UNIFIED_RAW_COLUMNS
    assert len(df) == 2
    assert set(df["series"].unique()) == {"EQ"}


def test_parse_file_udiff_from_zip(tmp_path):
    zip_path = tmp_path / "BhavCopy_NSE_CM_0_0_0_20240725_F_0000.csv.zip"
    zip_path.write_bytes(_udiff_zip_bytes())
    df = p.parse_file(zip_path, FMT_UDIFF)
    assert list(df.columns) == p.UNIFIED_RAW_COLUMNS
    assert len(df) == 2


def test_parse_file_raises_on_missing_csv(tmp_path):
    """ZIP with no CSV inside must raise ValueError, not an obscure exception."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "not a csv")
    zip_path = tmp_path / "bad.zip"
    zip_path.write_bytes(buf.getvalue())
    with pytest.raises(ValueError, match="no CSV found"):
        p.parse_file(zip_path, FMT_LEGACY)


# --------------------------------------------------------------------------- #
# All-filtered input → empty frame with correct schema                          #
# --------------------------------------------------------------------------- #
def test_all_out_of_scope_returns_empty_with_correct_columns():
    """A file containing only BE rows → empty DataFrame, columns correct."""
    all_be_csv = (
        "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,"
        "TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
        "RCOM,BE,15.00,16.00,14.00,15.50,15.50,15.00,"
        "50000,775000.00,04-JUL-2024,200,INE000D01001,\n"
    )
    df = p.parse_bytes(all_be_csv.encode(), FMT_LEGACY)
    assert df.empty
    assert list(df.columns) == p.UNIFIED_RAW_COLUMNS


def test_unknown_format_raises():
    with pytest.raises(ValueError, match="unknown bhavcopy format"):
        p.parse_bytes(b"", "bogus")
