import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import FundamentalCache, ScreenResult, TechnicalSignal


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    # Base.metadata.create_all(bind=engine) # This might fail if models are not fully defined for SQLite
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_technical_signal_new_fields():
    # This should fail if columns are missing or ScreenResult is not defined
    # Actually, we just want to test that we can instantiate with these kwargs
    sig = TechnicalSignal(
        momentum_1m=10.5,
        momentum_3m=15.2,
        momentum_6m=20.1,
        rs_score=85.0,
        adx=25.0,
        above_200ema=True,
        ema_slope_21=0.05,
        pct_from_52w_high=-5.0,
        pct_from_52w_low=40.0,
        week52_high=150.0,
        week52_low=100.0,
        resistance_level=145.0,
        pct_from_resistance=-2.0,
        volume_breakout=True,
    )
    assert sig.momentum_1m == 10.5
    assert sig.volume_breakout is True


def test_fundamental_cache_new_fields():
    cache = FundamentalCache(
        roce=18.5,
        peg_ratio=1.2,
        ev_to_ebitda=12.0,
        dividend_yield=1.5,
        price_to_fcf=25.0,
        earnings_growth_3y=15.0,
        fcf_positive=True,
        dividend_consistency=True,
        market_cap_category="Large Cap",
    )
    assert cache.roce == 18.5
    assert cache.market_cap_category == "Large Cap"


def test_screen_result_model():
    res = ScreenResult(
        screen_slug="growth-momentum",
        symbol="RELIANCE.NS",
        timeframe="D",
        rank=1,
        score_used=92.5,
    )
    assert res.screen_slug == "growth-momentum"
    assert res.rank == 1
