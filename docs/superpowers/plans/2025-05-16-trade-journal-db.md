# Trade Journal Database Model & Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `TradeJournal` database model and run the migration.

**Architecture:** Add `TradeJournal` to `models.py` and use Alembic to create the table in PostgreSQL.

**Tech Stack:** SQLAlchemy, Alembic, PostgreSQL.

---

### Task 1: Database Model & Migration

**Files:**
- Modify: `backend/app/db/models.py`
- Create: Alembic migration (auto-generated)

- [ ] **Step 1: Add TradeJournal model to models.py**

Modify `backend/app/db/models.py` to include the `TradeJournal` class.

```python
class TradeJournal(Base):
    __tablename__ = "trade_journal"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    watchlist_id = Column(Integer, ForeignKey('watchlist.id'), nullable=True)

    # Entry
    signal_date = Column(Date, nullable=True)
    entry_date = Column(Date, nullable=False, default=datetime.date.today)
    entry_price = Column(Float, nullable=False)
    shares = Column(Integer, nullable=False)
    position_value = Column(Float, nullable=False)

    # Risk Management
    stop_loss = Column(Float, nullable=False)
    target = Column(Float, nullable=False)
    quality_tier = Column(String(1), nullable=True)
    signal_score = Column(Float, nullable=True)

    # Exit
    exit_date = Column(Date, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True) # 'stop', 'target', 'manual', 'trail'
    pnl = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)

    status = Column(String, nullable=False, default='open') # 'open' | 'closed'
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        Index('ix_tj_status', 'status'),
        Index('ix_tj_symbol', 'symbol'),
    )
```

- [ ] **Step 2: Generate Alembic migration**

Run: `cd backend && alembic revision --autogenerate -m "add_trade_journal_table"`
Expected: Success, new file in `backend/migrations/versions/`.

- [ ] **Step 3: Run Alembic migration**

Run: `cd backend && alembic upgrade head`
Expected: Success, table created.

- [ ] **Step 4: Verify table creation**

Run: `export PGPASSWORD=postgres && psql -h localhost -U postgres -d stock_ai -c "\dt trade_journal"`
Expected: `trade_journal` table listed.

- [ ] **Step 5: Commit changes**

```bash
git add backend/app/db/models.py backend/migrations/versions/*.py
git commit -m "db: add trade_journal table"
```
