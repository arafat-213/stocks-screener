import datetime
from unittest.mock import patch

import pandas as pd

from app.db.models import FundamentalCache, FundamentalData, Stock, TechnicalSignal


@patch("app.routers.stocks.OHLCVCache.get")
def test_get_stock_detail_enhanced(mock_fetch, db, client):
    # Mock OHLCV data
    mock_df = pd.DataFrame(
        {
            "Close": [100.0],
            "Open": [95.0],
            "High": [105.0],
            "Low": [90.0],
            "Volume": [1000],
        },
        index=pd.to_datetime(["2024-05-11"]),
    )
    mock_df.index.name = "Date"
    mock_fetch.return_value = mock_df

    # Seed data
    symbol = "ENHANCED_STOCK"
    stock = Stock(
        symbol=symbol,
        name="Enhanced Stock",
        sector="Tech",
        industry="Software",
        market_cap=1000000.0,
    )
    db.add(stock)

    # Technical signals
    for i in range(300):
        sig = TechnicalSignal(
            date=datetime.datetime(2024, 1, 1) + datetime.timedelta(days=i),
            symbol=symbol,
            timeframe="D",
            is_bullish=True,
            entry_score=50.0 + (i % 50),
            rsi=60.0,
            above_200ema=True,
            is_consolidating=False,
            ema5_level=105.0,
            ema13_level=104.0,
            ema20_level=103.0,
            ema26_level=102.0,
        )
        db.add(sig)

    # Fundamental Data
    fund_data = FundamentalData(
        date=datetime.datetime.utcnow(),
        symbol=symbol,
        pe=25.0,
        pb=5.0,
        roe=18.0,
        pledged_percent=0.0,
    )
    db.add(fund_data)

    # Fundamental Cache
    fund_cache = FundamentalCache(
        symbol=symbol, roce=22.0, roe=20.0, de_ratio=0.2, peg_ratio=1.5
    )
    db.add(fund_cache)

    db.commit()

    response = client.get(f"/api/stocks/{symbol}")
    assert response.status_code == 200
    data = response.json()

    # Verify industry
    assert data["industry"] == "Software"

    # Verify technical signals in scores_map
    scores_d = data["scores"]["D"]
    assert "above_200ema" in scores_d
    assert scores_d["above_200ema"] is True
    assert "is_consolidating" in scores_d
    assert scores_d["is_consolidating"] is False
    assert scores_d["ema5_level"] == 105.0
    assert scores_d["ema13_level"] == 104.0
    assert scores_d["ema20_level"] == 103.0
    assert scores_d["ema26_level"] == 102.0

    # Verify score_history limit
    assert len(data["score_history"]) == 250

    # Verify fundamentals
    funds = data["fundamentals"]
    assert funds["pe"] == 25.0  # Should NOT be peg_ratio (1.5)
    assert funds["pb"] == 5.0
    assert funds["roe"] == 20.0  # From FundamentalCache
    assert funds["roce"] == 22.0  # From FundamentalCache
    assert funds["debt_equity"] == 0.2  # From FundamentalCache
    assert funds["pledged_percent"] == 0.0  # From FundamentalData
