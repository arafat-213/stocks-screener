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
            signal_date=paper_pos.signal_date,
            signal_score=paper_pos.signal_score,
            status="pending" if paper_pos.status == "pending" else "open",
            entry_price=0.0,
            strategy_tags=paper_pos.strategy_tags,
            position_value=0.0,
        )
        db.add(journal)

    # Sync state-specific fields
    if paper_pos.status == "pending":
        journal.status = "pending"
        journal.entry_price = paper_pos.ema20_at_signal or 0.0  # Target price
        journal.shares = 0
        journal.position_value = 0.0

    elif paper_pos.status == "open":
        journal.status = "open"
        journal.entry_date = paper_pos.entry_date
        journal.entry_price = paper_pos.entry_price or 0.0
        journal.shares = int(paper_pos.shares or 0)
        journal.position_value = (paper_pos.entry_price or 0) * (paper_pos.shares or 0)
        journal.stop_loss = paper_pos.stop_loss_price
        journal.target = paper_pos.target_price

    elif paper_pos.status in ["closed", "expired"]:
        journal.status = "closed"
        journal.exit_date = paper_pos.closed_at.date() if paper_pos.closed_at else None
        journal.exit_price = paper_pos.exit_price
        journal.exit_reason = paper_pos.exit_reason

        # Sync PnL and metrics for visibility in closed journal
        if (
            paper_pos.exit_price is not None
            and paper_pos.entry_price is not None
            and paper_pos.shares is not None
        ):
            journal.pnl = (
                paper_pos.exit_price - paper_pos.entry_price
            ) * paper_pos.shares
            if paper_pos.entry_price > 0:
                journal.return_pct = round(
                    (
                        (paper_pos.exit_price - paper_pos.entry_price)
                        / paper_pos.entry_price
                    )
                    * 100,
                    2,
                )

        if paper_pos.entry_date and paper_pos.closed_at:
            delta = paper_pos.closed_at.date() - paper_pos.entry_date
            journal.holding_days = delta.days

    db.commit()
