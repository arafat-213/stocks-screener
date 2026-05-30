import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, TechnicalSignal
from app.pipeline.utils import get_market_regime

# Use in-memory SQLite for testing
engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


def test_get_market_regime():
    db = SessionLocal()

    # Setup: No signals
    regime = get_market_regime(db, datetime.date(2023, 1, 1))
    assert regime is True, "Should fallback to True if no signal"

    # Setup: Bullish signal
    sig1 = TechnicalSignal(
        symbol="^NSEI", date=datetime.date(2023, 1, 1), timeframe="D", is_bullish=True
    )
    db.add(sig1)
    db.commit()

    regime = get_market_regime(db, datetime.date(2023, 1, 1))
    assert regime is True, "Should be True for bullish signal"

    # Setup: Bearish signal on later date
    sig2 = TechnicalSignal(
        symbol="^NSEI", date=datetime.date(2023, 1, 2), timeframe="D", is_bullish=False
    )
    db.add(sig2)
    db.commit()

    regime = get_market_regime(db, datetime.date(2023, 1, 2))
    assert regime is False, "Should be False for bearish signal"

    regime = get_market_regime(db, datetime.date(2023, 1, 1))
    assert regime is True, "Should be True for 2023-01-01 (latest prior)"

    print("test_get_market_regime PASSED")
    db.close()


if __name__ == "__main__":
    test_get_market_regime()
