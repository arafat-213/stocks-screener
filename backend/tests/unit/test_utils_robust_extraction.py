import pandas as pd

from app.pipeline.utils import get_financial_row


def test_get_financial_row_basic_match():
    df = pd.DataFrame(
        [[100, 200], [300, 400]],
        index=["Net Income", "Total Revenue"],
        columns=["2023", "2022"],
    )
    # net_income keywords: ["net income", "net earnings", "profit after tax", "pat"]
    row = get_financial_row(df, "net_income")
    assert row is not None
    assert row["2023"] == 100


def test_get_financial_row_case_insensitive():
    df = pd.DataFrame([[100]], index=["NET INCOME"], columns=["2023"])
    row = get_financial_row(df, "net_income")
    assert row is not None
    assert row["2023"] == 100


def test_get_financial_row_partial_match():
    df = pd.DataFrame([[500]], index=["Total Operating Revenue"], columns=["2023"])
    # revenue keywords: ["total revenue", "revenue", "total operating revenue", "net sales"]
    row = get_financial_row(df, "revenue")
    assert row is not None
    assert row["2023"] == 500


def test_get_financial_row_no_match():
    df = pd.DataFrame([[100]], index=["Something Else"], columns=["2023"])
    row = get_financial_row(df, "net_income")
    assert row is None


def test_get_financial_row_ordered_priority():
    df = pd.DataFrame(
        [[100], [200]],
        index=["Net Earnings", "Net Income"],  # Both match net_income keywords
        columns=["2023"],
    )
    # net_income keywords: ["net income", "net earnings", ...]
    # "net income" comes first in keywords, so it should match "Net Income" row even if "Net Earnings" is first in DF?
    # Wait, the instruction says: "check each keyword (case-insensitive) against the DataFrame index."
    # This implies iterating keywords first.
    row = get_financial_row(df, "net_income")
    assert row.name == "Net Income"
