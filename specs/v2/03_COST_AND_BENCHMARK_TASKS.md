# Spec 03 — Cost Model & Benchmark: Task Breakdown & Build Tracker

> **Purpose.** Decompose `03_COST_AND_BENCHMARK.md` into small, resumable,
> session-sized tasks so no single session has to build the whole cost +
> benchmark layer (too expensive in tokens). Each task is self-contained: a
> session loads `00_OVERVIEW.md`, `03_COST_AND_BENCHMARK.md`, this file, and the
> **one task** it is doing — nothing more.
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
> Done-criteria. Do not tune cost rates or slippage coefficients to flatter the
> backtest — calibrate conservatively; tuning/sweeps live in spec `04`.

---

## What this layer plugs into (already built — specs 01 + 02)

The simulation core is **complete and validated** (see `02_SIMULATION_CORE_TASKS.md`
exit criteria: T0–T9 ☑, 218/218 tests, real-data run clean after the leverage fix).
Spec 03 swaps the two placeholders the core left behind and adds the benchmark seam:

- **`app.backtest_v2.costs`** — currently a **flat-bps placeholder** (`CostConfig`,
  `fill_cost(side, qty, price, adv_20, cfg) -> float`, `CostFn` type alias). The
  engine and portfolio already accept `cost_fn` + `cost_cfg` injected (`engine.run`
  params, `Portfolio.apply_fills`). Spec 03 replaces the model behind that seam.
- **`app.backtest_v2.metrics`** — currently **absolute** daily-MTM metrics only
  (CAGR, Sharpe, Sortino, maxDD, Calmar, exposure, turnover, per-name). The module
  docstring explicitly reserves the benchmark-relative block for spec 03.
- **`app.backtest_v2.regime`** — `RegimeOverlay` already takes an **injected**
  price-index series (`engine.run(index_prices=...)`). Spec 03 supplies the real
  price index that feeds it (`03` §2.3).

**Reuse / read, do NOT rewrite (`00` §5):**
- `app.data.bhavcopy.store` for `adv_20` (slippage scales by participation = order
  value / `adv_20`, `03` §1.2). It is already a first-class per-row column.
- `OHLCVCache`-style atomic-write + `CACHE_DIR` caching *ideas* for the TRI cache.

### ⚠ Load-bearing integration fact — the cost seam is currently *fee-only*

`Portfolio.apply_fills` (`portfolio.py:142`) uses `fill.price` verbatim and treats
`cost_fn`'s return value as a **₹ cash deduction only**. But `03` §1.3 is emphatic:
**slippage must be realized by adjusting the *effective fill price*** (buys fill
higher, sells fill lower) so it also moves **cost basis / realized P&L** — *not* as a
fee-only term. Statutory + flat (STT, DP, exchange, SEBI, stamp, GST) are the cash
deduction; **slippage is a price adjustment.** Wiring this correctly requires
extending the seam beyond a one-line function swap (see **T1 §Do**). Acceptance
`03` §4.2 ("slippage moves cost basis") fails if this is done as a fee.

---

## Target module layout (from `03` §1–§3) — for reference

```
backend/app/backtest_v2/
  costs.py        # T1 — REPLACE placeholder: statutory + DP + slippage (effective price)
  benchmark.py    # T2 — NEW: TRI loaders (3) + price index for regime; align/rebase
  metrics.py      # T3 — ADD benchmark-relative block (excess CAGR, Calmar ratio, IR, capture, beta)
  engine.py       # T4 — cost level as first-class run param (optimistic/base/pessimistic)
  run_real.py     # T4/T5 — three-cost-level report + benchmark-relative print on real data
```

Keep **entirely separate** from `backend/app/backtest/` (v1). v1 must stay runnable.
`benchmark.py` lives in `backtest_v2/` (benchmark-specific, not part of the bhavcopy
data layer); its TRI cache lands under gitignored `backend/data/`.

---

## Task graph (dependencies)

```
T0 (verify rates + niftyindices download method + slippage calibration — NO production code)
   ├─> T1 (real cost model: statutory + DP + slippage via effective fill price)
   │        └─────────────────────────────┐
   └─> T2 (benchmark.py: TRI loaders + price index; align/rebase)                 │
            └─> T3 (benchmark-relative metrics)                                    │
                   │                                                               │
   ┌───────────────┴───────────────────────────────────────────────────────────┘
   ▼
  T4 (cost level = first-class run param; three-cost-level report)  needs T1 (+T3 for full report)
        └─> T5 (acceptance suite — §4 as hard tests)  needs T1,T2,T3,T4
```

