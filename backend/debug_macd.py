import pandas as pd
import numpy as np
import pandas_ta as ta

def _make_macd_positive_territory_df() -> pd.DataFrame:
    n = 300
    # Accelerating uptrend: MACD line will be positive and above signal
    t = np.linspace(0, 1, n)
    closes = 80 + 100 * t + 20 * t**2
    df = pd.DataFrame({
        "Open":   closes * 0.998,
        "High":   closes * 1.015,
        "Low":    closes * 0.985,
        "Close":  closes,
        "Volume": np.full(n, 2_000_000.0),
    }, index=pd.date_range("2021-01-01", periods=n, freq="B"))
    return df

df = _make_macd_positive_territory_df()
df.ta.macd(fast=12, slow=26, signal=9, append=True)
latest = df.iloc[-1]
prev = df.iloc[-2]

macd_line = latest['MACD_12_26_9']
signal_line = latest['MACDs_12_26_9']
prev_macd = prev['MACD_12_26_9']
prev_sig = prev['MACDs_12_26_9']

fresh_cross = (macd_line > signal_line) and (prev_macd <= prev_sig)
condition = (macd_line > signal_line and macd_line > 0)

print(f"{macd_line=}")
print(f"{signal_line=}")
print(f"{prev_macd=}")
print(f"{prev_sig=}")
print(f"{fresh_cross=}")
print(f"{condition=}")
