# Design Doc: Stock Watchlist & Live Tracking

**Date:** 2026-05-24
**Topic:** Watchlist
**Status:** Draft

## 1. Problem Statement
The current system alerts users to technical signals, but there is no native way to track these signals over the following days. Users must manually monitor whether a stock enters its "entry zone" or if the signal has expired (8 trading days). This leads to missed opportunities and difficulty in reviewing past signal performance.

## 2. Goals
- Provide a lightweight table (Watchlist) to track signals the user intends to act on.
- Automatically calculate "Trading Days Elapsed" using precise market session data.
- Show current price vs. Entry Zone / EMA20 status live without re-running the full pipeline.
- Allow simple state management (Watching, Entered, Skipped, Expired).

## 3. Architecture & Data Flow

### 3.1 Data Model (SQLAlchemy)
```python
class Watchlist(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, ForeignKey('stocks.symbol'), nullable=False)
    added_date = Column(Date, nullable=False, default=datetime.date.today)
    signal_date = Column(Date, nullable=False)

    # Snapshot of signal metadata at time of addition
    alert_type = Column(String, nullable=True)
    quality_tier = Column(String(1), nullable=True)
    signal_score = Column(Float, nullable=True)
    planned_entry_low = Column(Float, nullable=True)
    planned_entry_high = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default='watching') # 'watching', 'entered', 'skipped', 'expired'

    __table_args__ = (
        UniqueConstraint('symbol', 'signal_date'),
        Index('ix_watchlist_status', 'status'),
    )
```

### 3.2 Live Calculation Logic
The `GET /watchlist` endpoint will perform the following "Compute on Read" steps for items where `status == 'watching'`:
1.  **Fetch OHLCV:** Load recent history from `OHLCVCache`.
2.  **Calculate Session Count:** Filter dataframe for `index > signal_date`. The count of rows is the `trading_days_elapsed`.
3.  **Calculate Live EMA20:** Compute EMA20 on the latest data.
4.  **Auto-Expiration:** If `trading_days_elapsed > 8`, the API will return the status as `expired` and trigger a background task or inline update to mark it as such in the DB.
5.  **Zone Status:**
    *   `current_price` = latest close from OHLCV.
    *   `in_zone` = `planned_entry_low <= current_price <= planned_entry_high`.
    *   `vs_ema20` = `(current_price - ema20) / ema20 * 100`.

### 3.3 API Endpoints
- `POST /api/watchlist`:
    - Payload: `{symbol, signal_date}`.
    - Action: Fetches metadata from `TechnicalSignal` table for that symbol/date. If not found, uses default values or fails.
- `GET /api/watchlist`:
    - Returns: List of items with `status='watching'`, enriched with live computed fields.
- `PATCH /api/watchlist/{id}/status`:
    - Payload: `{status: 'entered' | 'skipped'}`.
- `GET /api/watchlist/expired`:
    - Returns: History of items with `status='expired'` or `status='skipped'`.

## 4. UI/UX (Frontend)
- **Watchlist Tab:** A new top-level navigation or dashboard section.
- **Table Columns:** Symbol, Signal Date, Days Elapsed (1-8), Entry Zone (Price vs Zone Range), Live Price vs EMA20, Quality, Actions.
- **Actions:** Buttons for "Enter Trade" (moves to Paper Trading or simply marks as entered) and "Skip/Dismiss".

## 5. Security & Constraints
- **Personal Use:** No multi-user authentication required.
- **Stock Symbols:** Must continue using `.NS` suffix for NSE stocks internally.
- **Data Integrity:** Prevent duplicate `symbol + signal_date` entries.

## 6. Testing Strategy
- **Unit Tests:** Verify trading day calculation with mock OHLCV data (including weekends/holidays).
- **API Tests:** Verify that `POST` correctly pulls metadata from `TechnicalSignal`.
- **Integration Tests:** Ensure `OHLCVCache` correctly triggers incremental fetches during `GET /watchlist`.
