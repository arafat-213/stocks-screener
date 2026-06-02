import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    SectorSnapshot,
    Stock,
    TechnicalSignal,
)
from app.screens.base import get_latest_signal_date
from app.screens.confluence import (
    screen_fresh_52w_breakout,
    screen_mtf_confluence,
    screen_sector_leaders,
)
from app.screens.sector_rotation import compute_sector_rotation, screen_hot_sectors


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_screen_mtf_confluence(db_session):
    date_d = datetime.datetime(2023, 10, 1, tzinfo=datetime.timezone.utc)
    date_w = datetime.datetime(2023, 9, 25, tzinfo=datetime.timezone.utc)
    date_m = datetime.datetime(2023, 9, 1, tzinfo=datetime.timezone.utc)

    # Add stocks
    db_session.add(Stock(symbol="RELIANCE.NS", name="Reliance", sector="Energy"))
    db_session.add(Stock(symbol="TCS.NS", name="TCS", sector="Tech"))

    # Setup mock signals
    # RELIANCE: Bullish on all three timeframes
    s_d = TechnicalSignal(
        symbol="RELIANCE.NS",
        date=date_d,
        timeframe="D",
        is_bullish=True,
        above_200ema=True,
        rsi=60,
        entry_score=80,
    )
    s_w = TechnicalSignal(
        symbol="RELIANCE.NS", date=date_w, timeframe="W", is_bullish=True
    )
    s_m = TechnicalSignal(
        symbol="RELIANCE.NS", date=date_m, timeframe="M", is_bullish=True
    )

    # TCS: Bullish on Daily but not Weekly
    t_d = TechnicalSignal(
        symbol="TCS.NS",
        date=date_d,
        timeframe="D",
        is_bullish=True,
        above_200ema=True,
        rsi=60,
        entry_score=70,
    )
    t_w = TechnicalSignal(symbol="TCS.NS", date=date_w, timeframe="W", is_bullish=False)

    db_session.add_all([s_d, s_w, s_m, t_d, t_w])
    db_session.commit()

    latest_d = get_latest_signal_date(db_session, "D")
    print(f"DEBUG: latest_d={latest_d}, type={type(latest_d)}")

    results = screen_mtf_confluence(db_session)
    assert len(results) == 1
    assert results[0][0] == "RELIANCE.NS"


def test_screen_sector_leaders(db_session):
    date = datetime.datetime(2023, 10, 1, tzinfo=datetime.timezone.utc)

    # Stocks in Tech sector
    db_session.add(Stock(symbol="TCS.NS", sector="Tech"))
    db_session.add(Stock(symbol="INFY.NS", sector="Tech"))
    db_session.add(Stock(symbol="WIPRO.NS", sector="Tech"))
    db_session.add(Stock(symbol="HCLTECH.NS", sector="Tech"))

    # Signals
    db_session.add(
        TechnicalSignal(
            symbol="TCS.NS",
            date=date,
            timeframe="D",
            rs_score=90,
            is_bullish=True,
            above_200ema=True,
        )
    )
    db_session.add(
        TechnicalSignal(
            symbol="INFY.NS",
            date=date,
            timeframe="D",
            rs_score=85,
            is_bullish=True,
            above_200ema=True,
        )
    )
    db_session.add(
        TechnicalSignal(
            symbol="WIPRO.NS",
            date=date,
            timeframe="D",
            rs_score=80,
            is_bullish=True,
            above_200ema=True,
        )
    )
    db_session.add(
        TechnicalSignal(
            symbol="HCLTECH.NS",
            date=date,
            timeframe="D",
            rs_score=75,
            is_bullish=True,
            above_200ema=True,
        )
    )

    db_session.commit()

    results = screen_sector_leaders(db_session)
    # Should only have top 3: TCS, INFY, WIPRO
    assert len(results) == 3
    symbols = [r[0] for r in results]
    assert "TCS.NS" in symbols
    assert "INFY.NS" in symbols
    assert "WIPRO.NS" in symbols
    assert "HCLTECH.NS" not in symbols


