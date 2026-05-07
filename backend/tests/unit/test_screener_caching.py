import pytest
from unittest.mock import MagicMock, patch
from app.pipeline.screener import fetch_and_cache_deep_fundamentals
from app.db.models import FundamentalCache, FundamentalData
import datetime

@patch('app.pipeline.screener.yf.Ticker')
def test_fetch_and_cache_deep_fundamentals(mock_ticker_class):
    # Setup mocks
    mock_db = MagicMock()
    mock_ticker = MagicMock()
    mock_ticker_class.return_value = mock_ticker
    
    # Mock Ticker.info
    mock_ticker.info = {
        'sector': 'Financial Services',
        'debtToEquity': 150.0,
        'pledgedPercent': 0.05,
        'trailingPE': 20,
        'priceToBook': 2.5,
        'returnOnEquity': 0.20,
        'earningsGrowth': 0.15,
        'heldPercentInsiders': 0.50,
        'marketCap': 1000000000
    }
    
    # Mock Ticker.financials (3 years of positive net income and revenue)
    import pandas as pd
    data = {
        '2023-12-31': [1000, 5000],
        '2022-12-31': [800, 4500],
        '2021-12-31': [600, 4000],
    }
    mock_ticker.financials = pd.DataFrame(data, index=['Net Income', 'Total Revenue'])
    
    # Mock DB query results (no existing cache)
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    symbols = ['RELIANCE']
    fetch_and_cache_deep_fundamentals(symbols, mock_db)
    
    # Verify DB interactions
    assert mock_db.add.call_count >= 2 # At least FundamentalCache and FundamentalData
    
    # Check if commit was called
    assert mock_db.commit.called
    
    # Check what was added
    added_objects = [call.args[0] for call in mock_db.add.call_args_list]
    
    cache_entry = next(obj for obj in added_objects if isinstance(obj, FundamentalCache))
    assert cache_entry.symbol == 'RELIANCE'
    assert cache_entry.profitability_streak_passed is True
    assert cache_entry.de_check_passed is True # 1.5 < 10 for Financial Services
    
    fund_data = next(obj for obj in added_objects if isinstance(obj, FundamentalData))
    assert fund_data.symbol == 'RELIANCE'
    assert fund_data.pe == 20
    assert fund_data.market_cap == 1000000000

@patch('app.pipeline.screener.yf.Ticker')
def test_fetch_and_cache_deep_fundamentals_de_fail(mock_ticker_class):
    # Setup mocks
    mock_db = MagicMock()
    mock_ticker = MagicMock()
    mock_ticker_class.return_value = mock_ticker
    
    # Mock Ticker.info - High D/E for non-financial sector
    mock_ticker.info = {
        'sector': 'Technology',
        'debtToEquity': 250.0, # > 2.0 default limit
        'pledgedPercent': 0.05,
        'marketCap': 1000000000
    }
    mock_ticker.financials = None # Should fail streak
    
    # Mock DB query results (no existing cache)
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    symbols = ['INFY']
    fetch_and_cache_deep_fundamentals(symbols, mock_db)
    
    added_objects = [call.args[0] for call in mock_db.add.call_args_list]
    cache_entry = next(obj for obj in added_objects if isinstance(obj, FundamentalCache))
    
    assert cache_entry.symbol == 'INFY'
    assert cache_entry.de_check_passed is False
    assert cache_entry.profitability_streak_passed is False
