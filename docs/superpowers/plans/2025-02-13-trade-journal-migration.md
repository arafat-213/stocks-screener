# Database Migration: Trade Journal Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `source` and `external_id` columns to the `trade_journal` table to support integration with paper trading.

**Architecture:** Update the SQLAlchemy model in `backend/app/db/models.py` and generate a migration using Alembic.

**Tech Stack:** Python, SQLAlchemy, Alembic, PostgreSQL.

---

### Task 1: Update SQLAlchemy Model

**Files:**
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Add columns to TradeJournal class**

```python
# Around line 409
class TradeJournal(Base):
    __tablename__ = "trade_journal"
    # ... existing fields ...
    source = Column(String, nullable=False, default="manual")  # 'manual' | 'paper'
    external_id = Column(Integer, nullable=True)  # Links to PaperPosition.id
```

- [ ] **Step 2: Commit model changes**

```bash
git add backend/app/db/models.py
git commit -m "models: add source and external_id to TradeJournal"
```

### Task 2: Generate and Run Migration

**Files:**
- Create: `backend/migrations/versions/<timestamp>_add_source_to_journal.py`

- [ ] **Step 1: Generate Alembic revision**

Run: `cd backend && ./venv/bin/alembic revision --autogenerate -m "add_source_and_external_id_to_journal"`
Expected: New migration file created in `backend/migrations/versions/`.

- [ ] **Step 2: Apply migration**

Run: `cd backend && ./venv/bin/alembic upgrade head`
Expected: INFO [alembic.runtime.migration] Running upgrade <old_head> -> <new_head>, add_source_and_external_id_to_journal

- [ ] **Step 3: Commit migration file**

```bash
git add backend/migrations/versions/
git commit -m "db: migration for trade_journal source and external_id"
```

### Task 3: Verification

- [ ] **Step 1: Verify database schema**

Run: `export PGPASSWORD=postgres && psql -h localhost -U postgres -d stock_ai -c "\d trade_journal"`
Expected: Columns `source` (character varying, NOT NULL, default 'manual') and `external_id` (integer) exist.
