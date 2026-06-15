# Spec 02 — Simulation Core: Task Breakdown & Build Tracker

> **Purpose.** Decompose `02_SIMULATION_CORE.md` into small, resumable, session-sized
> tasks so no single session has to build the whole v2 engine (too expensive in
> tokens). Each task is self-contained: a session loads `00_OVERVIEW.md`,
> `02_SIMULATION_CORE.md`, this file, and the **one task** it is doing — nothing more.
>
> **How to use this file each session:**
> 1. Read the task you are picking up (and its "Depends on").
> 2. Do only that task. Honor the per-session token budget (CLAUDE.md Rule 6).
> 3. Update the task's **Status** and fill its **Session log** at the end.
> 4. Check off the task's Done-criteria. Do not mark Done if anything was skipped
>    (Rule 12 — fail loud).
>
> **Status legend:** ☐ not started · ◐ in progress · ☑ done · ⚠ blocked
>
> **Build order is strict.** Later tasks assume earlier ones passed their
> Done-criteria. Do not tune parameters here — tuning lives in spec `04`.

---

## What this module consumes (already built — spec 01)

The data layer is **complete and validated** (see `01_DATA_LAYER_TASKS.md` exit criteria:
2017-01-02 → 2026-06-12, 3,470 ISINs, 739 delisted). v2 reads it via:

- `app.data.bhavcopy.store` — `read_prices_adjusted`, `read_universe_membership`,
  `read_isin_symbol_map`. Canonical columns: `isin, symbol, date, open, high, low, close,
  close_raw, close_tr, volume, traded_value, adv_20, adj_factor, tr_factor, series`.
- **MTM/P&L uses `close_tr`** (total return). **Signals/ranking use `close`** (split+bonus
  adjusted, ex-dividend). This split is load-bearing — do not mix them (`02` §3, §4).

**Reuse, do NOT rewrite (`00` §5):**
- `app.core.strategy.TechnicalStrategy.calculate_indicators` for EMAs/ATR (live/backtest
  parity). **Ignore** `evaluate()` and the v1 boolean signal stack.
- `app.pipeline.ohlcv_cache.OHLCVCache` caching *ideas* — but the source is v2 parquet.

**Out of scope here (later specs):**
- Real cost model + benchmark/index loaders are **spec 03**. This module defines the *cost
  interface* and a trivial default so the engine runs, and lets `regime` take an injected
  index series. Spec 03 swaps in the real implementations.

---

## Target module layout (from `02` §2) — for reference

```
backend/app/backtest_v2/
  __init__.py
  types.py         # T1 — Position, Fill, RebalancePlan, DailySnapshot
  config.py        # T1 — MomentumConfig (stripped down, §7)
  costs.py         # T2 — cost INTERFACE + trivial default (real model = spec 03)
  signals.py       # T3 — indicator precompute + ranker + binary entry gate
  regime.py        # T4 — market-level risk-on/off overlay (injected index series)
  portfolio.py     # T5 (state/MTM/fills) + T6 (build_rebalance_plan)
  engine.py        # T7 — the daily loop (orchestrator)
  metrics.py       # T8 — daily-MTM metrics (absolute; benchmark-relative = spec 03)
```

Keep **entirely separate** from `backend/app/backtest/` (v1). v1 must stay runnable.

---

## Task graph (dependencies)

```
T0 (reuse-contract spike — NO production code)
   └─> T1 (scaffold: types + config)
          ├─> T2 (costs interface + default)
          ├─> T3 (signals: indicators + ranker + gate)   [reads 01 parquet]
          ├─> T4 (regime overlay — injected index series)
          └─> T5 (portfolio: state + MTM + apply_fills)   needs T2
                 └─> T6 (build_rebalance_plan: hysteresis) needs T3
                        │
   ┌────────────────────┘
   ▼
  T7 (engine daily loop)  needs T2,T3,T4,T5,T6
        └─> T8 (metrics: daily-MTM)
              └─> T9 (acceptance suite — §10 as hard tests)
```

T2, T3, T4 are independent once T1 lands and can be done in any order.

---

## T0 — Reuse-contract spike (NO production code)

