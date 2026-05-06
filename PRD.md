# Stock AI MVP — Design Document
**Date:** 2026-05-06
**Author:** Solo Developer
**Status:** MVP Spec — Ready for Implementation

---

## Summary

A personal AI-powered stock research tool for Indian markets (NSE/BSE) that runs a daily pipeline after market close. It screens NSE-listed stocks using fundamental filters, scores them using technical analysis across daily/weekly/monthly timeframes, and presents results on a React web dashboard. Built for a single user, runs locally, uses only free APIs.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data Fetching | `yfinance`, `nsepython` |
| Technical Analysis | `pandas-ta` |
| Backend | `FastAPI` (Python) |
| Scheduler | `APScheduler` (Embedded in FastAPI) |
| Database | `PostgreSQL` (Managed via Neon/Supabase) |
| Migrations | `Alembic` |
| Frontend | `React` + `Vite` + `Recharts` + `lightweight-charts` |
| Package Manager | `pip` + `npm` |
| Testing | `pytest`, `pytest-cov`, `httpx` |

---

## Architecture Overview

The system follows a **Monolithic Architecture** to simplify development and deployment on free-tier hosting services.

```
┌─────────────────────────────────────────────────────┐
│             FASTAPI BACKEND (Monolith)              │
│  ┌──────────────────────┐  ┌─────────────────────┐  │
│  │   API ENDPOINTS      │  │    APScheduler      │  │
│  │  /stocks, /scores    │  │  (Daily 4 PM Job)   │  │
│  └──────────┬───────────┘  └──────────┬──────────┘  │
└─────────────┼─────────────────────────┼─────────────┘
              │                         │
     ┌────────▼─────────────────────────▼────────┐
     │            DATA & PROCESSING              │
     │  fetcher.py | screener.py | scorer.py     │
     └────────────────────┬──────────────────────┘
                          │
                 ┌────────▼────────┐
                 │  PostgreSQL DB  │
                 │ (Neon/Supabase) │
                 └────────┬────────┘
                          │
                 ┌────────▼────────┐
                 │  React Frontend │
                 │ (Vite + Charts) │
                 └─────────────────┘
```

---

## Component Breakdown

### 1. Data Layer

**Responsibilities:** Fetch EOD price data + company fundamentals daily.

| Need | Library | Notes |
|---|---|---|
| EOD OHLCV prices | `yfinance` | Use `.NS` suffix for NSE (e.g. `RELIANCE.NS`) |
| Fundamentals (P/E, ROE, Debt) | `yfinance .info` | Free, no API key needed |
| NSE stock universe | `nsepython` | Fetch full list of NSE-listed stocks for screener |
| Sector/industry info | `yfinance .info` | Included in same call |

**What it fetches daily:**
- Last 1 year of OHLCV (for TA calculations)
- Fundamentals: P/E, P/B, ROE, Debt/Equity, EPS growth, promoter holding, market cap

---

### 2. Processing Engine

**Stage 1 — Fundamental Screener**

Filters the NSE universe (~2000 stocks) down to a quality shortlist:

| Filter | Threshold |
|---|---|
| ROE | > 15% |
| Debt/Equity | < 1 |
| EPS Growth (YoY) | > 10% |
| Market Cap | > ₹500 Cr |
| Promoter Holding | > 40% |

Output: ~50–150 quality stocks passed to Stage 2.

**Stage 2 — Technical Scorer**

Runs TA on each shortlisted stock using `pandas-ta` and scores 0–100:

| Indicator | Signal | Weight |
|---|---|---|
| EMA 5/13/26 alignment | Bullish stack | 25% |
| MACD crossover | Bullish cross | 25% |
| RSI 14 | 40–60 recovery zone | 20% |
| Volume vs 20 SMA | Above average | 15% |
| Price vs 52-week range | Near breakout | 15% |

Output: Each stock gets an **Entry Score (0–100)**.

**Stage 3 — Report Generator**
- Ranks stocks by Entry Score
- Tags each as 🟢 Strong Entry (>70) / 🟡 Watch (40–70) / 🔴 Avoid (<40)
- Saves daily snapshot to SQLite
- Generates a summary JSON for the dashboard

---

### 3. PostgreSQL Database

Managed via free-tier provider (Neon/Supabase). Migrations handled by **Alembic**.