T1 and T2 are independent once T0 lands and can be done in either order. T3 needs T2.
T4 needs T1 (and T3 to render the full headline). T5 gates the whole layer.

---

## T0 — Verification spike (NO production code)

- **Status:** ☑
- **Depends on:** — (specs 01 + 02 done)
- **Goal:** Resolve every "verify at build time" item in `03` (§1.1 rates change,
  §1.2 slippage calibration, §2.1 TRI source/download method). The spec forbids
  baking in stale rates or a guessed download method.
- **Do:**
  - **Cost rates (`03` §1.1)** — verify current Zerodha **delivery** equity rates via
    web research, with a source link each: STT (buy+sell %), NSE exchange txn charge,
    SEBI charges, stamp duty (buy only), GST (on brokerage+txn), DP charges (flat ₹ per
    scrip on sell). Brokerage = ₹0 (delivery). Record the exact numbers you'll hardcode.
  - **Slippage calibration (`03` §1.2)** — pick `base_slippage_pct` (≈0.15%/side
    placeholder) and an `impact_coeff` such that a 1%-of-ADV order adds ≈0.1–0.2%.
    Cite the literature/reasoning. State the participation ceiling (cap position if
    order > ~5–10% of ADV) — conservative, tuned later in `04`, not optimized down here.
  - **Benchmark TRI source (`03` §2.1)** — confirm the niftyindices.com historical
    TRI download method (POST form? CSV endpoint? warmup cookie like NSE?) for:
    **Nifty200 Momentum 30 TRI** (primary), **Nifty Midcap150 Momentum 50 TRI**
    (secondary), **Nifty 50 TRI** (large-cap floor). Capture one verbatim TRI data row
    with column names per series.
  - **Regime price index (`03` §2.3)** — confirm the **price** (not TRI) index source
    for the regime 200-DMA: Nifty 50 or Nifty 200 price index. Note download method.
  - Probe code (a throwaway script to fetch one TRI file + one cost calc) is allowed but
    **not** shipped as a module.
- **Deliverable:** a `## Verified findings (T0)` section appended to the **top** of
  `03_COST_AND_BENCHMARK.md` with: the confirmed cost rates (table), the slippage
  defaults + calibration rationale, the TRI download method + one verbatim row per
  series, and the regime price-index source + method.
- **Done-criteria:**
  - [x] Each cost component has a verified current rate + source link (Rule 12 — no
        guessed rates silently shipped).
  - [x] `base_slippage_pct` + `impact_coeff` + participation ceiling chosen, with the
        1%-of-ADV ≈ 0.1–0.2% calibration shown.
  - [x] niftyindices TRI download method confirmed working, with one verbatim row +
        column names for each of the 3 TRI series.
  - [x] Regime **price** index source + download method confirmed (distinct from TRI).
- **Session log:**
  - 2026-06-15: All four T0 items verified live. Zerodha charges fetched from
    zerodha.com/charges + Oct 2024 revision article. NSE exchange txn revised to
    0.00297% (was 0.00322%) effective Oct 1, 2024. DP = ₹15.34/scrip/sell. Slippage
    defaults: base 0.15%/side, impact_coeff 0.15, cap 10% ADV (calibration: 1% ADV
    participation → +0.15% additional, within spec target). niftyindices POST API
    confirmed for getTotalReturnIndexString (TRI) and getHistoricaldatatabletoString
    (price). Verbatim rows fetched for all 3 TRI series. Regime: Nifty 50 price index
    (CLOSE column). All findings written to `## Verified findings (T0)` section at top
    of 03_COST_AND_BENCHMARK.md. No production code written.

---

## T1 — Real cost model (`costs.py`) — statutory + DP + slippage

- **Status:** ☑
- **Depends on:** T0
- **Goal:** Replace the flat-bps placeholder with the real per-fill cost model:
  statutory + DP charges as a **cash deduction**, slippage as an **effective-price**
  adjustment that moves cost basis (`03` §1.1–§1.3).