def test_screen_fresh_52w_breakout(db_session):
    date = datetime.datetime(2023, 10, 1, tzinfo=datetime.timezone.utc)

    # Add stocks
    db_session.add(Stock(symbol="RELIANCE.NS", name="Reliance", sector="Energy"))
    db_session.add(Stock(symbol="TCS.NS", name="TCS", sector="Tech"))

    # Breakout stock
    db_session.add(
        TechnicalSignal(
            symbol="RELIANCE.NS",
            date=date,
            timeframe="D",
            pct_from_52w_high=0.5,
            volume_breakout=True,
            above_200ema=True,
            rsi=65,
            adx=25,
            entry_score=90,
        )
    )

    # Not a breakout (volume missing)
    db_session.add(
        TechnicalSignal(
            symbol="TCS.NS",
            date=date,
            timeframe="D",
            pct_from_52w_high=0.5,
            volume_breakout=False,
            above_200ema=True,
            rsi=65,
            adx=25,
            entry_score=80,
        )
    )

    db_session.commit()

    results = screen_fresh_52w_breakout(db_session)
    assert len(results) == 1
    assert results[0][0] == "RELIANCE.NS"


def test_sector_rotation_computation(db_session):
    date_val = datetime.datetime(2023, 10, 1, tzinfo=datetime.timezone.utc)

    db_session.add(Stock(symbol="TCS.NS", sector="Tech"))
    db_session.add(Stock(symbol="INFY.NS", sector="Tech"))
    db_session.add(Stock(symbol="WIPRO.NS", sector="Tech"))

    db_session.add(
        TechnicalSignal(
            symbol="TCS.NS",
            date=date_val,
            timeframe="D",
            rs_score=90,
            is_bullish=True,
            momentum_3m=10,
        )
    )
    db_session.add(
        TechnicalSignal(
            symbol="INFY.NS",
            date=date_val,
            timeframe="D",
            rs_score=80,
            is_bullish=True,
            momentum_3m=8,
        )
    )
    db_session.add(
        TechnicalSignal(
            symbol="WIPRO.NS",
            date=date_val,
            timeframe="D",
            rs_score=70,
            is_bullish=False,
            momentum_3m=6,
        )
    )

    db_session.commit()

    compute_sector_rotation(db_session)

    snap = (
        db_session.query(SectorSnapshot)
        .filter_by(sector="Tech", date=date_val.date())
        .first()
    )
    assert snap is not None
    assert snap.avg_rs == 80.0
    assert snap.avg_momentum_3m == 8.0
    assert snap.bullish_pct == pytest.approx(66.66, abs=0.1)
    assert snap.stock_count == 3


def test_screen_hot_sectors(db_session):
    date_val = datetime.datetime(2023, 10, 1, tzinfo=datetime.timezone.utc)

    # Setup hot sector
    db_session.add(SectorSnapshot(date=date_val.date(), sector="Tech", avg_rs=90.0))
    db_session.add(SectorSnapshot(date=date_val.date(), sector="Energy", avg_rs=80.0))
    db_session.add(SectorSnapshot(date=date_val.date(), sector="Banks", avg_rs=70.0))
    db_session.add(SectorSnapshot(date=date_val.date(), sector="Auto", avg_rs=60.0))

    db_session.add(Stock(symbol="TCS.NS", sector="Tech"))
    db_session.add(
        TechnicalSignal(
            symbol="TCS.NS",
            date=date_val,
            timeframe="D",
            rs_score=95,
            is_bullish=True,
            above_200ema=True,
            entry_score=90,
        )
    )

    db_session.add(Stock(symbol="MARUTI.NS", sector="Auto"))
    db_session.add(
        TechnicalSignal(
            symbol="MARUTI.NS",
            date=date_val,
            timeframe="D",
            rs_score=95,
            is_bullish=True,
            above_200ema=True,
            entry_score=90,
        )
    )

    db_session.commit()

    results = screen_hot_sectors(db_session)
    # Tech is top 3, Auto is not (4th)
    assert len(results) == 1
    assert results[0][0] == "TCS.NS"
