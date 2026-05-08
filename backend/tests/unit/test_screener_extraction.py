import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from app.pipeline.screener import fetch_and_cache_deep_fundamentals
from app.db.models import FundamentalCache, FundamentalData
import datetime

@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    return session

@patch('app.pipeline.screener.yf.Ticker')
@patch('app.pipeline.screener.time.sleep')
def test_fetch_and_cache_deep_fundamentals_extraction(mock_sleep, mock_ticker, mock_db_session):
    symbol = "RELIANCE"
    ticker_instance = MagicMock()
    mock_ticker.return_value = ticker_instance
    
    # Mock data for extraction
    ticker_instance.info = {
        'sector': 'Energy',
        'marketCap': 15_000_000_000_000, # 1.5 Lakh Cr -> Largecap
        'trailingPE': 25.0,
        'earningsGrowth': 0.15, # 15%
        'debtToEquity': 40.0, # 0.4x
        'pledgedPercent': 0.0,
        'returnOnEquity': 0.12,
        'priceToBook': 2.5,
        'heldPercentInsiders': 0.5,
    }
    
    # Financials (for ROCE)
    # yf returns reverse chrono: iloc[:, 0] is latest
    ticker_instance.financials = pd.DataFrame({
        '2024-03-31': [1000, 5000, 1200], # Net Income, Revenue, EBIT
    }, index=['Net Income', 'Total Revenue', 'EBIT'])
    
    # Balance Sheet (for ROCE)
    ticker_instance.balance_sheet = pd.DataFrame({
        '2024-03-31': [10000, 2000], # Total Assets, Current Liabilities
    }, index=['Total Assets', 'Current Liabilities'])
    
    # Cashflow (for FCF)
    ticker_instance.cashflow = pd.DataFrame({
        '2024-03-31': [2000, 500], # Operating Cash Flow, Capital Expenditure
    }, index=['Operating Cash Flow', 'Capital Expenditure'])
    
    # Dividends (for Consistency)
    ticker_instance.dividends = pd.Series(
        [1.0, 1.0, 1.0],
        index=[pd.Timestamp('2023-06-01'), pd.Timestamp('2024-06-01'), pd.Timestamp('2025-06-01')]
    )
    
    fetch_and_cache_deep_fundamentals([symbol], mock_db_session)
    
    # Verify DB calls
    assert mock_db_session.add.call_count >= 1
    cache_entry = None
    for call in mock_db_session.add.call_args_list:
        obj = call[0][0]
        if isinstance(obj, FundamentalCache):
            cache_entry = obj
            break
    
    assert cache_entry is not None
    assert cache_entry.symbol == symbol
    
    # ROCE = 1200 / (10000 - 2000) = 1200 / 8000 = 0.15
    assert cache_entry.roce == pytest.approx(0.15)
    
    # PEG = 25.0 / (0.15 * 100) = 25.0 / 15 = 1.666...
    assert cache_entry.peg_ratio == pytest.approx(1.666666, rel=1e-3)
    
    # FCF = 2000 - 500 = 1500
    # Price to FCF = 15,000,000,000,000 / 1500 = 10,000,000,000 (Wait, market cap is in Cr?)
    # Usually market cap and FCF are in same units in yfinance?
    # If marketCap is 15T and FCF is 1.5k, P/FCF is huge. 
    # But let's just check the logic: marketCap / FCF
    assert cache_entry.price_to_fcf == pytest.approx(15_000_000_000_000 / 1500)
    
    assert cache_entry.dividend_consistency is True
    assert cache_entry.market_cap_category == 'largecap'

@patch('app.pipeline.screener.yf.Ticker')
@patch('app.pipeline.screener.time.sleep')
def test_fetch_and_cache_deep_fundamentals_retry_logic(mock_sleep, mock_ticker, mock_db_session):
    symbol = "FAIL"
    mock_ticker.side_effect = Exception("API Error")
    
    fetch_and_cache_deep_fundamentals([symbol], mock_db_session)
    
    # Should attempt 3 times
    assert mock_ticker.call_count == 3
    
    # Verify cache marked as failed (-1)
    cache_entry = None
    for call in mock_db_session.add.call_args_list:
        obj = call[0][0]
        if isinstance(obj, FundamentalCache):
            cache_entry = obj
            break
    
    assert cache_entry is not None
    assert cache_entry.cache_version == -1