- **Status:** ☑
- **Depends on:** — (spec 01 done)
- **Goal:** Pin down the exact interfaces v2 builds on **before** writing the engine, so
  later cold sessions don't guess column names or function signatures.
- **Do:**
  - Read `app.core.strategy.TechnicalStrategy.calculate_indicators`: record its **input**
    contract (expected DataFrame columns/index) and **output** column names for the
    indicators v2 needs — `EMA_200` (or `SMA_200`), `ATR`, and whatever it emits. Note
    whether it expects `close` or OHLC and whether it mutates in place.
  - Read `app.data.bhavcopy.store` read functions: confirm exact signatures, filter args
    (ISIN / date-range pushdown), and returned dtypes. Confirm `adv_20` and `close_tr` are
    present per-row (they are — `01` §4).
  - Read `app.pipeline.ohlcv_cache.OHLCVCache`: note the caching pattern worth borrowing.
  - Decide the **trend-MA source**: does `calculate_indicators` give `EMA_200` directly, or
    must v2 compute the 200-DMA? Pick `EMA_200` vs `SMA_200` and document (`02` §4, §7).
  - Decide `momentum_12_1` implementation against **calendar-aware index positions** (not
    naive shifts) per `02` §4: `close[day-21] / close[day-273] - 1`. Confirm the trading
    calendar source = distinct dates in the v2 dataset (or benchmark dates — note which).
- **Deliverable:** a `## Verified reuse contracts` section appended to the TOP of
  `02_SIMULATION_CORE.md` listing the confirmed signatures, indicator output columns, the
  trend-MA decision, and the momentum index-position recipe.
- **Done-criteria:**
  - [x] `calculate_indicators` input + output columns documented (real, copy-pasted from
        the function), incl. the exact trend-MA column name v2 will read.
  - [x] `store` read-fn signatures + key columns confirmed against the built parquet.
  - [x] Trend-MA choice (EMA_200 vs SMA_200) recorded with reason.
  - [x] `momentum_12_1` calendar-position recipe written down (offsets, calendar source).
- **Session log:**
  - 2026-06-15: Read `strategy.py`, `store.py`, `ohlcv_cache.py`. Found critical column-case
    mismatch (v2 parquet = lowercase; `calculate_indicators` = title-case). Confirmed `EMA_200`
    is directly available. Confirmed `MOMENTUM_12M` is naive-shift (NOT 12-1) — v2 must compute
    its own. ATR column name is `ATRr_14`. All contracts written into `02_SIMULATION_CORE.md`
    `## Verified reuse contracts` section.

---

## T1 — Scaffold + types + config (`types.py`, `config.py`, package)

- **Status:** ☑
- **Depends on:** T0
- **Goal:** Create the package and the data structures everything else targets, so later
  tasks build against fixed dataclasses instead of inventing them.
- **Do:**
  - Create `backend/app/backtest_v2/__init__.py` and docstring stubs for the other modules
    (`raise NotImplementedError`) so imports resolve, mirroring the `01` scaffold approach.
  - Implement `types.py` dataclasses (`02` §6, §5): `Position(isin, symbol, shares,
    cost_basis, entry_date, last_price)`, `Fill(isin, side, qty, price, date, ...)`,
    `RebalancePlan(sells, buys, trims)`, `DailySnapshot(date, equity, cash, invested_value,
    exposure, n_positions)`. Frozen where natural; explicit types.
  - Implement `config.py` `MomentumConfig` **exactly** as `02` §7 (no extra fields — the
    spec is emphatic: no scoring weights, no holding_days/RR/tier/MTF). Include the §7
    defaults verbatim.
- **Deliverable:** importable package; `types.py` + `config.py`; other modules stub cleanly.
- **Done-criteria:**
  - [x] `from app.backtest_v2 import types, config` works; other stubs import cleanly.
  - [x] `MomentumConfig` field set == `02` §7 exactly (no missing, no extra fields).
  - [x] A round-trip/instantiation test constructs each dataclass with sample values and
        asserts field presence + types (offline, no network).
