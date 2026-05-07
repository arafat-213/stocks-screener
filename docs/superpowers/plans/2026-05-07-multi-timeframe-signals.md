# Multi-Timeframe Signal Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a scoring engine that analyzes stocks across Daily, Weekly, and Monthly timeframes to identify confluence-based buy signals.

**Architecture:** Refactor the database to store timeframe-specific signals, implement OHLCV resampling with pandas, and update the scoring logic to use tiered thresholds per timeframe.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, pandas, pandas-ta.

---

### Task 1: Database Migration

**Files:**
- Create: `backend/migrations/versions/<timestamp>_refactor_signals_table.py`
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Create the Alembic migration script**

Run: `alembic revision -m "refactor signals table for multi-timeframe"`

- [ ] **Step 2: Implement the migration logic**

Use `batch_alter_table` for safe constraint handling (especially for SQLite/Postgres compatibility).
```python
# In the generated migration file
def upgrade():
    # 1. Rename table
    op.rename_table('daily_scores', 'technical_signals')
    
    # 2. Add columns and constraints
    with op.batch_alter_table('technical_signals') as batch_op:
        batch_op.add_column(sa.Column('id', sa.Integer(), autoincrement=True, nullable=True))
        batch_op.add_column(sa.Column('timeframe', sa.String(length=1), nullable=True))
        batch_op.add_column(sa.Column('is_bullish', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('rsi_signal', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('scored_at', sa.DateTime(), nullable=True))

    # 3. Backfill
    op.execute("UPDATE technical_signals SET timeframe = 'D', is_bullish = (ema_signal = 'bullish'), scored_at = date")

    # 4. Handle Primary Key and Unique Constraint
    # Note: Must drop old PK constraint (usually 'daily_scores_pkey') first
    op.execute("ALTER TABLE technical_signals DROP CONSTRAINT daily_scores_pkey")
    op.create_primary_key('pk_technical_signals', 'technical_signals', ['id'])
    op.create_unique_constraint('uq_symbol_date_tf', 'technical_signals', ['symbol', 'date', 'timeframe'])
```

- [ ] **Step 3: Update SQLAlchemy Model**

Modify `backend/app/db/models.py`:
```python
class TechnicalSignal(Base):
    __tablename__ = "technical_signals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False)
    symbol = Column(String, nullable=False)
    timeframe = Column(String(1), nullable=False) # 'D', 'W', 'M'
    is_bullish = Column(Boolean, nullable=False, default=False)
    entry_score = Column(Float)
    rsi = Column(Float)
    macd = Column(Float)
    ema_signal = Column(String)
    volume_signal = Column(String)
    rsi_signal = Column(String)
    scored_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    __table_args__ = (UniqueConstraint('symbol', 'date', 'timeframe'),)
```

- [ ] **Step 4: Run migration and verify**

Run: `alembic upgrade head`

- [ ] **Step 5: Commit**

### Task 2: Resampling Utility

**Files:**
- Modify: `backend/app/pipeline/utils.py`
- Create: `backend/tests/unit/test_resample.py`

- [ ] **Step 1: Write failing test for resampling**

Verify volume is summed and incomplete candles are dropped by default.

- [ ] **Step 2: Implement `resample_ohlcv`**

```python
def resample_ohlcv(df: pd.DataFrame, freq: str, drop_incomplete: bool = True) -> pd.DataFrame:
    ohlcv_agg = {
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }
    resampled = df.resample(freq).agg(ohlcv_agg).dropna()
    return resampled.iloc[:-1] if drop_incomplete else resampled
```

- [ ] **Step 3: Verify tests pass**

- [ ] **Step 4: Commit**

### Task 3: Multi-Timeframe Scorer

**Files:**
- Modify: `backend/app/pipeline/scorer.py`
- Create: `backend/tests/unit/test_scorer_mtf.py`

- [ ] **Step 1: Write failing tests for tiered logic**

- [ ] **Step 2: Refactor `calculate_technical_score`**

Add `timeframe` parameter and implement tiered `is_bullish` logic (RSI > 50 for W/M):
```python
def calculate_technical_score(df: pd.DataFrame, timeframe: str = 'D') -> dict:
    # ... indicator calc ...
    price = latest.get('Close')
    if timeframe == 'D':
        is_bullish = (macd_line > signal_line and macd_line > 0 and ema5 > ema13 > ema26)
    elif timeframe == 'W':
        is_bullish = (rsi > 50 and price > ema26)
    elif timeframe == 'M':
        is_bullish = (rsi > 50 and (price > ema13 or price > ema26))
    # ...
```

- [ ] **Step 3: Update `calculate_combined_score`**

Skip fundamental score if `timeframe != 'D'`.

- [ ] **Step 4: Verify tests pass**

- [ ] **Step 5: Commit**

### Task 4: Orchestrator Update

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Update fetcher call to use `period="3y"`**

- [ ] **Step 2: Implement multi-timeframe loop and explicit upsert**

```python
scored_at = datetime.datetime.utcnow()
for tf, freq in [('D', None), ('W', 'W-FRI'), ('M', 'ME')]:
    working_df = hist if tf == 'D' else resample_ohlcv(hist, freq)
    if working_df.empty: continue
    
    signal_date = working_df.index[-1].date()
    ta_data = calculate_combined_score(working_df, info, timeframe=tf)
    
    # Explicit Upsert Pattern
    signal = db.query(TechnicalSignal).filter_by(
        symbol=symbol, date=signal_date, timeframe=tf
    ).first()
    if not signal:
        signal = TechnicalSignal(symbol=symbol, date=signal_date, timeframe=tf)
        db.add(signal)
    
    signal.entry_score = ta_data['score']
    signal.is_bullish = ta_data['is_bullish']
    signal.rsi = ta_data['rsi']
    signal.macd = ta_data['macd']
    signal.ema_signal = ta_data['ema_signal']
    signal.volume_signal = ta_data['volume_signal']
    signal.rsi_signal = ta_data['rsi_signal']
    signal.scored_at = scored_at
```

- [ ] **Step 3: Commit**

### Task 5: Reporter Update

**Files:**
- Modify: `backend/app/pipeline/reporter.py`

- [ ] **Step 1: Update query to calculate confluence using `scored_at`**

```python
# Conceptual query logic
results = (
    db.query(
        TechnicalSignal.symbol,
        func.sum(case((TechnicalSignal.is_bullish == True, 1), else_=0)).label('confluence_count'),
        func.max(case((TechnicalSignal.timeframe == 'D', TechnicalSignal.entry_score), else_=0)).label('daily_score')
    )
    .filter(func.date(TechnicalSignal.scored_at) == today)
    .group_by(TechnicalSignal.symbol)
    .order_by(text('confluence_count DESC'), text('daily_score DESC'))
    .limit(20)
    .all()
)
```

- [ ] **Step 2: Update report output**

Add a "Confluence" column to the Markdown table.

- [ ] **Step 3: Commit**

### Task 4: Integration Verification

- [ ] **Step 1: Run full pipeline on a small subset of stocks**
- [ ] **Step 2: Verify `technical_signals` table has D, W, M rows**
- [ ] **Step 3: Verify report shows confluence scores**
