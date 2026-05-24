import pytest
from sqlalchemy.orm import Session
from app.db.models import Stock, TechnicalSignal, FundamentalCache
from app.routers.dashboard import get_dashboard_results
from fastapi import Response
from datetime import datetime, timedelta

def test_dashboard_fundamental_filter_param(db: Session):
    # Setup: 1 stock that passes fundamentals, 1 that fails
    s1 = Stock(symbol="PASS.NS", name="Pass", sector="Tech", market_cap=100000)
    s2 = Stock(symbol="FAIL.NS", name="Fail", sector="Tech", market_cap=50000)
    db.add_all([s1, s2])
    db.commit()

    now = datetime.utcnow().replace(microsecond=0)
    sig1 = TechnicalSignal(symbol="PASS.NS", date=now, timeframe="D", is_bullish=True, entry_score=80, rsi=50, close_price=100)
    sig2 = TechnicalSignal(symbol="FAIL.NS", date=now, timeframe="D", is_bullish=True, entry_score=70, rsi=50, close_price=50)
    db.add_all([sig1, sig2])
    
    # FundamentalCache: PASS passes both, FAIL fails profitability
    c1 = FundamentalCache(symbol="PASS.NS", profitability_streak_passed=True, de_check_passed=True, cache_version=1)
    c2 = FundamentalCache(symbol="FAIL.NS", profitability_streak_passed=False, de_check_passed=True, cache_version=1)
    db.add_all([c1, c2])
    db.commit()

    # Test with fundamental_filter=True (default)
    res = get_dashboard_results(Response(), db, fundamental_filter=True)
    symbols = [item["symbol"] for item in res["items"]]
    assert "PASS.NS" in symbols
    assert "FAIL.NS" not in symbols

    # Test with fundamental_filter=False
    res = get_dashboard_results(Response(), db, fundamental_filter=False)
    symbols = [item["symbol"] for item in res["items"]]
    assert "PASS.NS" in symbols
    assert "FAIL.NS" in symbols
    
    # Check fundamental_quality metadata
    fail_item = next(item for item in res["items"] if item["symbol"] == "FAIL.NS")
    assert fail_item["fundamental_quality"]["profitability_ok"] is False
    assert fail_item["fundamental_quality"]["has_fundamentals"] is True

def test_momentum_rsi_bound_lowered(db: Session):
    from app.screens.momentum import screen_actionable_entries
    
    now = datetime.utcnow().date()
    # Stock with RSI 37 (passes new bound, fails old 40 bound)
    s = Stock(symbol="RSI37.NS", name="RSI 37", sector="Tech")
    db.add(s)
    sig = TechnicalSignal(
        symbol="RSI37.NS", date=now, timeframe="D", 
        ema_signal='bullish_cross', above_200ema=True, 
        rsi=37, momentum_12m=10, is_consolidating=True,
        volume_breakout=True, entry_score=80
    )
    db.add(sig)
    db.commit()
    
    results = screen_actionable_entries(db)
    symbols = [r[0] for r in results]
    assert "RSI37.NS" in symbols