- **Session log:**
  - 2026-06-15: Created `backend/app/backtest_v2/` package with `__init__.py`, `types.py`,
    `config.py`, and stubs (raise NotImplementedError) for costs/signals/regime/portfolio/
    engine/metrics. All dataclasses frozen where appropriate. `MomentumConfig` field set
    matches spec §7 verbatim (14 fields). 16/16 unit tests pass offline.

---

## T2 — Cost interface + trivial default (`costs.py`)

- **Status:** ☑
- **Depends on:** T1
- **Goal:** Define the **cost contract** the engine/portfolio call, plus a deliberately
  trivial default, so v2 runs end-to-end now. **The real model is spec 03 — do not build it
  here.**
- **Do:**
  - Implement the `03` §1.3 signature as the contract:
    `fill_cost(side, qty, price, adv_20, cfg) -> float` returning total ₹ cost. Document
    that slippage will be realized via effective fill price (spec 03), not as a fee-only
    term — but the **default here may be a flat bps** charge with zero slippage.
  - Add a minimal `CostConfig` placeholder (e.g. a flat round-trip bps) and make the cost
    function **pluggable/injectable** into the portfolio + engine, so spec 03 swaps it with
    a one-line change.
  - Add a prominent module docstring: "PLACEHOLDER — real statutory+slippage model is
    spec 03 (`03_COST_AND_BENCHMARK.md`). This exists only to make the engine runnable and
    to satisfy `02` §10.2 (Σ per-fill costs == total cost paid)."
- **Done-criteria:**
  - [x] `fill_cost` matches the `03` §1.3 signature (so spec 03 is a drop-in).
  - [x] Default cost is deterministic and unit-tested (a known qty×price → known ₹ cost).
  - [x] Cost function is injectable (engine/portfolio accept it; not hard-imported).
  - [x] Docstring clearly flags this as a placeholder for spec 03 (Rule 12 — no silent
        pretend-real cost model).
- **Session log:**
  - 2026-06-15: Implemented `CostConfig` (flat 30 bps RT placeholder) and `fill_cost`
    (half-bps per leg, adv_20 accepted but ignored for interface parity). `CostFn` type
    alias defined so T5/T7 can accept it as a callable parameter — one-line swap for spec 03.
    10/10 unit tests pass offline (`test_t2_costs.py`).

---

## T3 — Signals: indicator precompute + ranker + entry gate (`signals.py`)

- **Status:** ☑
- **Depends on:** T1, T0 contracts; reads spec 01 parquet via `store`
- **Goal:** Produce the eligibility gate and the ranking score, **kept separate** (`02` §4:
  "do not merge them into a score").
