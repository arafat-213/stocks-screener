import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.backtest.sync_service import sync_paper_to_journal
from app.db import models
from app.main import app
from app.paper_trading.engine import process_pending_orders, scan_for_new_signals

client = TestClient(app)


def test_sync_pending_position(db: Session):
    paper_pos = models.PaperPosition(
        id=1001,
        portfolio_id=1,
        symbol="INFY.NS",
        status="pending",
        ema20_at_signal=1500.0,
        signal_date=datetime.date(2024, 1, 1),
    )

    sync_paper_to_journal(db, paper_pos)

    journal_entry = (
        db.query(models.TradeJournal)
        .filter_by(external_id=1001, source="paper")
        .first()
    )
    assert journal_entry is not None
    assert journal_entry.status == "pending"
    assert journal_entry.entry_price == 1500.0
    assert journal_entry.shares == 0
    assert journal_entry.position_value == 0


def test_sync_transition_pending_to_open(db: Session):
    # Setup pending in journal
    paper_pos = models.PaperPosition(
        id=1002,
        portfolio_id=1,
        symbol="SBIN.NS",
        status="pending",
        ema20_at_signal=600.0,
        signal_date=datetime.date(2024, 1, 1),
    )
    sync_paper_to_journal(db, paper_pos)

    # Transition to open
    paper_pos.status = "open"
    paper_pos.entry_price = 610.0
    paper_pos.shares = 100
    paper_pos.position_size = 61000.0
    paper_pos.entry_date = datetime.date(2024, 1, 5)
    paper_pos.stop_loss_price = 580.0
    paper_pos.target_price = 650.0

    sync_paper_to_journal(db, paper_pos)

    journal_entry = (
        db.query(models.TradeJournal)
        .filter_by(external_id=1002, source="paper")
        .first()
    )
    assert journal_entry.status == "open"
    assert journal_entry.entry_price == 610.0
    assert journal_entry.shares == 100
    assert journal_entry.position_value == 61000.0
    assert journal_entry.stop_loss == 580.0
    assert journal_entry.target == 650.0


def test_sync_expired_position(db: Session):
    # Setup pending in journal
    paper_pos = models.PaperPosition(
        id=1003,
        portfolio_id=1,
        symbol="HDFCBANK.NS",
        status="pending",
        ema20_at_signal=1600.0,
        signal_date=datetime.date(2024, 1, 1),
    )
    sync_paper_to_journal(db, paper_pos)

    # Transition to expired
    paper_pos.status = "expired"
    paper_pos.closed_at = datetime.datetime(2024, 1, 10, 10, 0)
    paper_pos.exit_reason = "invalidated"

    sync_paper_to_journal(db, paper_pos)

    journal_entry = (
        db.query(models.TradeJournal)
        .filter_by(external_id=1003, source="paper")
        .first()
    )
    assert journal_entry.status == "closed"
    assert journal_entry.exit_date == datetime.date(2024, 1, 10)
    assert journal_entry.exit_reason == "invalidated"


@patch("app.paper_trading.engine.get_market_regime")
@patch("app.paper_trading.engine.sync_paper_to_journal")
def test_scan_calls_sync(mock_sync, mock_regime, db: Session):
    mock_regime.return_value = True  # Bullish

    # Create a stock
    stock = models.Stock(symbol="TEST.NS", name="Test", sector="IT")
    db.add(stock)

    # Create a signal
    today = datetime.date(2024, 1, 1)
    sig = models.TechnicalSignal(
        date=datetime.datetime.combine(today, datetime.time(10, 0)),
        symbol="TEST.NS",
        timeframe="D",
        above_200ema=True,
        entry_score=80.0,
        ema_signal="bullish_cross",
        ema20_level=100.0,
        atr=5.0,
    )
    db.add(sig)
    db.commit()

    with patch("app.paper_trading.engine._ohlcv_cache.get") as mock_get:
        import pandas as pd

        mock_df = pd.DataFrame(
            {
                "Low": [95.0] * 20,
                "High": [105.0] * 20,
                "Close": [100.0] * 20,
                "Open": [100.0] * 20,
            },
            index=pd.date_range(start="2023-12-01", periods=20, freq="D"),
        )
        mock_get.return_value = mock_df

        scan_for_new_signals(db, today)

        assert mock_sync.called


@patch("app.paper_trading.engine.sync_paper_to_journal")
def test_process_pending_expiration_calls_sync(mock_sync, db: Session):
    portfolio = models.PaperPortfolio(id=1, is_active=True)
    db.add(portfolio)
    db.flush()

    pos = models.PaperPosition(
        portfolio_id=1,
        symbol="EXPIRE.NS",
        status="pending",
        wait_days_elapsed=10,  # already over limit
        signal_date=datetime.date(2024, 1, 1),
        ema20_at_signal=100.0,
        pending_highest_closeness_pct=20.0,  # way too far
    )
    db.add(pos)
    db.commit()

    with patch("app.paper_trading.engine._ohlcv_cache.get") as mock_get:
        import pandas as pd

        today = datetime.date(2024, 1, 15)
        mock_df = pd.DataFrame(
            {
                "Low": [120.0],
                "High": [130.0],
                "Close": [125.0],
                "Open": [125.0],
                "EMA_20": [100.0],
            },
            index=[pd.Timestamp(today)],
        )
        mock_get.return_value = mock_df

        process_pending_orders(db, today)

        assert pos.status == "expired"
        assert mock_sync.called
