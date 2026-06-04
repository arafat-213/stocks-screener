import datetime

import pandas as pd

from app.backtest.engine import _calculate_breadth_map


def test_calculate_breadth_map():
    dates = pd.date_range("2023-01-01", periods=5)

    # Stock 1: Always above EMA200
    df1 = pd.DataFrame(
        {"Close": [110, 115, 120, 125, 130], "EMA_200": [100, 100, 100, 100, 100]},
        index=dates,
    )

    # Stock 2: Below EMA200 then above
    df2 = pd.DataFrame(
        {"Close": [90, 95, 105, 110, 115], "EMA_200": [100, 100, 100, 100, 100]},
        index=dates,
    )

    all_dfs = {"SYM1": df1, "SYM2": df2}

    breadth = _calculate_breadth_map(all_dfs)

    # Expected breadth:
    # 2023-01-01: SYM1 (Above), SYM2 (Below) -> 50%
    # 2023-01-02: SYM1 (Above), SYM2 (Below) -> 50%
    # 2023-01-03: SYM1 (Above), SYM2 (Above) -> 100%
    # 2023-01-04: SYM1 (Above), SYM2 (Above) -> 100%
    # 2023-01-05: SYM1 (Above), SYM2 (Above) -> 100%

    assert breadth[datetime.date(2023, 1, 1)] == 50.0
    assert breadth[datetime.date(2023, 1, 2)] == 50.0
    assert breadth[datetime.date(2023, 1, 3)] == 100.0
    assert breadth[datetime.date(2023, 1, 4)] == 100.0
    assert breadth[datetime.date(2023, 1, 5)] == 100.0


def test_calculate_breadth_map_empty():
    assert _calculate_breadth_map({}) == {}


def test_calculate_breadth_map_no_indicators():
    dates = pd.date_range("2023-01-01", periods=5)
    df1 = pd.DataFrame({"Close": [110, 115, 120, 125, 130]}, index=dates)
    assert _calculate_breadth_map({"SYM1": df1}) == {}
