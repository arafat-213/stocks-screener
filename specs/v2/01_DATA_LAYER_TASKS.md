# Spec 01 — Data Layer: Task Breakdown & Build Tracker

> **Purpose.** Decompose `01_DATA_LAYER.md` into small, resumable, session-sized
> tasks so no single session has to build the whole data layer (too expensive in
> tokens). Each task is self-contained: a session loads `00_OVERVIEW.md`,
> `01_DATA_LAYER.md`, this file, and the **one task** it is doing — nothing more.
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
> Done-criteria. Do not tune anything here — tuning lives in spec `04`.

---

## Target module layout (from `01` §3) — for reference

```
backend/app/data/bhavcopy/
  __init__.py
  download.py            # T2
  parse.py               # T3
  corporate_actions.py   # T4
  adjust.py              # T5
  universe.py            # T6
  store.py               # T1
  build.py               # T7
  validate.py            # T8
```

Independent of the FastAPI app and the v1 engine. This is a batch pipeline.

---

## Task graph (dependencies)

```
T0 (research spike)
   └─> T1 (scaffold + store contract)
          ├─> T2 (download)  ──> T3 (parse) ──┐
          ├─> T4 (corporate actions) ─────────┤
          │                                    ├─> T5 (adjust) ─> T6 (universe)
          └────────────────────────────────────┘                     │
                                                                       ▼
                                              T7 (build orchestrator) ─> T8 (validate)
```

T2/T3 and T4 can be done in either order once T1 lands. T5 needs T3 + T4.

---

## T0 — Research & verification spike (NO production code)

- **Status:** ☐
- **Depends on:** —
- **Goal:** Resolve every "verify live" item in `01` §2 and §9 and record findings,
  because the spec forbids writing the loader before these are confirmed.
- **Do:**
  - WebSearch/WebFetch to confirm, with a working example each:
    - Legacy full bhavcopy download URL + schema (`sec_bhavdata_full_DDMMYYYY.csv`?).
    - UDiFF bhavcopy URL + schema, and the **exact cutover date** legacy→UDiFF.
    - Corporate-actions feed URL + format (splits, bonuses, dividends, ex-dates).
    - Index TRI history source (niftyindices.com) — needed later by `03`; just
      confirm it exists + access method, don't build it here.
    - Decide: maintained wrapper (`jugaad-data` / `nsepython`) vs direct HTTP
      (NSE needs browser headers + warmup cookie + rate limiting). Pick one, justify.
  - Resolve the two open policy questions enough to proceed: **`EQ` only vs `EQ`+`BE`**
    (recommend, with reason), and the **liquidity-floor default** (pick a conservative
    placeholder, e.g. ₹5 cr/day — explicitly "to be tuned in `04`").
  - Probe code is allowed (a throwaway script to fetch one day of each format), but it
    is **not** shipped as a module.