- **Do:**
  - Extend `CostConfig` with the verified-rate fields from T0 (STT %, exchange txn %,
    SEBI %, stamp duty %, GST %, DP flat ₹, `base_slippage_pct`, `impact_coeff`,
    participation cap). Keep dataclass defaults = the T0 verified base numbers.
  - Implement statutory + DP per-fill ₹ cost per side (`03` §1.1 table): STT both
    sides, exchange/SEBI both sides, stamp duty buy-only, GST on (brokerage+txn), DP
    flat on sell. Keep `fill_cost(side, qty, price, adv_20, cfg) -> float` returning
    **total ₹ statutory+flat cost** so the existing `apply_fills` cash path is intact.
  - **Slippage as effective price (`03` §1.3, the load-bearing part):** add a function
    that returns the **effective fill price** —
    `effective_price(side, price, qty, adv_20, cfg)` where
    `participation = order_value/adv_20`,
    `slippage_pct = base + impact_coeff*participation` (clamped to a ceiling); buys fill
    `price*(1+slippage_pct)`, sells `price*(1-slippage_pct)`.
  - **Extend the seam (touches portfolio + engine):** apply the effective price to the
    fill **before** `apply_fills` records it, so cost basis & realized P&L reflect
    slippage (not a fee). Minimal surgical options — pick one and document:
    (a) the engine slips the fill price when stamping next-open fills, then `apply_fills`
    uses statutory-only `fill_cost`; or (b) `apply_fills` slips internally via an injected
    `slippage_fn`. **Prefer (a)** — keeps slippage in the engine's fill-stamping step next
    to `_stamp_fills`/`_clamp_buys_to_cash`, leaves `apply_fills` cash mechanics unchanged.
  - Update the module docstring (remove "PLACEHOLDER"); cite T0 rates + sources.
- **Done-criteria:**
  - [x] Statutory + DP ₹ cost matches a hand-worked example per side (STT, stamp duty
        buy-only, DP flat on sell) — unit-tested against T0 rates.
  - [x] Slippage moves the **effective fill price** (buy higher, sell lower) and thus
        **cost basis** — not a fee-only term (`03` §4.2). Unit test asserts a buy's
        cost basis > raw open, and a freshly-bought name shows slightly negative
        realized return pre-move.
  - [x] Slippage scales with participation = order_value/`adv_20`; low-ADV names pay
        more; clamped at the ceiling (unit test at small and large participation).
  - [x] `fill_cost` signature unchanged (drop-in); engine + portfolio still run; the
        existing passing tests still pass (the seam extension is additive). Note: 4
        test files have a pre-existing `types → schemas` import error (from commit
        a9bb163c); 8 regime tests pre-fail from an in-progress regime.py change.
        No regressions introduced: 93 pass (was 79), 8 fail (same 8 as before).
- **Session log:**
  - 2026-06-15: Replaced flat-bps placeholder with real statutory + slippage model.
    `CostConfig` extended with T0-verified fields (stt_pct, exchange_txn_pct, sebi_pct,
    stamp_duty_pct, gst_pct, dp_charge, base_slippage_pct, impact_coeff, participation_cap).
    `fill_cost()` computes statutory + DP cash deduction; `effective_price()` added for
    slippage adjustment. Engine `_stamp_fills` extended (option a) to slip fill prices
    before `apply_fills` — slippage moves cost basis, not a fee-only term. Legacy
    `round_trip_bps` field kept for backwards-compat with spec-02 test suites (zero
    additional changes needed to existing test files). 24 new T1 tests pass; 0 regressions.

---

## T2 — Benchmark wiring (`benchmark.py`) — TRI loaders + regime price index

- **Status:** ☑
- **Depends on:** T0 (download method)
- **Goal:** Load the benchmark TRIs and the regime price index, calendar-aligned and
  warmup-sliced, rebased to starting capital (`03` §2.1–§2.3).
- **Do:**
  - Implement download + parse + disk cache (atomic write, `CACHE_DIR` fallback per
    `02` §5 borrowed pattern) for the **3 TRI series** (`03` §2.1): Nifty200 Momentum
    30 TRI (primary), Nifty Midcap150 Momentum 50 TRI (secondary), Nifty 50 TRI
    (floor), via the T0-verified niftyindices method. Skip files already cached
    (idempotent); warmup cookie / headers per T0.
  - Implement the **price** index loader for the regime overlay (`03` §2.3) — Nifty 50
    or Nifty 200 **price** index (per T0). Return a `pd.Series` (DatetimeIndex → close)
    shaped exactly as `engine.run(index_prices=...)` expects.
  - **Alignment (`03` §2.2):** align benchmark to the **same trading calendar** and the
    **same date window** as the run; **slice off the indicator warmup** so warmup
    doesn't dilute benchmark return (the v1 `compute_metrics` bug). Rebase both strategy
    equity and benchmark TRI to the same starting capital at `date_from`. Compute
    benchmark daily returns from TRI closes for apples-to-apples Sharpe.
  - Keep the two roles **distinct**: price index → regime signal; momentum TRI →
    performance benchmark (`03` §2.3). Do not feed the TRI into regime.
