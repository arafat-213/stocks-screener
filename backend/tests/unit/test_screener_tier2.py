import pandas as pd

from app.pipeline.screener import check_profitability_streak


def test_streak_passes_with_positive_data():
    data = {
        "2023-12-31": [1000, 5000],
        "2022-12-31": [800, 4500],
        "2021-12-31": [600, 4000],
    }
    df = pd.DataFrame(data, index=["Net Income", "Total Revenue"])
    assert check_profitability_streak(df) is True


def test_streak_fails_with_negative_income():
    data = {
        "2023-12-31": [1000, 5000],
        "2022-12-31": [-100, 4500],  # Negative income
        "2021-12-31": [600, 4000],
    }
    df = pd.DataFrame(data, index=["Net Income", "Total Revenue"])
    assert check_profitability_streak(df) is False


def test_streak_fails_with_negative_revenue():
    data = {
        "2023-12-31": [1000, 5000],
        "2022-12-31": [800, -50],  # Negative revenue
        "2021-12-31": [600, 4000],
    }
    df = pd.DataFrame(data, index=["Net Income", "Total Revenue"])
    assert check_profitability_streak(df) is False


def test_streak_fails_with_missing_years():
    data = {
        "2023-12-31": [1000, 5000],
        "2022-12-31": [800, 4500],
    }
    df = pd.DataFrame(data, index=["Net Income", "Total Revenue"])
    assert check_profitability_streak(df) is False


def test_streak_fails_with_missing_rows():
    data = {
        "2023-12-31": [1000],
        "2022-12-31": [800],
        "2021-12-31": [600],
    }
    df = pd.DataFrame(data, index=["Net Income"])
    assert check_profitability_streak(df) is False


def test_streak_handles_empty_dataframe():
    df = pd.DataFrame()
    assert check_profitability_streak(df) is False


def test_streak_handles_different_keywords():
    data = {
        "2023-12-31": [1000, 5000],
        "2022-12-31": [800, 4500],
        "2021-12-31": [600, 4000],
    }
    df = pd.DataFrame(data, index=["Net Earnings", "Revenue"])
    assert check_profitability_streak(df) is True
