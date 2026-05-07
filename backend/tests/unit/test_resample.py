import pandas as pd
import pytest
from app.pipeline.utils import resample_ohlcv

def test_resample_ohlcv_weekly():
    # Create daily data for 2 weeks
    # Week 1: Mon-Fri (5 days)
    # Week 2: Mon-Wed (3 days) - Incomplete if freq is W-FRI
    dates = pd.date_range(start="2023-01-02", periods=8, freq="D")  # 2023-01-02 is Monday
    data = {
        "Open": [100.0] * 8,
        "High": [110.0] * 8,
        "Low": [90.0] * 8,
        "Close": [105.0] * 8,
        "Volume": [1000] * 8
    }
    df = pd.DataFrame(data, index=dates)
    
    # Resample to weekly (Friday)
    # Week 1 should end on 2023-01-06 (Friday)
    # Week 2 should end on 2023-01-13 (Friday), but we only have data up to Wed 2023-01-09
    
    # By default, drop_incomplete=True, so it should only return Week 1
    resampled = resample_ohlcv(df, freq="W-FRI", drop_incomplete=True)
    
    assert len(resampled) == 1
    assert resampled.index[0] == pd.Timestamp("2023-01-06")
    assert resampled.iloc[0]["Open"] == 100.0
    assert resampled.iloc[0]["High"] == 110.0
    assert resampled.iloc[0]["Low"] == 90.0
    assert resampled.iloc[0]["Close"] == 105.0
    assert resampled.iloc[0]["Volume"] == 5000  # 1000 * 5 days

def test_resample_ohlcv_keep_incomplete():
    dates = pd.date_range(start="2023-01-02", periods=8, freq="D")
    data = {
        "Open": [100.0] * 8,
        "High": [110.0] * 8,
        "Low": [90.0] * 8,
        "Close": [105.0] * 8,
        "Volume": [1000] * 8
    }
    df = pd.DataFrame(data, index=dates)
    
    resampled = resample_ohlcv(df, freq="W-FRI", drop_incomplete=False)
    
    assert len(resampled) == 2
    assert resampled.iloc[1]["Volume"] == 3000  # 1000 * 3 days (Mon, Tue, Wed)