- **Done-criteria:**
  - [x] All 3 TRI series load + cache; second call does zero network (idempotent),
        tested offline with a mocked/cached fixture (Rule 5 — no live niftyindices in tests).
  - [x] Benchmark is calendar-aligned to the run window and **warmup-sliced** — a test
        asserts the benchmark series starts at `date_from`, not at `start - warmup`.
  - [x] Strategy + benchmark both rebased to starting capital at `date_from`; benchmark
        daily returns computed from TRI closes.
  - [x] Regime **price** index loader returns a series consumable by
        `engine.run(index_prices=...)` — distinct from the TRI (asserted: different source).
  - [x] Tests offline (committed fixture TRI rows; no live network).
- **Session log:**
  - 2026-06-15: `benchmark.py` created with `load_tri`, `load_price_index`, `align_benchmark`.
    All three TRI constants + price index loader implemented using T0-verified niftyindices
    POST API. Atomic-write cache pattern borrowed from OHLCVCache; parquet files land in
    `backend/data/niftyindices/` (gitignored). Cache is keyed by (index_name, start, end)
    so second call hits disk — zero network (verified by mock call count assertion).
    `align_benchmark` forward-fills TRI onto trading calendar, slices at `date_from`
    (warmup-dropped), rebases to starting_capital at date_from. `_fetch_fn` injectable
    for full offline testing. 26 new tests pass (TestDateHelpers, TestParsers, TestLoadTriCache,
    TestThreeTriSeries, TestLoadPriceIndex, TestAlignBenchmark, TestPriceIndexRegimeCompatibility).
    Pre-existing failures unchanged: 8 regime tests (regime.py in-flight), 4 collection
    errors (types→schemas rename). No regressions.

---

## T3 — Benchmark-relative metrics (`metrics.py`)

- **Status:** ☑
- **Depends on:** T2 (benchmark series), T8/spec-02 absolute metrics (already built)
- **Goal:** Add the benchmark-relative block to `metrics.py` against the clean seam the
  T8 docstring reserved (`03` §3 "Benchmark-relative", §4.5).
- **Do:**
  - Add a benchmark-relative metrics function/dataclass consuming the strategy daily
    equity curve + the aligned/rebased benchmark TRI series from T2. Compute (`03` §3):
    excess CAGR; **Calmar ratio of strategy ÷ Calmar of benchmark** (headline — must be
    > 1); **max-DD ratio (strategy ÷ benchmark)** (target ≤ 0.70); information ratio
    (excess return / tracking error); up/down capture; correlation + beta to benchmark.
  - Reuse the existing absolute-metric helpers (CAGR, maxDD, Calmar) on the benchmark
    series — do **not** duplicate the math; compute benchmark absolute metrics with the
    same functions, then form the ratios.
  - Keep it additive — the absolute block and its 42 tests stay untouched.
- **Done-criteria:**
  - [x] Each benchmark-relative metric unit-tested against a hand-constructed
        strategy+benchmark pair with a known answer (e.g. strategy = 2× benchmark daily
        returns → beta ≈ 2; known maxDDs → exact max-DD ratio).
  - [x] Calmar ratio (strat ÷ bench) and max-DD ratio computed — the pass/fail headline
        numbers (`03` §4.5). A test asserts they're present and finite.
  - [x] IR uses excess return / tracking error; up/down capture split on benchmark sign.
  - [x] Absolute-metric math reused (not re-derived) for the benchmark series.
  - [x] Tests offline.
- **Session log:**
  - 2026-06-15: Added `BenchmarkMetrics` dataclass + `compute_benchmark_metrics()` +
    `benchmark_summary()` to `metrics.py`. `_cagr_from_equity()` extracted as a shared
    helper so both absolute and benchmark paths use the same math (no duplication).
    `_compute_max_drawdown` reused directly for benchmark series. All 6 spec-03 §3
    metrics implemented: excess CAGR, Calmar ratio (strat/bench), max-DD ratio,
    information ratio (excess/tracking-error × √252), up/down capture (split on bench
    sign), correlation + beta. `benchmark_summary()` prints headline ratios prominently
    with pass/fail flags (> 1, ≤ 0.70). 20 new T3 tests pass (5 test classes:
    TestBenchmarkMetricsKnownValues, TestHeadlineRatios, TestInformationRatio,
    TestCapture, TestAbsoluteReuseNotReduplicated, TestEdgeCases).
    No regressions: 139 pass (was 119 before T3), same 8 pre-existing regime failures,
    same 4 collection errors (types→schemas rename, pre-existing).

