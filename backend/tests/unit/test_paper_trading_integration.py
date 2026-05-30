import datetime
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.db import models
from app.paper_trading.engine import _convert_to_open, update_open_positions


def test_convert_to_open_calls_sync(db: Session):
    # Mocking sync_paper_to_journal to verify it's called
    with patch("app.paper_trading.engine.sync_paper_to_journal") as mock_sync:
        # Create a dummy PaperPosition
        pos = models.PaperPosition(
            symbol="RELIANCE.NS",
            status="pending",
            atr_at_signal=10.0,
            wait_days_elapsed=0,
        )
        # Mock OHLCV Cache to avoid real data fetching
        with patch("app.paper_trading.engine._ohlcv_cache.get") as mock_get:
            import pandas as pd

            mock_df = pd.DataFrame(
                {
                    "Low": [2400.0] * 20,
                    "High": [2600.0] * 20,
                    "Close": [2500.0] * 20,
                    "Open": [2500.0] * 20,
                },
                index=pd.date_range(start="2024-01-01", periods=20, freq="D"),
            )
            mock_get.return_value = mock_df

            _convert_to_open(
                db,
                pos,
                entry_price=2500.0,
                entry_type="pullback_a",
                today=datetime.date(2024, 1, 20),
            )

            assert pos.status == "open"
            assert mock_sync.called
            mock_sync.assert_called_with(db, pos)


def test_update_open_positions_calls_sync(db: Session):
    # Setup: Create a portfolio and an open position
    portfolio = models.PaperPortfolio(name="test", is_active=True)
    db.add(portfolio)
    db.flush()

    pos = models.PaperPosition(
        portfolio_id=portfolio.id,
        symbol="RELIANCE.NS",
        status="open",
        signal_date=datetime.date(2023, 12, 31),
        entry_price=2500.0,
        shares=10,
        position_size=25000.0,
        entry_date=datetime.date(2024, 1, 1),
        highest_price=2500.0,
        stop_loss_price=2400.0,
        target_price=2800.0,
    )
    db.add(pos)
    db.commit()

    # Mocking sync_paper_to_journal to verify it's called
    with patch("app.paper_trading.engine.sync_paper_to_journal") as mock_sync:
        with patch("app.paper_trading.engine._ohlcv_cache.get") as mock_get:
            import pandas as pd

            # Trigger stop loss
            mock_df = pd.DataFrame(
                {
                    "Low": [2350.0],
                    "High": [2450.0],
                    "Close": [2400.0],
                    "Open": [2400.0],
                },
                index=[pd.Timestamp("2024-01-02")],
            )
            mock_get.return_value = mock_df

            update_open_positions(db, today=datetime.date(2024, 1, 2))

            db.refresh(pos)
            assert pos.status == "closed"
            assert pos.exit_reason == "stop_loss"
            assert mock_sync.called
            mock_sync.assert_called_with(db, pos)
