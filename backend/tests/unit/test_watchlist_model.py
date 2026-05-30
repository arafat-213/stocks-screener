import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Stock, Watchlist

# Use in-memory SQLite for testing the model mapping
DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture
def session():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_watchlist_model_mapping(session):
    # First, need a stock for the foreign key if it was strictly enforced,
    # but SQLite doesn't enforce it by default unless configured.
    # However, let's add it for completeness if we were using a real DB.
    stock = Stock(symbol="RELIANCE.NS", name="Reliance Industries")
    session.add(stock)
    session.commit()

    watchlist_item = Watchlist(
        symbol="RELIANCE.NS",
        signal_date=datetime.date.today(),
        alert_type="tier1_entry",
        quality_tier="A",
        signal_score=85.5,
        status="watching",
    )
    session.add(watchlist_item)
    session.commit()

    retrieved = session.query(Watchlist).filter_by(symbol="RELIANCE.NS").first()
    assert retrieved is not None
    assert retrieved.symbol == "RELIANCE.NS"
    assert retrieved.quality_tier == "A"
    assert retrieved.status == "watching"
    assert retrieved.added_date == datetime.date.today()
