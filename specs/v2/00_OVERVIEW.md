# Stock-AI v2 — Overview & Context

> **Read this first.** This file gives a fresh session the full context, the
> findings that motivated v2, the locked design decisions, and the build order.
> The four component specs (`01`–`04`) depend on the decisions recorded here.
> Do not re-litigate decisions marked **LOCKED** — they were made deliberately
> after reviewing the v1 results.

---

## 1. What we are building

A systematic, **long-only momentum portfolio** strategy for Indian (NSE) equities,
plus the backtest engine to validate it. v1 exists and works mechanically, but its
**measurement is biased optimistic** and its architecture cannot support the fixes
we need. v2 is a partial rewrite: we keep the good, well-tested pieces and replace
the simulation core.

This is **not** a greenfield rewrite. It is a "strangler": reuse the data/indicator
layers, replace the simulation engine and the strategy's exit model.

---

## 2. Why v1 must be replaced (the findings)

These are the evidence-backed problems found reviewing v1. They define what v2 must fix.

1. **Survivorship bias (confirmed by the user).** v1's universe is
   `db.query(Stock).limit(2500)` — today's *live* NSE listings — fed by yfinance.
   Delisted/blown-up names are absent. Momentum is especially vulnerable because the
   pump-then-collapse names that generate signals are exactly the ones missing.
   → v2 must use a **point-in-time, survivorship-free universe** (see `01_DATA_LAYER`).

2. **Sharpe is structurally inflated.** In v1 `compute_metrics`, equity only changes
   on trade *exit* dates (step function), open positions are never marked to market
   daily, and returns are computed on the full ₹1M base regardless of deployment.
   This deflates measured volatility and makes Sharpe non-comparable to the benchmark.
   → v2 must do **daily mark-to-market** and **track exposure/utilization**.

3. **Fill assumptions lean optimistic.** v1 checks target *before* stop within a bar
   (`engine.py:1117` before `:1122`) — books the win when a bar spans both — and the
   trailing logic raises the stop using the same bar's high before checking the low
   (intrabar lookahead). → v2's rebalance model removes intrabar targets entirely;
   the only intra-period exit (catastrophic stop) executes next-day open after a
   *close* breach. **No intrabar ordering assumptions allowed.**

4. **Costs are too low.** v1 uses a flat 0.25% round-trip. Real delivery-equity cost
   is STT 0.2% + flat DP/charges + slippage; realistic round-trip on mid/smallcaps is
   **0.6–1.0%**. → v2 must use a **cost function** (see `03_COST_AND_BENCHMARK`).

5. **The scoring system is theater.** A weighted 0–100 score that is then overridden by
   a wall of hard boolean gates. Evidence: Stage-1 ranks #1/#2/#3 are byte-identical
   with `min_adx` 20/25/30 — that dimension does nothing. → v2 **drops the score**;
   ranking is a single transparent metric (volatility-adjusted momentum).

6. **Adding complexity made it worse.** v1 Stage-1 best had mean Sharpe 0.71 / 10.1%
   return; adding the Stage-2 regime/breadth layer collapsed it to 0.24 / 1.6% with a
   0.0% D3 improvement rate (target was >30%). → v2 starts **minimal** and adds a layer
   only when it earns its keep against the benchmark.

7. **Symbol-first architecture is the root blocker.** v1 scores each symbol, simulates
   each symbol's trades in isolation, then reconciles portfolio constraints post-hoc
   (`simulate_portfolio` / `_is_portfolio_valid`). This makes daily MTM, exposure
   tracking, and slot-level ranking impossible to add cleanly. → v2 inverts to a
   **time-driven daily loop** (see `02_SIMULATION_CORE`).

---

## 3. The goal (LOCKED)

**Risk-adjusted outperformance of an investable momentum index**, not raw return and
not "positive Sharpe vs cash."

- **Benchmark:** Nifty200 Momentum 30 TRI (primary). Nifty Midcap150 Momentum 50 TRI
  as a secondary/aspirational benchmark if the universe skews mid-cap.
- **Falsifiable target (set before any tuning):** match the benchmark's CAGR after
  realistic costs while holding **max drawdown ≤ 70% of the benchmark's** — i.e.
  **beat the benchmark's Calmar ratio**. If a candidate cannot do this on honest data,
  it fails, regardless of raw return.
- The edge thesis: the index has **no drawdown control**. Our intended edge is a
  simple **market-regime/cash overlay** that de-risks between rebalances. We are the
  same *kind* of strategy as the benchmark, and we try to beat it on risk control.

---

