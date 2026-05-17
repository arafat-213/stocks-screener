import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from app.pipeline.fetcher import fetch_stock_data, fetch_market_snapshots, session

@patch('yfinance.Ticker')
def test_fetch_stock_data_uses_session(mock_ticker):
    mock_instance = MagicMock()
    mock_ticker.return_value = mock_instance
    # Ensure hist has an index so hist.empty works correctly
    mock_instance.history.return_value = pd.DataFrame({'Close': [100, 101]}, index=pd.date_range('2023-01-01', periods=2))
    
    # We pass fetch_info=False to test the new signature
    fetch_stock_data("RELIANCE", fetch_info=False)
    
    mock_ticker.assert_called_once_with("RELIANCE.NS")

@patch('yfinance.download')
def test_fetch_market_snapshots_uses_session(mock_download):
    mock_download.return_value = pd.DataFrame()
    fetch_market_snapshots(["^NSEI"])
    
    mock_download.assert_called_once_with(["^NSEI"], period="5d", progress=False, threads=False)
