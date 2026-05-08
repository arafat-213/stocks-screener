import pytest
from app.pipeline.screener import passes_tier1_fast_filters

def test_passes_tier1_valid_stock():
    # Valid stock: Mcap 21B, PE 20, ROE 5% (should pass), Pledge 50% (should pass), Volume 1M, Price 100 (Liquidity 100M)
    info = {
        'marketCap': 21_000_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.05,
        'pledgedPercent': 0.50,
        'averageVolume': 1_000_000,
        'currentPrice': 100
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is True
    assert flag_missing is False

def test_fails_tier1_market_cap():
    # Mcap < 20B
    info = {
        'marketCap': 19_000_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000,
        'currentPrice': 100
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is False

def test_fails_tier1_pe_negative():
    # PE <= 0 (Loss making)
    info = {
        'marketCap': 21_000_000_000,
        'trailingPE': -5,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000,
        'currentPrice': 100
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is False

def test_fails_tier1_pe_too_high():
    # PE > 300
    info = {
        'marketCap': 21_000_000_000,
        'trailingPE': 301,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000,
        'currentPrice': 100
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is False

def test_passes_tier1_roe_low():
    # ROE < 15% should now PASS
    info = {
        'marketCap': 21_000_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.01,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000,
        'currentPrice': 100
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is True

def test_passes_tier1_pledge_high():
    # Pledge > 20% should now PASS
    info = {
        'marketCap': 21_000_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.80,
        'averageVolume': 1_000_000,
        'currentPrice': 100
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is True

def test_flags_missing_pledge():
    # Pledge is None
    info = {
        'marketCap': 21_000_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.20,
        'pledgedPercent': None,
        'averageVolume': 1_000_000,
        'currentPrice': 100
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is True
    assert flag_missing is True

def test_fails_tier1_liquidity():
    # Value < 20M
    info = {
        'marketCap': 21_000_000_000,
        'trailingPE': 20,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.05,
        'averageVolume': 100_000,
        'currentPrice': 100
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is False

def test_fails_tier1_empty_info():
    passes, flag_missing = passes_tier1_fast_filters({})
    assert passes is False

def test_uses_forward_pe_if_trailing_missing():
    # trailingPE missing, but forwardPE valid
    info = {
        'marketCap': 21_000_000_000,
        'forwardPE': 20,
        'returnOnEquity': 0.20,
        'pledgedPercent': 0.05,
        'averageVolume': 1_000_000,
        'currentPrice': 100
    }
    passes, flag_missing = passes_tier1_fast_filters(info)
    assert passes is True
