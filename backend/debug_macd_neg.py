import numpy as np
import pandas as pd


def _make_macd_negative_territory_df() -> pd.DataFrame:
    n = 300
    closes = np.concatenate(
        [
            np.linspace(500, 100, 290),
            np.linspace(100, 102, 10),
        ]
    )
    df = pd.DataFrame(
        {
            "Open": closes * 0.998,
            "High": closes * 1.01,
            "Low": closes * 0.99,
            "Close": closes,
            "Volume": np.full(n, 2_000_000.0),
        },
        index=pd.date_range("2021-01-01", periods=n, freq="B"),
    )
    return df


df = _make_macd_negative_territory_df()
df.ta.macd(fast=12, slow=26, signal=9, append=True)
latest = df.iloc[-1]
prev = df.iloc[-2]

macd_line = latest["MACD_12_26_9"]
signal_line = latest["MACDs_12_26_9"]
prev_macd = prev["MACD_12_26_9"]
prev_sig = prev["MACDs_12_26_9"]

fresh_cross = (macd_line > signal_line) and (prev_macd <= prev_sig)
condition = macd_line > signal_line and macd_line < 0

print(f"{macd_line=}")
print(f"{signal_line=}")
print(f"{prev_macd=}")
print(f"{prev_sig=}")
print(f"{fresh_cross=}")
print(f"{condition=}")
