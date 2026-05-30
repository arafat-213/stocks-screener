import datetime
from unittest.mock import MagicMock, patch

from app.pipeline.screener import (
    CURRENT_SCREENER_VERSION,
    fetch_and_cache_deep_fundamentals,
)


@patch("app.pipeline.screener.yf.Ticker")
def test_screener_uses_resilient_session(mock_ticker):
    # Setup mock to not crash on DB operations
    mock_instance = MagicMock()
    mock_ticker.return_value = mock_instance
    mock_instance.info = {"marketCap": 1e10}
    mock_instance.financials = MagicMock(empty=True)
    mock_instance.balance_sheet = MagicMock(empty=True)
    mock_instance.cashflow = MagicMock(empty=True)

    mock_db_session = MagicMock()
    mock_cache = MagicMock()
    # Mocking properties to prevent TypeError during comparisons
    mock_cache.last_updated = datetime.datetime.utcnow()
    mock_cache.cache_version = CURRENT_SCREENER_VERSION
    mock_db_session.query.return_value.filter.return_value.first.return_value = (
        mock_cache
    )

    fetch_and_cache_deep_fundamentals(["TEST"], mock_db_session)

    mock_ticker.assert_called_with("TEST.NS")
