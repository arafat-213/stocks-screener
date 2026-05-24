import pytest
from unittest.mock import patch
from app.db.models import Stock

@patch('app.routers.stocks.OHLCVCache.get')
def test_get_stock_detail_with_ns_suffix_case_insensitive(mock_fetch, client, db):
    # Seed data
    db.add(Stock(symbol="RELIANCE", name="Reliance Industries Ltd", sector="Energy"))
    db.commit()

    # Mock the return value of OHLCVCache.get to simulate a valid response
    def mock_fetch_stock_data(*args, **kwargs):
        import pandas as pd
        mock_df = pd.DataFrame({"Close": [100.0], "Open": [95.0], "High": [105.0], "Low": [90.0], "Volume": [1000]}, index=pd.to_datetime(["2024-05-11"]))
        mock_df.index.name = "Date"
        return mock_df
    
    mock_fetch.side_effect = mock_fetch_stock_data

    # Searching with .NS suffix (case-insensitive) should work
    for suffix in [".NS", ".ns", ".Ns", ".nS"]:
        response = client.get(f"/api/stocks/RELIANCE{suffix}")
        assert response.status_code == 200, f"Failed for RELIANCE{suffix}"
        data = response.json()
        assert data["symbol"] == "RELIANCE"
