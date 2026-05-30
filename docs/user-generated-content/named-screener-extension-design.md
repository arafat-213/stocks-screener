# Named Screener Extension Design

## Goal

Extend the existing two-tier pipeline into a general-purpose screener platform. The pipeline becomes a screen-agnostic data enrichment engine that computes and persists a rich set of signals daily. Named screens (e.g., Momentum Monsters, Near Breakout, Steady Compounders) are defined as query functions over that persisted data, not as separate pipeline runs. The frontend calls a screen by slug and receives a pre-shaped result list.

---

## Architecture

### 1. Database Schema — New and Modified Tables

#### 1a. Modified: `technical_signals`

Add the following columns to the existing table to support momentum, trend quality, and breakout detection screens:

- `momentum_1m`: Float — price return over last 1 month (%).
- `momentum_3m`: Float — price return over last 3 months (%).
- `momentum_6m`: Float — price return over last 6 months (%).
- `rs_score`: Float — relative strength percentile rank (0–100) vs. Nifty 500, computed over trailing 12 months.
- `adx`: Float — Average Directional Index (14-period), measures trend strength.
- `above_200ema`: Boolean — whether Close > EMA200 on signal date.
- `ema_slope_20`: Float — slope of EMA20 over last 5 bars (positive = rising).
- `pct_from_52w_high`: Float — percentage distance of current close from the 52-week high (negative = below high).
- `pct_from_52w_low`: Float — percentage distance of current close from the 52-week low.
- `week52_high`: Float — highest close over the trailing 52 weeks.
- `week52_low`: Float — lowest close over the trailing 52 weeks.
- `resistance_level`: Float — highest close in the 52 weeks prior to last pullback, used for breakout proximity.
- `pct_from_resistance`: Float — how far current price is below `resistance_level` (%).
- `volume_breakout`: Boolean — True if volume > 2× 20-day average on a green (up) day.

#### 1b. Modified: `fundamental_cache`

Add the following columns to support value, quality, and dividend-based screens. These are refreshed on the existing 7-day cache cycle.

- `roce`: Float — Return on Capital Employed (EBIT / Capital Employed). Derivable from yfinance financials + balance sheet.
- `peg_ratio`: Float — PE ratio divided by 3-year EPS growth rate. Identifies growth at a reasonable price.
- `ev_to_ebitda`: Float — sourced directly from `info.get('enterpriseToEbitda')`.
- `dividend_yield`: Float — sourced from `info.get('dividendYield')`.
- `price_to_fcf`: Float — Market Cap / Free Cash Flow. FCF derivable from `cashflow` statement.
- `earnings_growth_3y`: Float — CAGR of net income over the last 3 annual periods (already fetched in Tier 2).
- `fcf_positive`: Boolean — True if Free Cash Flow was positive in the last fiscal year.
- `dividend_consistency`: Boolean — True if the stock paid a dividend in each of the last 3 years. Requires `ticker.dividends` history.
- `market_cap_category`: String — `'largecap'`, `'midcap'`, or `'smallcap'` based on `marketCap` thresholds (Large > ₹20,000 Cr, Mid ₹5,000–20,000 Cr, Small < ₹5,000 Cr).

#### 1c. New: `screen_results`

Materialized output table populated at the end of each pipeline run. Avoids recomputing screens on every API request.

- `id`: Integer, Primary Key.
- `screen_slug`: String — e.g., `'momentum-monsters'`.
- `symbol`: String, ForeignKey(`stocks.symbol`).
- `rank`: Integer — position within the screen result.
- `score_used`: Float — the primary sort metric for the given screen.
- `computed_at`: DateTime — timestamp of the pipeline run that produced this row.

**Constraint:** `UniqueConstraint('screen_slug', 'symbol', 'computed_at')`.

> Note: The API reads from this table by default. A `?live=true` query param can bypass it and run the screen function directly against `technical_signals` and `fundamental_cache` — useful for development and testing.

---

### 2. Pipeline Changes — Decoupled Enrichment

#### 2a. Loosen Tier 1 Hard Filters

The current Tier 1 applies ROE and Promoter Pledge as hard gates. These must move to screen-level filters. The revised Tier 1 only excludes structurally invalid candidates:

