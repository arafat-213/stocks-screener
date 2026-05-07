import pytest
from app.pipeline.screener import passes_tier1_fast_filters

def test_passes_tier1_valid_stock():
    # Valid stock: Mcap 10M, PE 20, ROE 20%, Pledge 5%, Volume 1M
    info = {
        'marketCap': 10_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is True
    assert flag_missing is False

def test_fails_tier1_market_cap():
    # Mcap < 6M
    info = {
        'marketCap': 5_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is False

def test_fails_tier1_pe_negative():
    # PE <= 0 (Loss making)
    info = {
        'marketCap': 10_000_000,
        'trailingPE': -5,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is False

def test_fails_tier1_pe_too_high():
    # PE > 150
    info = {
        'marketCap': 10_000_000,
        'trailingPE': 151,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is False

def test_fails_tier1_roe():
    # ROE < 15%
    info = {
        'marketCap': 10_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.14,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is False

def test_fails_tier1_pledge_high():
    # Pledge > 20%
    info = {
        'marketCap': 10_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.21,
        'averageVolume': 1_000_000
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is False

def test_flags_missing_pledge():
    # Pledge is None
    info = {
        'marketCap': 10_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.20,
        'pledgedPercent': None,
        'averageVolume': 1_000_000
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is True
    assert flag_missing is True

def test_fails_tier1_liquidity():
    # Volume < 500k
    info = {
        'marketCap': 10_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.05,
        'averageVolume': 499_999
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is False

def test_fails_tier1_empty_info():
    passes, flag_missing = passes_tier1_fast_filters({})
    assert passes is False

def test_uses_forward_pe_if_trailing_missing():
    # trailingPE missing, but forwardPE valid
    info = {
        'marketCap': 10_000_000,
        'forwardPE': 20,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is True
