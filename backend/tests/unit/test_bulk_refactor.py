import pandas as pd

from app.pipeline.fetcher import slice_bulk_df


def test_slice_bulk_df_multiindex():
    cols = pd.MultiIndex.from_tuples(
        [("Close", "RELIANCE.NS"), ("Open", "RELIANCE.NS"), ("Close", "TCS.NS")]
    )
    df = pd.DataFrame([[100, 90, 200], [110, 100, 210]], columns=cols)
    sliced = slice_bulk_df(df, "RELIANCE")
    assert sliced is not None
    assert "Close" in sliced.columns
    assert sliced.iloc[0]["Close"] == 100
    assert len(sliced.columns) == 2  # Should only have RELIANCE cols


def test_slice_bulk_df_single():
    df = pd.DataFrame([[100, 90]], columns=["Close", "Open"])
    sliced = slice_bulk_df(df, "RELIANCE")
    assert sliced is not None
    assert sliced.iloc[0]["Close"] == 100
    assert len(sliced.columns) == 2


def test_slice_bulk_df_missing():
    cols = pd.MultiIndex.from_tuples([("Close", "TCS.NS")])
    df = pd.DataFrame([[200]], columns=cols)
    sliced = slice_bulk_df(df, "RELIANCE")
    assert sliced is None


def test_slice_bulk_df_empty():
    df = pd.DataFrame()
    sliced = slice_bulk_df(df, "RELIANCE")
    assert sliced is None


def test_slice_bulk_df_all_nan():
    cols = pd.MultiIndex.from_tuples([("Close", "RELIANCE.NS")])
    df = pd.DataFrame([[float("nan")]], columns=cols)
    sliced = slice_bulk_df(df, "RELIANCE")
    assert sliced is None
