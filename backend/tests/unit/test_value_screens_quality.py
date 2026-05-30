from datetime import datetime, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, FundamentalCache, Stock, TechnicalSignal
from app.screens.value import (
    screen_low_debt_midcap,
    screen_steady_compounders,
    screen_undervalued_fundamentals,
)

# In-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture
def db_session():
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Add common data
    # Use datetime instead of date because TechnicalSignal.date is DateTime
    today = datetime.combine(datetime.now().date(), time.min)

    # Stock 1: Passes all quality
    db.add(Stock(symbol="PASS.NS", name="Pass", market_cap=10000 * 1e7))
    db.add(
        FundamentalCache(
            symbol="PASS.NS",
            de_check_passed=True,
            fcf_positive=True,
            profitability_streak_passed=True,
            peg_ratio=1.0,
            roe=0.20,
            ev_to_ebitda=10,
            dividend_yield=0.02,
            roce=0.20,
            dividend_consistency=True,
            market_cap_category="midcap",
        )
    )
    db.add(
        TechnicalSignal(
            symbol="PASS.NS",
            date=today,
            timeframe="D",
            entry_score=80,
            above_200ema=True,
            is_bullish=True,
            rsi=50,
            ema_slope_20=1.0,
        )
    )

    # Stock 2: Fails profitability streak
    db.add(Stock(symbol="FAIL_STREAK.NS", name="Fail Streak", market_cap=10000 * 1e7))
    db.add(
        FundamentalCache(
            symbol="FAIL_STREAK.NS",
            de_check_passed=True,
            fcf_positive=True,
            profitability_streak_passed=False,  # FAILS
            peg_ratio=1.0,
            roe=0.20,
            ev_to_ebitda=10,
            dividend_yield=0.02,
            roce=0.20,
            dividend_consistency=True,
            market_cap_category="midcap",
        )
    )
    db.add(
        TechnicalSignal(
            symbol="FAIL_STREAK.NS",
            date=today,
            timeframe="D",
            entry_score=85,
            above_200ema=True,
            is_bullish=True,
            rsi=50,
            ema_slope_20=1.0,
        )
    )

    # Stock 3: Fails DE check
    db.add(Stock(symbol="FAIL_DE.NS", name="Fail DE", market_cap=10000 * 1e7))
    db.add(
        FundamentalCache(
            symbol="FAIL_DE.NS",
            de_check_passed=False,  # FAILS
            fcf_positive=True,
            profitability_streak_passed=True,
            peg_ratio=1.0,
            roe=0.20,
            ev_to_ebitda=10,
            dividend_yield=0.02,
            roce=0.20,
            dividend_consistency=True,
            market_cap_category="midcap",
        )
    )
    db.add(
        TechnicalSignal(
            symbol="FAIL_DE.NS",
            date=today,
            timeframe="D",
            entry_score=90,
            above_200ema=True,
            is_bullish=True,
            rsi=50,
            ema_slope_20=1.0,
        )
    )

    db.commit()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_screen_low_debt_midcap_quality(db_session):
    results = screen_low_debt_midcap(db_session, timeframe="D")
    symbols = [r.symbol for r in results]
    assert "PASS.NS" in symbols
    assert (
        "FAIL_STREAK.NS" not in symbols
    )  # Should fail due to profitability_streak_passed=False
    assert "FAIL_DE.NS" not in symbols  # Should fail due to de_check_passed=False


def test_screen_undervalued_fundamentals_quality(db_session):
    results = screen_undervalued_fundamentals(db_session, timeframe="D")
    symbols = [r.symbol for r in results]
    assert "PASS.NS" in symbols
    assert "FAIL_DE.NS" not in symbols  # Should fail due to de_check_passed=False
    assert (
        "FAIL_STREAK.NS" in symbols
    )  # This screen doesn't check profitability_streak_passed (only de_check_passed)


def test_screen_steady_compounders_quality(db_session):
    results = screen_steady_compounders(db_session, timeframe="D")
    symbols = [r.symbol for r in results]
    assert "PASS.NS" in symbols
    assert (
        "FAIL_STREAK.NS" not in symbols
    )  # Should fail due to profitability_streak_passed=False
    assert (
        "FAIL_DE.NS" in symbols
    )  # This screen doesn't check de_check_passed (only profitability_streak_passed)
