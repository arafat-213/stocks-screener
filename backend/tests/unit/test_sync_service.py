# backend/tests/unit/test_sync_service.py
import datetime

from app.backtest.sync_service import sync_paper_to_journal
from app.db import models


def test_sync_new_position(db):
    paper_pos = models.PaperPosition(
        id=999,
        portfolio_id=1,
        symbol="RELIANCE.NS",
        status="open",
        entry_price=2500.0,
        shares=10,
        entry_date=datetime.date(2024, 1, 1),
        signal_date=datetime.date(2024, 1, 1),
    )
    # We don't need to add it to DB for the function to work,
    # but the function might query it if it's not passed as an object?
    # No, it's passed as an object.

    # We might need to mock or provide dependencies if sync_paper_to_journal expects them.
    sync_paper_to_journal(db, paper_pos)

    journal_entry = db.query(models.TradeJournal).filter_by(external_id=999).first()
    assert journal_entry is not None
    assert journal_entry.source == "paper"
    assert journal_entry.symbol == "RELIANCE.NS"
    assert journal_entry.entry_price == 2500.0
    assert journal_entry.shares == 10
    assert journal_entry.status == "open"


def test_sync_closed_position(db):
    paper_pos = models.PaperPosition(
        id=888,
        portfolio_id=1,
        symbol="TCS.NS",
        status="closed",
        entry_price=3500.0,
        shares=5,
        entry_date=datetime.date(2024, 1, 1),
        signal_date=datetime.date(2024, 1, 1),
        closed_at=datetime.datetime(2024, 1, 15, 15, 30),
        exit_price=3800.0,
        exit_reason="target",
    )

    # First sync as open (simulating it was already in journal)
    open_pos = models.PaperPosition(
        id=888,
        portfolio_id=1,
        symbol="TCS.NS",
        status="open",
        entry_price=3500.0,
        shares=5,
        entry_date=datetime.date(2024, 1, 1),
        signal_date=datetime.date(2024, 1, 1),
    )
    sync_paper_to_journal(db, open_pos)

    # Now sync as closed
    sync_paper_to_journal(db, paper_pos)

    journal_entry = db.query(models.TradeJournal).filter_by(external_id=888).first()
    assert journal_entry is not None
    assert journal_entry.status == "closed"
    assert journal_entry.exit_price == 3800.0
    assert journal_entry.exit_date == datetime.date(2024, 1, 15)
    assert journal_entry.exit_reason == "target"
