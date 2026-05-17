from app.pipeline.fetcher import fetch_stock_data
from unittest.mock import patch, MagicMock

@patch('yfinance.Ticker')
def test_fetch_stock_data_index(mock_ticker):
    mock_instance = MagicMock()
    mock_ticker.return_value = mock_instance
    mock_instance.history.return_value = MagicMock(empty=False)
    
    # This should fail initially because append_ns is not an argument
    fetch_stock_data("^NSEI", append_ns=False)
    mock_ticker.assert_called_with("^NSEI")

    fetch_stock_data("RELIANCE", append_ns=True)
    mock_ticker.assert_called_with("RELIANCE.NS")
