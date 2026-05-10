FOR AI AGENTS: DO NOT READ THIS FILE YET OR TRY TO IMPLEMENT ANY OF THIS YET

🟡 Phase 2 — High-Value Features
Alerting / Notifications — The screener runs but nobody knows when a stock hits 3/3 confluence. Add a Telegram bot (via python-telegram-bot) or email alert (SMTP) triggered at the end of run_pipeline() when confluence_count == 3. This is the #1 reason a screener becomes a daily-use tool.
Watchlist — A simple Watchlist DB table (user_id, symbol, added_at). Lets users pin stocks to track across pipeline runs even if they fall out of the top 20. Add a heart icon to StockCard.jsx.
Historical Signal Tracking — Your TechnicalSignal table stores signals but the dashboard only shows the latest. Build a chart showing a stock's score over time — this reveals whether a stock is trending up or deteriorating in its signal strength.

🟢 Phase 3 — Intelligence & Depth
Backtesting Engine — Given you already store historical OHLCV (3 years via period="3y"), you can replay your calculate_combined_score() logic over past dates and measure: "If I bought everything with score > 80 and sold after 20 days, what was the return?" This validates your scoring model with real data.
News Sentiment Layer — Add a NewsSignal model. At pipeline end, fetch headlines for top-scored stocks via a free API (e.g. NewsAPI or Yahoo Finance RSS) and run a quick sentiment pass. A stock with strong technicals + positive news sentiment is a much higher conviction signal.
Position Sizing / Risk Module — Add a simple Kelly Criterion or fixed-fractional calculator. Given a portfolio size, score, and ATR (already derivable from your OHLCV data), suggest position size and stop-loss level. This moves the tool from screener to decision support.

🔵 Phase 4 — Platform Maturity
User Authentication — Add FastAPI-Users or a simple JWT layer. This unlocks per-user watchlists, custom alert thresholds, and eventually a SaaS model.
Real-time Price Updates — Your dashboard polls every 15s via REST. Switch to WebSockets (fastapi-websockets) for live intraday price ticks during market hours. The CandlestickChart component is already structured for this.
Deployment & Scheduling — Containerize with Docker Compose (FastAPI + PostgreSQL + a Redis task queue). Replace the BackgroundTasks pipeline trigger with APScheduler or Celery so the pipeline runs automatically at market close (3:30 PM IST) daily without manual triggering.

---

## High Impact — Core Trading Utility

**1. Watchlist & Alerts**
The most requested feature in any screener. Users should be able to save stocks and get notified when conditions change.
- Per-symbol watchlists stored in DB
- Alert triggers: price crosses EMA, RSI crosses 50, volume breakout fires, score crosses a threshold
- Delivery via email or Telegram bot (Telegram is popular with Indian retail traders)

**2. Backtesting Engine**
You have historical `TechnicalSignal` data accumulating every day — this is the raw material for backtesting. Let users ask: *"If I bought every stock that hit score ≥ 80 on a given day, what happened 30 days later?"*
- Forward return calculation: store `close_price` at signal date, compute return at T+5, T+10, T+30
- Win rate, average gain, max drawdown per screen
- This also validates whether your scoring model actually works

**3. Sector Rotation Dashboard**
You already have `sector` in `Stock` and momentum data in `TechnicalSignal`. Aggregate them:
- Average RS score, momentum_3m, and confluence per sector
- Heatmap showing which sectors are leading vs. lagging
- This is a high-signal feature institutional traders use daily

**4. Portfolio Tracker**
Let users input their holdings and see:
- Current score + signal for each holding
- Alert when a holding's signal turns bearish
- Overall portfolio confluence score

---

## Medium Impact — Screener Depth

**5. Custom Screen Builder**
Instead of only your hardcoded screens, let users build their own by combining filters from a UI:
- Fields: RSI range, momentum thresholds, market cap category, sector, above/below 200 EMA, etc.
- Save named screens to DB
- This turns your tool from a product into a platform

**6. Multi-Timeframe Signal Change Detection**
Right now you show the current state. What traders really want is *when did the signal change?*
- Detect when `is_bullish` flips from False → True (fresh breakout)
- Detect when confluence goes from 1 → 3 (alignment happening now)
- Surface these as "Today's Setups" — stocks where something just changed

**7. Earnings Calendar Integration**
A stock scoring 90 two days before earnings is a trap. Integrate NSE's earnings calendar:
- Flag stocks with earnings within 7 days on the screener results
- Optionally exclude them from screens (user preference)
- Source: NSE website or a free API like `jugaad-trader`

**8. FII/DII Institutional Activity**
NSE publishes daily FII and DII buy/sell data. A stock with strong technicals + FII buying is a much stronger setup than technicals alone.
- Scrape or fetch NSE's bhav copy + FII data
- Add `fii_net_buying` column to signals or a separate table
- Surface in screener results as a filter

---

## Lower Impact but High Polish

**9. Score History Charts**
You already store 30 days of `score_history` per stock in the API. Plot it:
- Line chart of daily score over time
- Overlay price to show correlation between score peaks and price action
- This builds trust in your model

**10. Export to CSV/Excel**
Every serious trader wants to work with data offline. Add a `/api/screens/{slug}/export` endpoint that returns a CSV. Simple to build, high perceived value.

**11. Scheduled Report Delivery**
You already generate a Markdown report daily. Go one step further:
- Email the top 10 setups every day at 4:30 PM IST (after market close)
- Include confluence count, score, RSI, and a one-line reason (e.g. "Fresh MACD crossover + volume breakout")

**12. "Why This Stock?" Explainability**
When a stock scores 85, users don't know why. Add a signal breakdown:
```json
{
  "score": 85,
  "breakdown": {
    "ema_alignment": 20,
    "macd_bullish": 20,
    "rsi_crossing_50": 15,
    "volume_surge": 15,
    "pe_under_25": 20,
    "pledge_clean": 10,
    "deductions": -15
  },
  "narrative": "Strong trend alignment with institutional volume. RSI just crossed 50 from below."
}
```
You already have all this data — it just needs to be surfaced.

---

## Infrastructure Features Worth Adding

**13. Rate Limiting & Queue for Pipeline**
Right now if someone hits `/screener/run` twice, you get two pipelines running simultaneously against the same DB. Add a simple lock:
```python
# Check if pipeline is already running before starting
run = db.query(PipelineRun).filter(PipelineRun.status == "running").first()
if run:
    raise HTTPException(400, "Pipeline already running")
```

**14. Data Quality Monitoring**
Silent failures are your biggest risk. Add a daily check:
- How many stocks have signals today vs. yesterday? (Large drop = fetch failure)
- How many have `NULL` momentum_12m? (Indicates insufficient history)
- Log these as a `/api/health/data` endpoint

**15. User Authentication**
If you plan to share this beyond yourself, you'll need it before adding watchlists or custom screens. FastAPI + JWT is straightforward. Without it, all watchlist/alert features are single-user.

---

## Suggested Build Order

```
Phase 1: Signal Change Detection → Earnings Flag → Export CSV
         (high value, low effort, standalone)

Phase 2: Watchlist + Alerts → Score Explainability
         (requires auth, foundational for retention)

Phase 3: Backtesting Engine → Sector Rotation
         (data is already there, just needs aggregation)

Phase 4: Custom Screen Builder → Portfolio Tracker
         (platform features, higher complexity)
```

The single highest-ROI feature given your current data is **signal change detection** — you already have everything needed and it directly answers the trader's core question: *"What should I look at today?"*