## 4. The strategy model (LOCKED)

Position-centric, periodically rebalanced momentum portfolio. **Not** trade-centric.

| Decision | Choice |
|---|---|
| Rebalance cadence | **Monthly** (last trading day of month → execute next open). Cadence is the one structural knob we may sweep later. |
| Selection | Rank universe by **volatility-adjusted momentum**. Binary entry gate is separate from the ranker. |
| Membership buffer (hysteresis) | **Buy** when rank ≤ N (e.g. top 20). **Sell** only when rank falls past M, M > N (e.g. top 35). Reduces churn at the boundary. |
| Weighting | **Equal-weight, reset each rebalance**, with a single-name cap. Fewer than N qualifiers → hold cash for the remainder. |
| Primary exit | **Rank drop-out** at rebalance. |
| Risk overlay | **Portfolio-level market-regime/cash overlay** (de-risk/scale to cash when market breaks). Simple, on/off + scale. |
| Catastrophic stop | **Wide circuit-breaker only** (e.g. −25% from cost basis), checked on daily *close*, executed next-day open. No tactical/tight stops. |
| Entry timing | Evaluate at rebalance date close; **fill next-day open**. **No pullback-entry machinery.** |

**Dropped from v1 entirely:** the 0–100 scoring system, `holding_days`, `target_pct`,
`risk_reward_ratio`, partial exits, state-based/overextended exits, signal-invalidation
exits, pullback entry + fallback, signal tiers, MTF weekly/monthly confirmation, the
multi-state regime hysteresis maze, per-trade tight stops.

---

## 5. What to reuse (do NOT rewrite)

- `backend/app/core/strategy.py` → `TechnicalStrategy.calculate_indicators`. Indicator
  math is fine and is shared with the live pipeline — keep live/backtest parity. v2 may
  call it for EMAs/ATR/momentum, but **ignore** `evaluate()` (the scoring) and the v1
  `calculate_signals` boolean stack.
- `backend/app/pipeline/ohlcv_cache.py` → `OHLCVCache`. Reuse for caching, but the v2
  data source is bhavcopy parquet, not yfinance (see `01_DATA_LAYER`).
- Gap-aware fill primitives in `backend/app/backtest/engine.py` (the open-vs-level fill
  logic) — reuse the *idea*, fix the *ordering* (stop-before-target, no intrabar peek).

**What to delete/ignore from v1:** `score_series`, `simulate_trades`, `simulate_portfolio`,
`_is_portfolio_valid`, `_build_regime_map`, `build_mtf_state_map`, the scoring in
`evaluate()`. Keep v1 runnable in parallel until v2 reproduces/beats it on honest data.

---

## 6. Build sequence (specs map to these)

1. **Data layer** — `01_DATA_LAYER.md`. The long pole. Nothing downstream is trustworthy
   until this is correct and independently validated (spot-check known splits/bonuses).
2. **v2 simulation core** — `02_SIMULATION_CORE.md`. The daily event-driven loop.
3. **Cost model + benchmark wiring** — `03_COST_AND_BENCHMARK.md`.
4. **Validation floor + methodology** — `04_VALIDATION_FLOOR.md`. Establish the simple
   momentum floor vs the index; anti-overfit discipline.

Build strictly in this order. Do not tune parameters until step 4's floor is established
on honest data.

---

## 7. Glossary

- **Point-in-time universe:** the set of symbols that were actually tradeable on a given
  historical date — including names later delisted.
- **TRI:** Total Return Index (includes dividends). Use TRI for benchmark comparison.
- **12-1 momentum:** price return over the last 12 months *excluding* the most recent
  1 month (avoids short-term reversal). Default ranking input.
- **ADV:** Average Daily traded Value (₹), used for the liquidity floor and slippage.
- **Deployable capital:** equity × regime-scaled invested fraction; the rest is cash.
- **Turnover:** Σ|target weight − current weight| at each rebalance; a first-class metric
  and cost driver in v2.

---

## 8. Environment / repo facts a fresh session needs

- Backtest code lives under `backend/`. Python, SQLAlchemy, Alembic, FastAPI, Celery,
  pandas / pandas_ta_classic. Postgres on 5434, Redis on 6380 (docker-compose).
- CLAUDE.md "Pipeline Laws" apply: idempotency, `.NS` suffix on symbols, UTC storage /
  IST display, Alembic migration for every schema change, Pydantic on API I/O.
- v2 should live in clearly separated modules (e.g. `backend/app/backtest_v2/` and
  `backend/app/data/bhavcopy/`) so v1 stays runnable for comparison.