| Filter | Current Threshold | New Threshold | Reason for Change |
|---|---|---|---|
| Market Cap | > ₹500 Cr | > ₹200 Cr | Capture small-caps for dedicated screens |
| P/E | 0 < PE < 150 | 0 < PE < 300 | High-growth stocks may have elevated PE legitimately |
| ROE | > 15% | **Removed** | Belongs in quality screens, not the gate |
| Promoter Pledge | < 20% | **Removed** | Belongs in screen filters |
| Liquidity | Avg Vol × Price > ₹5 Cr | ₹2 Cr | Widen to catch mid/small-cap candidates |

Tier 2 (profitability streak, D/E check) is retained as a data field (`profitability_streak_passed`, `de_check_passed`) but should no longer be a hard skip gate in the orchestrator. The orchestrator scores all Tier 1 survivors; screens then filter by these flags as needed.

#### 2b. Extended `scorer.py` — New Computed Fields

The `calculate_technical_score` function is extended to also return the new fields. All new computations reuse the same `df` copy that is already in scope:

```
52w stats:        df['Close'].rolling(252)
Momentum:         (close_now / close_N_bars_ago - 1) * 100
ADX:              df.ta.adx(length=14, append=True)  → column ADX_14
EMA200:           df.ta.ema(length=200, append=True) → column EMA_200
EMA slope:        (EMA_20.iloc[-1] - EMA_20.iloc[-6]) / 5
Resistance:       max close over bars [-260:-20] approx (prior year, ex last month)
Volume breakout:  volume > 2 × VOL_SMA_20 and Close > Open
RS score:         computed in orchestrator against Nifty 500 (see §2c)
```

All new fields are included in the dict returned by `calculate_technical_score` and persisted by the orchestrator in the same signal upsert block. No new function is required; the existing return dict is extended.

#### 2c. Relative Strength Score — Orchestrator-Level Computation

RS Score cannot be computed per-stock in isolation. It requires ranking all stocks against each other after individual scores are known. The orchestrator handles this as a post-scoring step:

1. After all symbols are scored, collect `momentum_12m` for each symbol (price return over trailing 252 bars, computed during scoring).
2. Fetch Nifty 500 index return over the same period using `fetch_stock_data("^CRSLDX", append_ns=False)`.
3. Compute excess return per symbol: `momentum_12m - nifty_12m`.
4. Rank all symbols by excess return and assign a percentile (0–100) as `rs_score`.
5. Upsert `rs_score` back into `technical_signals` for the current signal date.

This happens in a dedicated `_compute_rs_ranks(db, signal_date)` function called between Step 3 (scoring) and Step 5 (report generation) in the orchestrator.

#### 2d. Extended `fetch_and_cache_deep_fundamentals` in `screener.py`

The existing function already fetches `ticker.financials`, `ticker.info`, and `ticker.cashflow`. Add the following extraction logic within the same per-symbol try block:

- **ROCE:** `EBIT / (Total Assets - Current Liabilities)` using balance sheet rows. Wrapped in `try/except` returning `None` on failure.
- **PEG:** `trailingPE / (earningsGrowth * 100)` — only set if both values are non-None and growth > 0.
- **FCF:** `Operating Cash Flow - Capital Expenditures` from cashflow statement. Set `fcf_positive` if FCF > 0.
- **Price to FCF:** `marketCap / FCF` if FCF > 0.
- **Dividend Consistency:** `len(ticker.dividends.resample('YE').sum()[ticker.dividends.resample('YE').sum() > 0].tail(3)) == 3`.
- **Market Cap Category:** Derived from `marketCap` using INR thresholds: Large > ₹20,000 Cr (~$2.4B), Mid ₹5,000–20,000 Cr, Small below.

All new fields are written to the `FundamentalCache` row in the same commit block.

---

### 3. Screen Definitions

#### 3a. Module Layout

```
backend/app/screens/
    __init__.py
    base.py           # shared: latest_signal_date(), format_result(), base query builder
    price_action.py   # 52w High, 52w Low, Near Breakout
    value.py          # Undervalued, Low Debt Midcap/Smallcap, Steady Compounders
    momentum.py       # Momentum Monsters, Value with Momentum
    registry.py       # SCREEN_REGISTRY dict + metadata
```

#### 3b. `registry.py` — Screen Registry