---

## T4 — Cost level as first-class run parameter + three-cost-level report

- **Status:** ☐
- **Depends on:** T1 (cost model), T3 (for the full headline report)
- **Goal:** Make cost level a first-class run parameter and render the mandatory
  three-cost-level sensitivity report (`03` §1.4, §4.4).
- **Do:**
  - Define the three cost levels (`03` §1.4): **optimistic** (≈0.3% RT, no slippage),
    **base** (the T1 model), **pessimistic** (2× slippage). Express each as a
    `CostConfig` preset (e.g. `CostConfig.optimistic()/base()/pessimistic()` or a
    `cost_level` enum → config) so a run picks one with a single parameter.
  - Thread `cost_level` through `engine.run` (it already accepts `cost_fn`/`cost_cfg`)
    and the `run_real.py` harness so a headline result is reproducible at all three
    levels.
  - Render the report (in `run_real.py` or a small reporting helper): for each cost
    level, print the absolute metrics + the T3 benchmark-relative headline (Calmar
    ratio, max-DD ratio). The edge must survive **base**; if it only exists at
    optimistic, the report makes that obvious (`03` §1.4 — "no edge").
- **Done-criteria:**
  - [ ] Three `CostConfig` presets exist; optimistic = no slippage + ~0.3% RT
        statutory, pessimistic = 2× base slippage (unit-tested: pessimistic cost >
        base > optimistic on the same fill).
  - [ ] `cost_level` is a single run parameter threaded through `engine.run` +
        `run_real.py` (not hand-edited per run).
  - [ ] The three-cost-level report renders for a run (each level → its metric block).
  - [ ] Tests offline for the preset ordering; the real-data report is exercised via the
        `run_real.py` harness (out-of-pytest, depends on the bhavcopy parquet — Rule 5).
- **Session log:**
  - _(fill in at session end)_

---

## T5 — Acceptance suite (`03` §4 as hard tests) — the gate

- **Status:** ☐
- **Depends on:** T1, T2, T3, T4
- **Goal:** Encode **all** of `03` §4 as a test suite that gates the cost + benchmark
  layer. Fail loud (Rule 12).
- **Do — assert each of `03` §4:**
  1. **Cost wired into P&L:** reducing slippage to 0 and statutory to v1's flat 0.25%
     reproduces v1-style cost drag — confirms the model is *in* the P&L path, not bolted
     on cosmetically. (Run two configs; assert the cost delta shows up in the equity curve.)
  2. **Slippage moves cost basis:** a buy's realized return starts slightly negative
     pre-move (re-assert at engine level, complementing the T1 unit test).
  3. **Benchmark loaded + aligned + warmup-sliced:** benchmark TRI Sharpe/Calmar
     computed on the aligned window (no warmup dilution).
  4. **Three-cost-level report renders** for any run (optimistic/base/pessimistic).
  5. **Headline ratios printed prominently:** max-DD ratio and Calmar ratio vs benchmark
     computed and surfaced — the pass/fail numbers for the whole project (`03` §4.5).
- **Done-criteria:**
  - [ ] All five §4 criteria implemented as tests; each fails if its invariant breaks
        (include a negative test per criterion where practical).
  - [ ] Criterion 1: an explicit zero-slippage + 0.25%-flat config reproduces a v1-style
        drag and differs measurably from the base model on the same data.
  - [ ] Criterion 5: Calmar ratio + max-DD ratio vs benchmark are asserted present,
        finite, and printed.
  - [ ] Suite runs offline (synthetic equity/benchmark; cached/fixture TRI — no live
        niftyindices/NSE, Rule 5).
- **Session log:**
  - _(fill in at session end)_

---

## Exit criteria for the whole Cost + Benchmark layer (spec 03 complete)

- [ ] T0–T5 all ☑.
- [ ] The §4 acceptance suite (T5) passes.
- [ ] A real-data run (`run_real.py`, 2017→present) renders the **three-cost-level
      report** with the benchmark-relative headline (Calmar ratio, max-DD ratio vs
      Nifty200 Momentum 30 TRI) at optimistic / base / pessimistic.
- [ ] The edge (if any) is evaluated at **base** cost, not optimistic — reviewed by Arafat.
- [ ] Clean seams preserved for spec 04 (sweeps): `cost_level` is a run parameter;
      benchmark series + regime price index are injectable; metrics module exposes both
      absolute and benchmark-relative blocks.
- [ ] v1 remains runnable in parallel (nothing in `backend/app/backtest/` modified).
</content>
</invoke>