- **Deliverable:** a `## Verified findings` section appended to the TOP of
  `01_DATA_LAYER.md` (per spec: "State your verified findings at the top of the
  implementation"), containing the confirmed URLs, both schemas (column lists),
  cutover date, wrapper decision, and the two policy decisions.
- **Done-criteria:**
  - [ ] One real sample row of each of: legacy bhavcopy, UDiFF bhavcopy, CA feed —
        pasted into findings with column names.
  - [ ] Cutover date stated as an explicit date with a source.
  - [ ] Wrapper-vs-HTTP decision recorded with rationale.
  - [ ] `EQ`-vs-`BE` and liquidity-floor placeholder decisions recorded.
- **Session log:** _(empty)_

---

## T1 — Scaffold + storage contract (`store.py`, package skeleton)

- **Status:** ☐
- **Depends on:** T0
- **Goal:** Create the package and the canonical read/write contract everything else
  targets, so later tasks write against a fixed schema instead of inventing one.
- **Do:**
  - Create `backend/app/data/bhavcopy/__init__.py` and empty stubs for the other
    modules (docstring + `raise NotImplementedError` placeholders) so imports resolve.
  - Implement `store.py`: parquet read/write for the three logical tables in `01` §4 —
    `prices_adjusted`, `universe_membership`, `isin_symbol_map`. Decide and document the
    **storage layout** (`01` §9): fast for both "all ISINs on date D" (membership,
    date-partitioned) and "full history for ISIN X" (prices, ISIN-partitioned). Consider
    single parquet + duckdb. Keep it a thin, typed I/O layer — no business logic.
  - Define the exact column schema (names + dtypes) for each table as code-level
    constants, matching `01` §4 (incl. `close_raw`, `close_tr`, `adj_factor`,
    `tr_factor`, `adv_20`, `traded_value`, `series`).
- **Deliverable:** importable package; `store.py` with schema constants + read/write fns;
  a one-paragraph "storage layout decision" docstring at the top of `store.py`.
- **Done-criteria:**
  - [ ] `from app.data.bhavcopy import store` works; other module stubs import cleanly.
  - [ ] Round-trip test: write a tiny synthetic frame for each table, read it back,
        assert schema + values preserved (mock data, no network — Rule: tests don't hit live).
  - [ ] Schema constants match `01` §4 exactly (no missing columns).
- **Session log:** _(empty)_

---

## T2 — Download layer (`download.py`)

- **Status:** ☐
- **Depends on:** T1, T0 findings
- **Goal:** Fetch raw daily bhavcopy files (both formats by date) into a disk cache,
  idempotently and politely.
- **Do:**
  - Implement fetch for legacy and UDiFF, selecting format by date vs the cutover from T0.
  - Cache to `data/raw/bhavcopy/`; **skip files already present** (idempotent).
  - Backoff + retry on 429/5xx; polite rate limit; browser-like headers + warmup cookie
    if going direct (per T0 decision).
  - Reuse `backend/app/pipeline/ohlcv_cache.py` (`OHLCVCache`) caching ideas where it fits
    (`00` §5), but the source is bhavcopy files, not yfinance.
- **Done-criteria:**
  - [ ] Given a date range, downloads missing files and skips present ones (verify by
        running twice — second run does zero network calls).
  - [ ] Picks correct format for a pre-cutover date and a post-cutover date.
  - [ ] Retry/backoff path unit-tested with a mocked 429 (no live calls in tests).
  - [ ] Non-trading days / missing files handled without crashing the range.
- **Session log:** _(empty)_

---

## T3 — Parse layer (`parse.py`)

- **Status:** ☐
- **Depends on:** T2 (sample files), T0 schemas
- **Goal:** Parse legacy + UDiFF day files into the **unified raw row** schema.
- **Do:**
  - Two parsers (legacy, UDiFF) → one unified schema:
    `(isin, symbol, date, open, high, low, close, volume, traded_value, series)`.
  - Filter to in-scope `series` (per T0 EQ/BE decision). Drop suspended/empty rows.
  - Use `traded_value` from bhavcopy if present, else leave null for `adjust`/`universe`
    to derive (`close_raw × volume`) per `01` §4.
- **Done-criteria:**
  - [ ] Legacy and UDiFF sample files both parse to identical unified schema.
  - [ ] Series filter verified; out-of-scope series excluded.
  - [ ] Golden-file test: small saved legacy + UDiFF fixtures → expected unified frame
        (fixtures committed; tests offline).
  - [ ] ISIN present on every retained row (it is the join key downstream).
- **Session log:** _(empty)_

---

## T4 — Corporate actions (`corporate_actions.py`)

- **Status:** ☐
- **Depends on:** T1, T0 (CA feed format)
- **Goal:** Fetch + parse the CA feed and build, per ISIN, the cumulative back-adjustment
  factor time series (split/bonus) and the dividend series for TR.
- **Do:**
  - Fetch + parse CA feed → records of `(isin, ex_date, type, ratio_or_amount)` for
    splits, bonuses, dividends.
  - Build per-ISIN cumulative **back-adjustment factor** (split/bonus, applied
    multiplicatively on/after each ex-date) and a **dividend factor** stream for TR
    using `(1 - D/close_cum)` reinvestment (`01` §5.3).
  - **Prefer the explicit CA feed over price-gap inference.** If a CA has no clean feed
    entry, **flag it** (collect into an unmatched list) — do not silently infer.
- **Done-criteria:**
  - [ ] Parsed splits/bonuses/dividends with ex-dates for a sample window.
  - [ ] Cumulative factor series is correct for one hand-checked split and one bonus
        (unit test with known ratio).
  - [ ] Unmatched/flagged CAs are surfaced (returned/logged), not dropped silently.
- **Session log:** _(empty)_

---

## T5 — Adjust (`adjust.py`)

- **Status:** ☐
- **Depends on:** T3 (raw prices), T4 (factors)
- **Goal:** Produce fully-adjusted OHLC + `close_tr`, retaining `close_raw` and factors.
- **Do:**
  - Apply split/bonus factor → adjusted `open/high/low/close` (signal prices,
    **no dividend adjustment** — `01` §4 rationale).
  - Apply split+bonus+dividend → `close_tr` (P&L prices). Store `adj_factor`,
    `tr_factor`, and keep `close_raw`.
  - Recompute `traded_value` consistency (`01` §5.4).
- **Done-criteria:**
  - [ ] On a known split ex-date, adjusted series has **no spurious >40% single-day gap**
        (this is also asserted in T8; here verify on one name).
  - [ ] `close_tr` cumulative return ≥ split/bonus-adjusted cumulative return on a sample
        (dividends non-negative — `01` §7.5).
  - [ ] `close_raw`, `adj_factor`, `tr_factor` all present and reconstructable.
- **Session log:** _(empty)_

---

## T6 — Universe membership + liquidity (`universe.py`)

- **Status:** ☐
- **Depends on:** T5 (adjusted prices w/ traded_value), T3 (presence)
- **Goal:** Emit point-in-time `universe_membership` and the `adv_20` liquidity series,
  with **no lookahead**.
- **Do:**
  - `universe_membership`: one row per (isin, date) the instrument actually traded
    (appeared in that day's scoped bhavcopy). This *is* the point-in-time universe.
  - `adv_20`: 20-day rolling **median** of `traded_value` (median, not mean — `01` §5.5).
  - Build `isin_symbol_map` (isin, symbol, first_date, last_date) for renames/reporting.
- **Done-criteria:**
  - [ ] `adv_20` and membership on date D use only data **≤ D** (no lookahead — `01` §7.4).
  - [ ] Rolling window uses median; verified on a synthetic spike (single huge day does
        not blow up adv_20).
  - [ ] `isin_symbol_map` spans renames as one continuous ISIN (sets up T8 check 3).
- **Session log:** _(empty)_

---

## T7 — Build orchestrator (`build.py`)

- **Status:** ☐
- **Depends on:** T2–T6
- **Goal:** End-to-end, **idempotent + resumable** pipeline, checkpointed by date
  (CLAUDE.md Pipeline Laws).
- **Do:**
  - Wire stages 1–7 of `01` §5 in order (download → parse → CA → adjust → liquidity →
    membership → store).
  - Checkpoint by date; resume from last successful date after a crash. Running twice
    must not duplicate or corrupt data (idempotency).
  - Classify/record per-symbol failures rather than crashing the whole run (Pipeline Laws).
- **Done-criteria:**
  - [ ] Full run over a small date range produces all three tables.
  - [ ] Kill mid-run, restart → resumes from checkpoint, final output identical to
        an uninterrupted run (idempotent).
  - [ ] A single bad symbol/day is recorded and skipped, not fatal.
- **Session log:** _(empty)_

---

## T8 — Validation (`validate.py`) — the gate

- **Status:** ☐
- **Depends on:** T7 (a built dataset to validate)
- **Goal:** Implement **all** acceptance checks from `01` §7. **Fail loud**, never
  warn-and-continue. The data layer is **not done** until this passes.
- **Do — assert each of `01` §7:**
  1. ~5 hard-coded known NSE split/bonus events adjust correctly (no spurious >40% gap on
     ex-date; ratio matches documented split/bonus).
  2. Survivorship sanity: universe contains ISINs with `last_date` well before today
     (delisted names present); count them; **zero delisted ⇒ FAIL**.
  3. ISIN continuity across a known rename: one continuous ISIN spans both symbols, no gap.
  4. No lookahead in `adv_20`/membership (≤ D only).
  5. `close_tr` cumulative ≥ split/bonus-adjusted cumulative on a sample.
  6. Coverage report: rows, distinct ISINs, distinct delisted ISINs, date range,
     % days with gaps, CA events applied vs flagged-unmatched.
- **Done-criteria:**
  - [ ] All six checks implemented as hard assertions that fail the build.
  - [ ] The 5 known-CA names are real, liquid, with documented ratios cited in comments.
  - [ ] Coverage report prints and the numbers are sane on a real multi-year run.
  - [ ] Running validate on a deliberately-broken dataset fails loudly (negative test).
- **Session log:** _(empty)_

---

## Exit criteria for the whole Data Layer (spec 01 complete)

- [ ] T0–T8 all ☑.
- [ ] `validate.py` passes on a real multi-year build (e.g. 2018→present).
- [ ] Coverage report reviewed by Arafat; delisted-name count is non-trivial.
- [ ] Canonical `prices_adjusted` / `universe_membership` / `isin_symbol_map` are
      readable via `store.py` by a downstream consumer (sets up spec `02`).
- [ ] v1 remains runnable in parallel (nothing in v1 was modified).
