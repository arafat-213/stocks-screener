"""
One-off script to generate committed fixture parquet files for T2 tests.
Run once: backend/venv/bin/python tests/backtest_v2/fixtures/make_fixtures.py

Produces:
  tri_n200m30_fixture.parquet     — 10 rows of synthetic Nifty200 Momentum 30 TRI
  tri_midcap_fixture.parquet      — 10 rows of synthetic Nifty Midcap150 Momentum 50 TRI
  tri_nifty50_fixture.parquet     — 10 rows of synthetic Nifty 50 TRI
  price_nifty50_fixture.parquet   — 10 rows of synthetic Nifty 50 price index (CLOSE)
"""

from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent

DATES = pd.bdate_range("2024-01-02", periods=15)  # 15 business days


# Synthetic TRI values (start ~35000, grow ~0.1%/day)
def _make_tri(start: float) -> pd.Series:
    vals = [start * (1.001**i) for i in range(15)]
    return pd.Series(vals, index=DATES, name="tri")


# Synthetic price values (start ~21500, grow ~0.05%/day)
def _make_price(start: float) -> pd.Series:
    vals = [start * (1.0005**i) for i in range(15)]
    return pd.Series(vals, index=DATES, name="price_close")


_make_tri(35000.0).to_frame().to_parquet(HERE / "tri_n200m30_fixture.parquet")
_make_tri(64000.0).to_frame().to_parquet(HERE / "tri_midcap_fixture.parquet")
_make_tri(31900.0).to_frame().to_parquet(HERE / "tri_nifty50_fixture.parquet")
_make_price(21500.0).to_frame().to_parquet(HERE / "price_nifty50_fixture.parquet")

print("Fixtures written.")