```sql
-- Master stock list
CREATE TABLE stocks (
  symbol VARCHAR PRIMARY KEY,
  name VARCHAR,
  sector VARCHAR,
  industry VARCHAR,
  market_cap DOUBLE PRECISION
);

-- Daily technical scores
CREATE TABLE daily_scores (
  date TIMESTAMP WITHOUT TIME ZONE,
  symbol VARCHAR,
  entry_score DOUBLE PRECISION,
  rsi DOUBLE PRECISION,
  macd DOUBLE PRECISION,
  ema_signal VARCHAR,
  volume_signal VARCHAR,
  PRIMARY KEY (date, symbol)
);

-- Pipeline run log
CREATE TABLE pipeline_runs (
  run_id UUID PRIMARY KEY,
  timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc'),
  status VARCHAR,  -- idle / running / complete / failed / warning
  stocks_fetched INTEGER,
  stocks_scored INTEGER,
  errors TEXT
);
```

---

### 4. FastAPI Backend

**Key Endpoints:**

```
GET  /api/stocks                → full watchlist with latest scores
GET  /api/stocks/{symbol}       → detail view (price history + fundamentals + scores)
GET  /api/screener/top          → top 10 stocks by entry score today
GET  /api/scores/history        → score trend over time for a stock
POST /api/screener/run          → manually trigger a fresh screener run
GET  /api/reports/latest        → today's full report summary
GET  /api/pipeline/status       → current pipeline run status
```

---

### 5. React Frontend

**Four main views:**

| View | Contents |
|---|---|
| **Dashboard** | Top scored stocks today, 3-timeframe score cards, pipeline health bar, last run timestamp |
| **Screener Results** | Full table of scored stocks, sortable/filterable by sector, score, fundamentals |
| **Stock Detail** | Candlestick chart (lightweight-charts), RSI/MACD panels, fundamental card, score history graph |
| **Reports** | Historical daily reports, score trends over time |

**3-Timeframe Score Card (per stock):**
```
RELIANCE.NS
Daily   → 🟢 78/100
Weekly  → 🟡 55/100
Monthly → 🟢 82/100
```

---

## Data Flow

### Daily Pipeline (Runs 4 PM weekdays)

```
1. APScheduler triggers daily job
        │
        ▼
2. DATA FETCH
   ├── nsepython → fetch full NSE stock universe (~2000 symbols)
   ├── yfinance  → fetch 1yr EOD OHLCV for all symbols (.NS suffix)
   ├── yfinance  → fetch fundamentals via .info for all symbols
   └── Store raw data in memory (pandas DataFrames)
        │
        ▼
3. FUNDAMENTAL SCREENING (Stage 1)
   ├── Apply filters: ROE, Debt/Equity, EPS growth, Market Cap, Promoter holding
   ├── Drop stocks that fail any filter
   └── Output: shortlist DataFrame (~50–150 stocks)
        │
        ▼
4. TECHNICAL SCORING (Stage 2)
   ├── pandas-ta computes: EMA 5/13/26, MACD, RSI 14, Volume SMA 20
   ├── Each indicator checked → produces sub-score
   ├── Weighted sum → final Entry Score (0–100)
   └── Output: scored DataFrame with all indicator values
        │
        ▼
5. MULTI-TIMEFRAME SCORING
   ├── Same scoring logic re-runs on interval="1wk" → weekly_score
   ├── Same scoring logic re-runs on interval="1mo" → monthly_score
   └── All three scores merged into single result per stock
        │
        ▼
6. PERSIST TO SQLITE
   ├── daily_scores   → insert today's rows (UPSERT)
   ├── weekly_scores  → update if Friday
   ├── monthly_scores → update if last trading day of month
   └── fundamentals   → upsert latest values
        │
        ▼
7. REPORT GENERATION
   ├── Rank stocks by daily entry score
   ├── Tag each: 🟢 Strong / 🟡 Watch / 🔴 Avoid
   ├── Generate daily summary JSON → saved to SQLite
   └── Log run timestamp + stock count processed
        │
        ▼
8. FastAPI serves fresh data
   └── React dashboard polls /api/reports/latest on page load
```

### User-Triggered Flow (Dashboard Interaction)

