import pandas as pd

FIELD_KEYWORDS = {
    "net_income":     ["net income", "net earnings", "profit after tax", "pat"],
    "revenue":        ["total revenue", "revenue", "total operating revenue", "net sales"],
    "ebit":           ["ebit", "operating income", "operating profit"],
    "total_assets":   ["total assets"],
    "current_liab":   ["current liabilities", "total current liabilities"],
    "op_cashflow":    ["operating cash flow", "cash from operations", "net cash from operating"],
    "capex":          ["capital expenditure", "purchase of fixed assets", "capex"],
}

def to_float(val, default=None):
    """Safely converts a value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def get_financial_row(df: pd.DataFrame, field_key: str) -> pd.Series | None:
    """
    Extracts a row from a yfinance financial DataFrame using ordered keyword matching.
    Looks up keywords for field_key, checks each keyword (case-insensitive) against index.
    Returns the first matching row as a Series, or None if no match.
    """
    if df is None or df.empty or field_key not in FIELD_KEYWORDS:
        return None
    
    keywords = FIELD_KEYWORDS[field_key]
    index_lowered = [str(idx).lower() for idx in df.index]
    
    for kw in keywords:
        kw_lower = kw.lower()
        for i, idx_val in enumerate(index_lowered):
            if kw_lower in idx_val:
                return df.iloc[i]
    return None

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
