# backend/app/backtest/sync_service.py
from sqlalchemy.orm import Session

from app.db import models


def sync_paper_to_journal(db: Session, paper_pos: models.PaperPosition):
    journal = (
        db.query(models.TradeJournal)
        .filter_by(source="paper", external_id=paper_pos.id)
        .first()
    )

    if not journal:
        journal = models.TradeJournal(
            source="paper",
            external_id=paper_pos.id,
            symbol=paper_pos.symbol,
            entry_date=paper_pos.entry_date,
            entry_price=paper_pos.entry_price,
            shares=int(paper_pos.shares or 0),
            position_value=(paper_pos.entry_price or 0) * (paper_pos.shares or 0),
            status="open",
        )
        db.add(journal)

    # Sync updates/exits
    if paper_pos.status == "closed":
        journal.status = "closed"
        journal.exit_date = paper_pos.closed_at.date() if paper_pos.closed_at else None
        journal.exit_price = paper_pos.exit_price
        journal.exit_reason = paper_pos.exit_reason

    db.commit()