```
User opens dashboard
        │
        ▼
React → GET /api/reports/latest
        │
        ▼
FastAPI reads SQLite → returns top stocks + scores + last run time
        │
        ▼
Dashboard renders:
├── Top 10 scored stocks (3-timeframe score cards)
├── Last pipeline run timestamp + health bar
└── Market summary

User clicks a stock
        │
        ▼
React → GET /api/stocks/{symbol}
        │
        ▼
FastAPI reads SQLite → returns:
├── 1yr OHLCV (candlestick chart)
├── All indicator values
├── Fundamental card data
└── Score history (daily/weekly/monthly trend)

User clicks "Run Screener Now"
        │
        ▼
React → POST /api/screener/run
        │
        ▼
FastAPI triggers pipeline manually
└── Returns job_id → React polls status → refreshes on complete
```

### Data Freshness Summary

| Data Type | Source | Frequency | Stored In |
|---|---|---|---|
| NSE stock universe | nsepython | Weekly | SQLite: stocks |
| EOD OHLCV | yfinance | Daily 4PM | In-memory → scores |
| Fundamentals | yfinance .info | Daily 4PM | SQLite: fundamentals |
| Daily scores | pandas-ta | Daily 4PM | SQLite: daily_scores |
| Weekly scores | pandas-ta | Friday 5PM | SQLite: weekly_scores |
| Monthly scores | pandas-ta | Month-end | SQLite: monthly_scores |
| Reports | Generator | Daily 4PM | SQLite: reports |

---

## Error Handling

### 1. Data Fetch Errors

```
For each symbol fetch:
├── Wrap in try/except
├── If empty DataFrame → mark as "fetch_failed" → skip
├── If exception (timeout, rate limit) → retry up to 3x with exponential backoff
├── If still failing → log warning, skip symbol, continue pipeline
└── Never let one bad symbol crash the entire pipeline

Batch fetching:
├── Fetch symbols in batches of 50 (avoid rate limiting)
├── Add 1–2 second delay between batches
└── Log total fetch success/failure count at end
```

### 2. Processing Engine Errors

```
Before scoring each stock:
├── Check minimum candle count → need at least 60 days of EOD data
├── If insufficient → skip TA scoring, mark as "insufficient_data"
├── If pandas-ta throws on a specific indicator → assign 0 for that sub-score
└── Log which indicators failed per symbol

Fundamental screening:
├── If a fundamental field is None/NaN → treat as failing that filter
├── Never score a stock with missing fundamentals
└── Log count of stocks dropped due to missing data
```

### 3. Database Errors

```
All DB writes:
├── Wrap in transactions → commit only if all writes succeed
├── On failure → rollback entire transaction, log error
├── Use UPSERT (INSERT OR REPLACE) → idempotent pipeline
└── Every run logged in pipeline_runs table regardless of outcome
```

### 4. FastAPI Errors

```
Pipeline running state:
├── Store pipeline status in SQLite: idle / running / failed / complete
├── If POST /api/screener/run called while running → return 409 Conflict
└── Frontend shows "Pipeline running..." state accordingly

Empty database (first run):
├── All GET endpoints return empty arrays with a "no_data" flag
└── Frontend shows "Run screener to get started" empty state

All endpoints:
└── Return structured error: { "error": "description", "code": "ERROR_CODE" }
```

### 5. Scheduler Errors

```
Market holiday detection:
├── Maintain hardcoded NSE holiday list for the year
├── Scheduler checks if today is a trading day before running
└── Skip gracefully with a log entry if holiday

Job crash recovery:
├── APScheduler misfire_grace_time → allows late execution if server was down
├── On crash → pipeline_runs table marks run as "failed"
└── Manual re-run always available via POST /api/screener/run

Prevent overlapping runs:
└── Job acquires a simple lock in SQLite before starting
    → Releases on completion or crash
```

### 6. Error Priority Summary

| Error | Severity | Action |
|---|---|---|
| Single symbol fetch fail | Low | Skip + log |
| Rate limit from yfinance | Medium | Retry with backoff |
| DB write failure | High | Rollback + alert on dashboard |
| Scheduler crash | High | Log + allow manual re-run |
| Pipeline running twice | Medium | Lock prevents it |
| Market holiday | Info | Skip gracefully |

### Pipeline Health Bar (Dashboard)

```
┌─────────────────────────────────────────┐
│ Last Run: Today 4:03 PM  ✅ Complete     │
│ Stocks Fetched: 1,847 / 2,000           │
│ Stocks Scored: 143                       │
│ Fetch Failures: 153 (logged)            │
└─────────────────────────────────────────┘
```

---

## Testing Strategy

### 1. Unit Tests