```python
SCREEN_REGISTRY = {
    "52w-high": {
        "fn": price_action.near_52w_high,
        "label": "Near 52-Week High",
        "description": "Stocks trading within 5% of their 52-week high with bullish momentum.",
        "category": "Price Action"
    },
    "52w-low": {
        "fn": price_action.near_52w_low,
        "label": "Near 52-Week Low",
        "description": "Stocks near annual lows — potential reversal or value candidates.",
        "category": "Price Action"
    },
    "near-breakout": {
        "fn": price_action.near_breakout,
        "label": "Near Breakout",
        "description": "Stocks within 3% of a key resistance level with rising volume.",
        "category": "Price Action"
    },
    "low-debt-midcap": {
        "fn": value.low_debt_midcap_smallcap,
        "label": "Low Debt Mid & Small Caps",
        "description": "Mid and small-cap stocks with D/E below sector limit and positive FCF.",
        "category": "Value"
    },
    "undervalued-fundamentals": {
        "fn": value.undervalued_strong_fundamentals,
        "label": "Undervalued with Strong Fundamentals",
        "description": "Low PEG, high ROE, dividend-paying stocks below fair value.",
        "category": "Value"
    },
    "momentum-monsters": {
        "fn": momentum.momentum_monsters,
        "label": "Momentum Monsters",
        "description": "Top RS-ranked stocks with strong trend and cross-timeframe bullish confluence.",
        "category": "Momentum"
    },
    "value-with-momentum": {
        "fn": momentum.value_with_momentum,
        "label": "Value with Momentum",
        "description": "Fundamentally sound stocks where price momentum is beginning to turn up.",
        "category": "Momentum"
    },
    "steady-compounders": {
        "fn": value.steady_compounders,
        "label": "Steady Compounders",
        "description": "High ROCE, consistent dividend payers above 200 EMA.",
        "category": "Quality"
    }
}
```

#### 3c. Filter Criteria per Screen

**Near 52-Week High**
- `pct_from_52w_high` between -5% and 0%
- `timeframe == 'D'`, `is_bullish == True`
- `entry_score >= 60`
- Sort: `pct_from_52w_high DESC` (closest to high first)

**Near 52-Week Low**
- `pct_from_52w_low` between 0% and 10%
- `timeframe == 'D'`
- `profitability_streak_passed == True` (avoid value traps)
- Sort: `pct_from_52w_low ASC`

**Near Breakout**
- `pct_from_resistance` between -3% and 0%
- `volume_breakout == True` OR `ema_slope_20 > 0`
- `timeframe == 'D'`, `entry_score >= 55`
- Sort: `entry_score DESC`

**Low Debt Mid & Small Cap**
- `market_cap_category IN ('midcap', 'smallcap')`
- `de_check_passed == True`
- `fcf_positive == True`
- `profitability_streak_passed == True`
- Sort: `entry_score DESC`

**Undervalued with Strong Fundamentals**
- `peg_ratio < 1.5` and `peg_ratio > 0`
- `roe >= 0.15`
- `dividend_yield > 0`
- `ev_to_ebitda < 20`
- `above_200ema == True`
- Sort: `peg_ratio ASC`

**Momentum Monsters**
- `rs_score >= 80` (top 20% relative strength)
- `momentum_3m >= 15` (up 15%+ in 3 months)
- `adx >= 25` (strongly trending)
- `above_200ema == True`
- `is_bullish == True` across `timeframe IN ('D', 'W')` (join with W signals, check both)
- Sort: `rs_score DESC`

**Value with Momentum**
- `peg_ratio < 2.0` and `peg_ratio > 0`
- `momentum_1m >= 5` (recent price uptick)
- `ema_slope_20 > 0` (trend turning up)
- `profitability_streak_passed == True`
- `entry_score >= 50`
- Sort: `momentum_1m DESC`

**Steady Compounders**
- `roce >= 0.15`
- `dividend_consistency == True`
- `profitability_streak_passed == True`
- `de_check_passed == True`
- `above_200ema == True`
- `timeframe == 'D'`, `entry_score >= 55`
- Sort: `roce DESC`

#### 3d. `base.py` — Shared Utilities

