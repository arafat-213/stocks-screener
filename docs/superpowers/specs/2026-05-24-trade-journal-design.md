# Design Spec: Stage 6 — Position Tracking (Trade Journal)

## Overview
A manual trade journal to track actual execution, live P&L, and performance metrics. It bridges the gap between the system's signals and the user's manual brokerage execution.

## 1. Database Model (`backend/app/db/models.py`)

```python
class TradeJournal(Base):
    __tablename__ = "trade_journal"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    watchlist_id = Column(Integer, ForeignKey('watchlist.id'), nullable=True) # Bridge link

    # Entry
    signal_date = Column(Date, nullable=True)
    entry_date = Column(Date, nullable=False, default=datetime.date.today)
    entry_price = Column(Float, nullable=False)
    shares = Column(Integer, nullable=False)
    position_value = Column(Float, nullable=False) # Computed: entry_price * shares

    # Risk Management (Pre-filled from signal if available)
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

## 2. API Router (`backend/app/routers/journal.py`)

### `GET /open` (The Live View)
1. Query all `TradeJournal` records where `status='open'`.
2. For each symbol:
    - Check `OHLCVCache` for today's price.
    - If cache missing or >1 hour old (during market hours), fetch latest quote via `yfinance`.
    - Compute `unrealized_pnl` and `dist_to_stop`/`dist_to_target`.
3. Return list with live metrics.

### `PATCH /{id}/close`
1. Accepts `exit_price`, `exit_date`, and `exit_reason`.
2. Computes `pnl = (exit_price - entry_price) * shares`.
3. Computes `return_pct` and `holding_days`.
4. Sets `status='closed'`.
5. Updates the linked `Watchlist` item (if any) to `status='closed'`.

## 3. Frontend Integration

### `Journal.jsx`
- **Stats Bar:** Total Realised P&L, Open Unrealised P&L, Win Rate.
- **Open Positions Table:** Symbol, Entry, Current Price, Live P&L (%), Stop/Target status.
- **Trade History Table:** Symbol, Entry/Exit, P&L (abs/%), Reason.

### The "Bridge" in `Watchlist.jsx`
- Replace "Entered" checkbox with a "Log Trade" button.
- Button navigates to `/journal/new?symbol=...&price=...&sl=...&target=...`.
- The New Trade form pre-fills these params into the input fields.

## 4. Performance Metrics (`/journal/stats`)
- **Win Rate:** Closed winning trades / Total closed trades.
- **Profit Factor:** Sum(Wins) / Sum(Losses).
- **Avg Return %:** Mean of `return_pct` for all closed trades.
- **Slippage Analysis:** Average difference between `signal_price` and `actual_entry_price`.