- **Do:**
  - **Precompute layer (vectorized, once):** load adjusted prices for in-universe ISINs over
    `[start - warmup, end]` from `store`; per ISIN compute `EMA_200`/`SMA_200` (via reused
    `calculate_indicators` per T0), `momentum_12_1`, annualized volatility (stdev of daily
    returns over `vol_lookback_days`, annualized). Use **`close`** (signal prices), not
    `close_tr`. Calendar-aware index positions for momentum (`02` §4) — no naive shifts.
  - **Binary entry gate** `entry_gate(day, isin) -> bool` — ALL of: `close > EMA_200`;
    `momentum_12_1 > 0`; `adv_20 >= liquidity_floor` on the decision date (`02` §4). Regime
    is **not** a per-name gate here (it's `deployable_fraction`, T4).
  - **Ranker** `ranker(day, isin) -> float` — default `momentum_12_1 / annualized_vol`.
    Keep the interface pluggable (the index-style composite is a later A/B, **do not build
    both now** — `02` §4).
- **Done-criteria:**
  - [x] `entry_gate` returns False if ANY of the three conditions fails; True only when all
        pass (unit test each branch on synthetic frames).
  - [x] `momentum_12_1` uses calendar index positions; a test with a gap-containing calendar
        proves it picks the right offset rows (not a naive `.shift`).
  - [x] `ranker` returns vol-adjusted momentum; higher momentum / lower vol ranks higher
        (hand-checked test). Interface is `ranker(day, isin) -> float` (pluggable).
  - [x] All indicator math uses **`close`** (not `close_tr`); asserted in a test.
  - [x] Tests offline (synthetic price frames; no live data, no network).
- **Session log:**
  - 2026-06-15: Implemented `signals.py`: `_momentum_12_1` (vectorized numpy helper),
    `precompute_signals` (per-ISIN groupby loop calling `calculate_indicators` via
    title-case adapter + calendar-aware momentum + rolling vol), and `SignalStore` with
    `entry_gate`, `ranker`, `eligible_ranked`. 31/31 unit tests pass offline
    (`test_t3_signals.py`). Key decisions: (1) close_tr excluded at groupby-select time
    so no indicator can silently use it; (2) `_momentum_12_1` exposed as module-level
    function for direct testing; (3) `eligible_ranked` helper combines gate+sort for
    engine use.

---

## T4 — Regime overlay (`regime.py`)

- **Status:** ☑
- **Depends on:** T1
- **Goal:** A single dumb market-level signal → `deployable_fraction(day) ∈ [0, 1]`
  (`02` §8). Keep it minimal — this is the one drawdown-control layer; it earns its keep in
  spec `04`, not by elaboration here.
- **Do:**
  - Implement `deployable_fraction(day) -> float`: risk-on `1.0` when the **price** index
    `close > its 200-DMA`; risk-off → a floor (e.g. `0.0`–`0.3`, config) when below, with a
    small **debounce** (N consecutive days) to avoid whipsaw at the line (`02` §8).
  - The index series is **injected** (a pandas Series of the benchmark *price* index — the
    real loader is spec 03 `benchmark.py`, `03` §2.3). Do **not** fetch it here.
  - No multi-state hysteresis maze, no breadth/RSI/ADX lattice (`00` §2.6 — adding layers
    made v1 worse).
- **Done-criteria:**
  - [x] `deployable_fraction` = 1.0 above 200-DMA, → floor below, with debounce verified on
        a synthetic index that crosses the line (no single-day whipsaw).
  - [x] Index series is a parameter (injected), not fetched — spec 03 wires the real one.
  - [x] No-lookahead: the fraction for day D uses index data ≤ D only (asserted).
  - [x] Tests offline (synthetic up-trend and down-trend index series).
- **Session log:**
  - 2026-06-15: Implemented `RegimeConfig` (risk_off_floor, debounce_days, dma_period) and
    `RegimeOverlay` with `_precompute_fractions` (rolling 200-SMA + forward state-machine
    debounce). Pre-DMA warmup period defaults to risk-on via `where(dma.notna(), other=True)`.
    `deployable_fraction` is O(1) lookup after O(n) precompute. 16/16 unit tests pass offline
    (`test_t4_regime.py`): risk-on, debounce-3 flip, anti-whipsaw, recovery, no-lookahead,
    injection, unsorted-input handling.

---

## T5 — Portfolio state + MTM + fills (`portfolio.py`, part 1)

- **Status:** ☐
- **Depends on:** T1, T2
- **Goal:** The core mutable object: cash + positions, marked to market daily, fills applied
  at open (`02` §6).
- **Do:**
  - `Portfolio(cash, positions: dict[isin, Position])`.
  - `mark_to_market(day, prices)`: `equity = cash + Σ shares_i * close_tr[i, day]` (**TR**
    for P&L). A held name with **no print** that day (suspension) → carry last known price
    and **flag** it (`02` §6) — do not crash, do not zero it.
  - `apply_fills(fills, costs)`: for each fill at the `open` price, compute cost via the
    injected `costs.fill_cost` (T2), update cash/shares/cost_basis. A buy of a new name
    creates a `Position`; a full sell removes it; trims/adds adjust shares.
  - Append a `DailySnapshot` each day (`date, equity, cash, invested_value,
    exposure=invested_value/equity, n_positions`) — the equity + exposure curves (`02` §6, §9).
- **Done-criteria:**
  - [ ] **Cash conservation:** after any sequence of fills, `equity == cash + Σ shares*price`
        to within rounding (`02` §10.2). Unit-tested.
  - [ ] Total cash paid in costs == Σ per-fill `fill_cost` (no double-count, `02` §10.2).
  - [ ] Suspension handling: a held ISIN missing on day D carries last price and is flagged,
        run continues (unit test).
  - [ ] MTM uses `close_tr`; a test asserts P&L reflects the TR series, not `close`.
  - [ ] Tests offline (synthetic positions/fills/prices).
- **Session log:**
  - _(fill at end of session)_

---

## T6 — Rebalance plan with hysteresis (`portfolio.py`, part 2)

- **Status:** ☐
- **Depends on:** T5, T3
- **Goal:** `build_rebalance_plan(portfolio, ranked, deployable_fraction, config)` →
  `RebalancePlan(sells, buys, trims)` as next-open fills (`02` §5). The buffer keeps
  turnover sane — turnover is the cost driver.
- **Do:**
  - **Sell discipline (hysteresis):** for each holding, sell if rank > `sell_rank_buffer`
    (M), OR it fails `entry_gate` (e.g. dropped below EMA200), OR flagged by catastrophic
    stop. Otherwise **hold** (let winners run).
  - **Target membership:** desired = survivors + top `ranked` names (rank ≤ `target_positions`
    N) until `target_positions` filled.
  - **Weighting:** equal-weight reset each rebalance. `target_weight = deployable_fraction /
    target_positions`, capped at `max_position_pct`. Unallocated capital (too few eligible,
    or `deployable_fraction < 1`) **stays in cash** — never force deployment (`02` §5.3).
  - Compute target ₹ per name from **current equity** → buy/trim/sell deltas (`02` §5.4).
  - Apply `max_position_pct` cap. `max_sector_positions` — **defer** (no sector map from
    bhavcopy; config-driven, default off — `02` §5).
- **Done-criteria:**
  - [ ] Hysteresis verified: a holding at rank between N and M is **held**, not sold; a
        holding past M is sold (unit test on a constructed `ranked` list).
  - [ ] A holding that fails the entry gate is sold even if rank ≤ M.
  - [ ] Equal-weight reset produces correct ₹ targets from current equity; cap enforced.
  - [ ] `deployable_fraction < 1` leaves the remainder in **cash** (no forced deployment).
  - [ ] Fewer than N eligible names → no padding with junk; cash held (unit test).
  - [ ] Tests offline.
- **Session log:**
  - _(fill at end of session)_

---

## T7 — Engine daily loop (`engine.py`)

- **Status:** ☐
- **Depends on:** T2, T3, T4, T5, T6
- **Goal:** Wire the authoritative control flow (`02` §3) — the time-driven daily loop that
  replaces v1's symbol-first engine.
- **Do:**
  - Setup: load prices for in-universe ISINs over `[start - warmup, end]`; precompute
    indicators once (T3); build the **trading calendar** (benchmark/dataset dates);
    `rebalance_dates` = last trading day of each month in `[start, end]`.
  - Per `day` in calendar, in this exact order (`02` §3):
    1. `mark_to_market`; record `DailySnapshot`.
    2. **Catastrophic stop check** on **close**: if `close ≤ cost_basis*(1 -
       catastrophic_stop_pct)`, queue SELL at **next** open.
    3. `deployable_fraction = regime.deployable_fraction(day)`.
    4. On `rebalance_dates`: `eligible = membership(day) ∩ entry_gate ∩ liquidity floor`;
       `ranked = sort eligible by ranker desc`; `plan = build_rebalance_plan(...)`; queue
       sells+buys at **next** open.
    5. `apply_fills(this_day_open_fills, costs)` — fills queued on the **prior** day.
  - **Invariants (`02` §3):** all decisions use data ≤ decision date; all fills at the next
    session's open. No same-bar decide-and-fill. No intrabar high/low peeking. Catastrophic
    stop triggers on close, fills next open.
- **Done-criteria:**
  - [ ] A full run over a small synthetic universe + calendar produces a `DailySnapshot`
        series (equity + exposure curves) and a fills/positions log.
  - [ ] Queue discipline verified: a decision on day D never fills before D+1 open
        (unit test inspects fill dates vs decision dates).
  - [ ] Rebalance only on month-end trading days; catastrophic stop fires on close breach
        and fills next open (unit tests).
  - [ ] **Determinism:** same config + data → identical equity curve (`02` §10.3).
  - [ ] Tests offline (synthetic prices/calendar; injected costs + regime series).
- **Session log:**
  - _(fill at end of session)_

---

## T8 — Metrics (`metrics.py`)

- **Status:** ☐
- **Depends on:** T7 (a `DailySnapshot` series to measure)
- **Goal:** Honest **daily-MTM** metrics from the v2 equity curve (`02` §9, `03` §3
  "Absolute" block). Benchmark-relative metrics are **spec 03** — not here.
- **Do:**
  - From the daily equity curve compute: CAGR (calendar-time annualized), daily-MTM Sharpe
    (mean/stdev daily returns × √252), Sortino, max drawdown + DD duration, **Calmar =
    CAGR / maxDD**, avg/median **exposure**, time-in-cash %, annualized **turnover**,
    annualized volatility.
  - Per-rebalance turnover (Σ|target − current| weights) and a turnover series (`02` §9).
  - Per-name diagnostics (contribution to return, hold-period distribution, hit rate of held
    names) — sanity, not tuning (`03` §3).
  - **Do not** compute benchmark-relative metrics (excess CAGR, Calmar ratio, capture, IR) —
    leave a clean seam for spec 03 to add them.
- **Done-criteria:**
  - [ ] Each metric unit-tested against a hand-constructed equity curve with a known answer
        (e.g. a fixed-CAGR ramp → exact CAGR; a known drawdown → exact maxDD/Calmar).
  - [ ] Sharpe uses **daily** returns × √252 (not step-on-exit — the v1 bug, `00` §2.2).
  - [ ] Turnover computed per rebalance and annualized; flagged absurd if > ~1000% (`02` §10.5).
  - [ ] Tests offline.
- **Session log:**
  - _(fill at end of session)_

---

## T9 — Acceptance suite (`02` §10 as hard tests)

- **Status:** ☐
- **Depends on:** T7, T8
- **Goal:** Encode **all** of `02` §10 as a test suite that gates the simulation core.
  Fail loud (Rule 12).
- **Do — assert each of `02` §10:**
  1. **No-lookahead:** corrupt **future** data (dates > D) and assert decisions/results up
     to D are unchanged (fills at D+1 open enforced).
  2. **Cash conservation:** `equity == cash + Σ shares*price` every day to rounding; total
     cost paid == Σ per-fill costs (re-assert at engine level).
  3. **Determinism:** same config + data → identical equity curve.
  4. **Exposure sanity:** sustained downtrend with `use_regime_overlay=True` → materially
     lower average exposure than overlay off (synthetic downtrend index).
  5. **Turnover sanity:** monthly rebalance with buffer yields plausible annualized turnover;
     flag absurd (> ~1000%).
  6. **v1-direction smoke:** on the same (biased) data, reproduce a v1-style run *direction*
     as a gross-wiring check — **not** a correctness claim (`02` §10.6).
- **Done-criteria:**
  - [ ] All six §10 criteria implemented as tests; each fails if its invariant is broken
        (include a negative test per criterion where practical).
  - [ ] No-lookahead test mutates future rows and asserts byte-identical pre-D results.
  - [ ] Exposure-sanity test shows overlay-on < overlay-off average exposure in a downtrend.
  - [ ] Suite runs offline (synthetic data; no live network, no live yfinance/NSE — Rule 5).
- **Session log:**
  - _(fill at end of session)_

---

## Exit criteria for the whole Simulation Core (spec 02 complete)

- [ ] T0–T9 all ☑.
- [ ] The §10 acceptance suite (T9) passes.
- [ ] An end-to-end run on the **real** spec-01 dataset (2017→present) produces an equity
      curve + exposure curve + fills log + daily-MTM metrics (with the placeholder cost
      model and an injected synthetic/real price index for regime).
- [ ] Determinism + cash-conservation + no-lookahead hold on the real-data run.
- [ ] Clean seams left for spec 03: injectable `costs.fill_cost`, injectable regime price
      index, and a metrics module ready for benchmark-relative additions.
- [ ] v1 remains runnable in parallel (nothing in `backend/app/backtest/` was modified).
