import pandas as pd

def to_float(val, default=None):
    """Safely converts a value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def resample_ohlcv(df: pd.DataFrame, freq: str, drop_incomplete: bool = True) -> pd.DataFrame:
    """
    Resamples OHLCV data to a different frequency.
    Volume is summed, Open is first, High is max, Low is min, Close is last.
    """
    if df.empty:
        return df

    ohlcv_agg = {
        'Open': 'first', 
        'High': 'max', 
        'Low': 'min', 
        'Close': 'last', 
        'Volume': 'sum'
    }
    
    # Ensure columns exist before aggregating to avoid errors
    cols_to_agg = {k: v for k, v in ohlcv_agg.items() if k in df.columns}
    
    resampled = df.resample(freq).agg(cols_to_agg).dropna()
    
    if drop_incomplete and len(resampled) > 0:
        return resampled.iloc[:-1]
    
    return resampled