```
tests/unit/
├── test_screener.py
│   ├── test_fundamental_filter_passes_good_stock()
│   ├── test_fundamental_filter_rejects_high_debt()
│   ├── test_fundamental_filter_handles_missing_fields()
│   └── test_shortlist_never_exceeds_limit()
│
├── test_scorer.py
│   ├── test_ema_bullish_alignment_scores_high()
│   ├── test_ema_bearish_alignment_scores_low()
│   ├── test_macd_crossover_detected_correctly()
│   ├── test_rsi_oversold_recovery_scores_correctly()
│   ├── test_score_always_between_0_and_100()
│   ├── test_insufficient_data_returns_none()
│   └── test_all_weights_sum_to_100()
│
└── test_db.py
    ├── test_upsert_daily_scores_is_idempotent()
    ├── test_pipeline_run_logged_on_success()
    └── test_pipeline_run_logged_on_failure()
```

### 2. Integration Tests

```
tests/integration/
└── test_pipeline.py
    ├── test_full_pipeline_with_mock_data()
    ├── test_pipeline_skips_failed_fetches_gracefully()
    ├── test_pipeline_idempotent_on_double_run()
    └── test_weekly_scores_only_written_on_friday()
```

### 3. API Tests

```
tests/api/
└── test_endpoints.py
    ├── test_get_stocks_returns_200()
    ├── test_get_stock_detail_returns_correct_symbol()
    ├── test_screener_run_returns_409_if_already_running()
    ├── test_reports_latest_returns_empty_state_before_first_run()
    └── test_invalid_symbol_returns_404()
```

### 4. Manual Smoke Test Checklist

```
[ ] Scheduler triggers at 4 PM and completes without crash
[ ] At least 50 stocks scored after pipeline run
[ ] Dashboard loads and shows today's scores
[ ] Clicking a stock opens detail page with chart
[ ] Score history graph shows multiple days of data
[ ] "Run Screener Now" button works and refreshes data
[ ] Pipeline run health bar shows correct counts
[ ] Weekly scores update on Friday
[ ] Holiday detection skips pipeline correctly
```

### 5. Data Sanity Checks (Built into Pipeline)

```python
assert 0 <= score <= 100 for all scores
assert scored_count >= 30       # alert if screener returning too few stocks
assert daily_scores date == today  # no stale data written
assert no duplicate (date, symbol) pairs in daily_scores
assert pipeline duration < 30 minutes  # alert if unusually slow
```

### 6. Coverage Targets

| Module | Target |
|---|---|
| Scoring engine | 90%+ |
| Fundamental screener | 80%+ |
| FastAPI endpoints | 70%+ |
| Pipeline orchestration | 60%+ |
| React frontend | Manual only |

### Test Setup

```bash
pip install pytest pytest-cov httpx

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Run only unit tests (fast)
pytest tests/unit/ -v
```

---

## Open Questions

- [ ] Which NSE holiday list source to use for 2026–2027?
- [ ] Should fundamentals refresh daily or weekly? (Daily adds API load)
- [ ] Add a `watchlist` table later so user can pin specific stocks outside screener?
- [ ] Should "Run Screener Now" support partial runs (e.g., only re-score technicals)?
- [ ] Consider adding Telegram notifications in v2 once MVP is stable

---

## Suggested Folder Structure

```
stock-ai/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── scheduler.py         # APScheduler jobs
│   │   ├── pipeline/
│   │   │   ├── fetcher.py       # yfinance + nsepython data fetching
│   │   │   ├── screener.py      # Fundamental screening logic
│   │   │   ├── scorer.py        # TA scoring engine
│   │   │   └── reporter.py      # Report generation
│   │   ├── db/
│   │   │   ├── models.py        # SQLite table definitions
│   │   │   └── queries.py       # DB read/write helpers
│   │   └── routers/
│   │       ├── stocks.py
│   │       ├── screener.py
│   │       └── reports.py
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── api/
│
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   ├── Dashboard.jsx
    │   │   ├── Screener.jsx
    │   │   ├── StockDetail.jsx
    │   │   └── Reports.jsx
    │   ├── components/
    │   │   ├── ScoreCard.jsx
    │   │   ├── CandlestickChart.jsx
    │   │   ├── FundamentalsCard.jsx
    │   │   └── PipelineHealthBar.jsx
    │   └── api/
    │       └── client.js        # Axios/fetch API calls
    └── package.json
```