```python
def latest_signal_date(db: Session) -> date:
    """Returns the most recent date in technical_signals."""

def format_result(signal: TechnicalSignal, stock: Stock, cache: FundamentalCache) -> dict:
    """Shapes a standard result dict for API responses."""

def confluence_for_symbol(db: Session, symbol: str, date: date) -> int:
    """Returns count of bullish timeframes for a symbol on a given date (0–3)."""
```

Screens that need confluence (e.g., Momentum Monsters) call `confluence_for_symbol` per result row. For screens where confluence is just informational, it is fetched in a single subquery after the main filter.

---

### 4. API Layer

#### 4a. New Router: `api/screens.py`

```
GET  /api/screens                → list all screens with label, description, category
GET  /api/screens/{slug}         → run or read materialized results for a screen
GET  /api/screens/{slug}?live=true  → bypass cache, run screen query directly
```

The router imports `SCREEN_REGISTRY` from `app/screens/registry.py`. It reads from `screen_results` by default (materialized in the pipeline), falling back to live execution if the table is empty or stale (last `computed_at` > 24h ago).

#### 4b. Wiring into `main.py`

```python
from app.api import screens as screens_router
app.include_router(screens_router.router)
```

No other API files require changes.

---

### 5. Materialization — End-of-Pipeline Step

At the end of `run_pipeline` in `orchestrator.py`, after report generation, add a call to `materialize_all_screens(db)`:

```python
def materialize_all_screens(db: Session):
    computed_at = datetime.datetime.utcnow()
    # Clear today's materialized results
    db.query(ScreenResult).filter(
        func.date(ScreenResult.computed_at) == computed_at.date()
    ).delete()

    for slug, meta in SCREEN_REGISTRY.items():
        try:
            results = meta['fn'](db)
            for rank, item in enumerate(results, start=1):
                db.add(ScreenResult(
                    screen_slug=slug,
                    symbol=item['symbol'],
                    rank=rank,
                    score_used=item.get('score', 0.0),
                    computed_at=computed_at
                ))
        except Exception as e:
            logger.error(f"Screen materialization failed for {slug}: {e}")

    db.commit()
```

This means frontend API responses are instant reads against `screen_results` during market hours, and data is fresh after each nightly pipeline run.

---

## Migration Strategy

### Step 1 — Alembic: Add new columns

Single migration script, no table renames required:

- Add all new columns to `technical_signals` (nullable Float/Boolean, no defaults needed — existing rows will have NULL which is valid).
- Add all new columns to `fundamental_cache` (same approach).
- Create `screen_results` table with PK and unique constraint.

No backfill is required or recommended. New columns will populate on the next pipeline run. Screens that filter on new columns will return empty results until the first enriched run completes, which is acceptable.

### Step 2 — Deploy code before running migration

Ensure `scorer.py` and `screener.py` changes are live before running the Alembic migration so the next pipeline run immediately writes all new fields. Deploying in the reverse order risks a window where the schema has new columns but the pipeline isn't populating them yet — functionally harmless but avoidable.

### Step 3 — Loosen Tier 1 filters

After confirming the new schema is stable (one pipeline run), update `passes_tier1_fast_filters` thresholds. This will increase the number of stocks scored per run — validate that pipeline run time remains acceptable before tightening Tier 1 further if needed.

---

## Implementation Tasks

1. **Alembic migration** — add columns to `technical_signals`, `fundamental_cache`; create `screen_results` table.
2. **Models** — update `TechnicalSignal`, `FundamentalCache` ORM models with new fields; add `ScreenResult` model.
3. **scorer.py** — extend `calculate_technical_score` to compute and return all new technical fields (52w stats, momentum, ADX, EMA200, slope, resistance, volume breakout).
4. **screener.py** — extend `fetch_and_cache_deep_fundamentals` to compute and write ROCE, PEG, FCF, Price/FCF, dividend consistency, market cap category.
5. **orchestrator.py** — add `_compute_rs_ranks()` post-scoring step; call `materialize_all_screens()` at end of pipeline; loosen Tier 1 gate (stop hard-skipping Tier 2 failures).
6. **screens/** — create module with `base.py`, `price_action.py`, `value.py`, `momentum.py`, `registry.py`.
7. **api/screens.py** — implement the two endpoints; wire into `main.py`.
8. **Tier 1 threshold update** — update `passes_tier1_fast_filters` with loosened thresholds after confirming pipeline stability.
