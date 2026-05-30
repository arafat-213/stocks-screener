import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import session as db_session_module
from app.db.models import Base
from app.db.session import get_db
from app.main import app

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    # Patch the session module's SessionLocal and engine
    # This ensures background tasks and other direct imports use the test DB
    old_session_local = db_session_module.SessionLocal
    old_engine = db_session_module.engine

    db_session_module.SessionLocal = TestingSessionLocal
    db_session_module.engine = engine

    # Create tables once per session
    Base.metadata.create_all(bind=engine)

    yield

    Base.metadata.drop_all(bind=engine)

    # Restore
    db_session_module.SessionLocal = old_session_local
    db_session_module.engine = old_engine


@pytest.fixture
def db():
    """Provides an isolated database session for a single test."""
    connection = engine.connect()
    # Begin a non-ORM transaction
    transaction = connection.begin()
    # Bind a new session to the connection
    session = TestingSessionLocal(bind=connection)

    # Run the test
    yield session

    # Roll back everything after the test
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    """Provides a TestClient with the get_db dependency overridden to use the test database."""

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_trending_df(
    n: int = 300, base: float = 100.0, trend: float = 0.001
) -> pd.DataFrame:
    """
    Synthetic OHLCV DataFrame with a smooth uptrend and enough history for
    all indicators (EMA-200 needs 200 bars; we add 100 extra for stability).
    Volume is set high enough that volume-breakout signals can fire.
    """
    rng = np.random.default_rng(42)
    dates = pd.date_range("2021-01-01", periods=n, freq="B")
    closes = base * (1 + trend) ** np.arange(n) + rng.normal(0, 0.3, n)
    opens = closes * rng.uniform(0.997, 1.003, n)
    highs = np.maximum(closes, opens) * rng.uniform(1.001, 1.012, n)
    lows = np.minimum(closes, opens) * rng.uniform(0.988, 0.999, n)
    volumes = rng.uniform(1_000_000, 2_500_000, n)
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=dates,
    )


def make_signal(
    df: pd.DataFrame,
    idx: int,
    score: float = 50.0,
    above_200ema: bool = True,
    volume_breakout: bool = False,
    adx: float = 25.0,
    rsi: float = 55.0,
) -> dict:
    """
    Builds a minimal signal dict as returned by score_series, anchored to
    a real row of df so date/index lookups in simulate_trades work correctly.
    """
    return {
        "date": df.index[idx],
        "score": score,
        "is_bullish": True,
        "rsi": rsi,
        "adx": adx,
        "ema_signal": "bullish_cross",
        "volume_signal": "neutral",
        "rsi_signal": "bullish_strong",
        "close": float(df.iloc[idx]["Close"]),
        "open": float(df.iloc[idx]["Open"]),
        "volume_breakout": volume_breakout,
        "atr": float(df.iloc[idx]["Close"]) * 0.015,  # ~1.5% ATR
        "above_200ema": above_200ema,
    }
