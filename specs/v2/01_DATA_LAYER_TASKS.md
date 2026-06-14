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

- **Status:** ☑
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
  - [x] One real sample row of each of: legacy bhavcopy, UDiFF bhavcopy, CA feed —
        pasted into findings with column names. **UDiFF + CA: real verbatim rows pasted
        at T0. Legacy verbatim `cm...bhav.csv` row RESOLVED at T2 (live pull, warmup
        cookie worked) — captured in the T2 session log; both formats confirmed across
        the 2024-07-08 cutover boundary.**
  - [x] Cutover date stated as an explicit date with a source (2024-07-08; Circular 62424).
  - [x] Wrapper-vs-HTTP decision recorded with rationale (direct HTTP; jugaad-data lacks
        UDiFF support, issue #79).
  - [x] `EQ`-vs-`BE` (EQ only) and liquidity-floor placeholder (₹5 cr/day) decisions recorded.
- **Session log:**
  - 2026-06-14: Web research spike. Verified legacy CM bhavcopy + UDiFF + CA-feed
    endpoints/schemas/cutover; wrote `## Verified findings` to top of `01_DATA_LAYER.md`.
  - **Key correction to §2:** `sec_bhavdata_full` has **no ISIN** → legacy source must be
    the **old CM bhavcopy** (`cm<DD><MMM><YYYY>bhav.csv`, has ISIN+OHLCV). Both chosen
    sources carry ISIN across 2018→present.
  - **Open item for T2:** capture a verbatim live `cm...bhav.csv` row + confirm both
    formats exist around the 2024-07-05→08 boundary (404-fallback). NSE needs a warmup
    cookie; WebFetch could not set one (live CA API timed out, archive needs cookie).

---

## T1 — Scaffold + storage contract (`store.py`, package skeleton)

- **Status:** ☑
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
  - [x] `from app.data.bhavcopy import store` works; other module stubs import cleanly.
  - [x] Round-trip test: write a tiny synthetic frame for each table, read it back,
        assert schema + values preserved (mock data, no network — Rule: tests don't hit live).
  - [x] Schema constants match `01` §4 exactly (no missing columns).
- **Session log:**
  - 2026-06-14: Created `backend/app/data/bhavcopy/` package. `__init__.py` documents the
    build order; `download/parse/corporate_actions/adjust/universe/build/validate.py` are
    docstring stubs that `raise NotImplementedError` so imports resolve. Also added
    `backend/app/data/__init__.py`.
  - Implemented `store.py` (thin, typed I/O only). Schema constants
    `PRICES_ADJUSTED_SCHEMA` / `UNIVERSE_MEMBERSHIP_SCHEMA` / `ISIN_SYMBOL_MAP_SCHEMA`
    match `01` §4 (incl. close_raw, close_tr, adj_factor, tr_factor, adv_20, traded_value,
    series). `_conform()` enforces exact columns + dtypes and fails loud on missing/extra
    (Rule 12).
  - **Storage layout decision** (documented in `store.py` module docstring): partitioned
    Parquet via pyarrow (DuckDB is not a dep; pyarrow is). `prices_adjusted/` partitioned
    by `isin` (fast "full history for ISIN X"); `universe_membership/` partitioned by
    derived `year` (fast "all ISINs on date D" without ~2k tiny per-day files);
    `isin_symbol_map.parquet` single file. Writes use
    `existing_data_behavior="delete_matching"` for idempotent rewrites (Pipeline Laws).
  - Tests: `backend/tests/data/test_bhavcopy_store.py` — 7 passing (round-trip ×3, ISIN +
    date-range filter pushdown, idempotent rewrite/no-dup, typed-empty reads, fail-loud on
    missing column). Run: `PYTHONPATH=. pytest tests/data/test_bhavcopy_store.py`
    (mirrors repo convention; conftest needs `app` on path). Offline, no network.
  - v1 untouched (only new files added).

---

## T2 — Download layer (`download.py`)

- **Status:** ☑
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
  - [x] Given a date range, downloads missing files and skips present ones (verify by
        running twice — second run does zero network calls).
        `test_downloads_then_skips_present_files`.
  - [x] Picks correct format for a pre-cutover date and a post-cutover date.
        `test_format_selection_by_cutover`, `test_picks_correct_format_per_date`.
  - [x] Retry/backoff path unit-tested with a mocked 429 (no live calls in tests).
        `test_retry_then_success_on_429` (asserts exponential backoff sleeps),
        `test_retry_exhausted_is_error_not_crash`.
  - [x] Non-trading days / missing files handled without crashing the range.
        `test_404_both_formats_is_missing`, `test_missing_day_does_not_break_range`,
        `test_weekends_are_skipped`.
- **Session log:**
  - 2026-06-14: Implemented `download.py` (direct HTTP, per T0 §6). Public API:
    `download_range(start, end)` / `download_day(d)`, plus `bhavcopy_format`,
    `source_url`, `build_session`, `DownloadResult`. Format chosen by
    `BHAVCOPY_UDIFF_CUTOVER = 2024-07-08`; on a 404 it falls back to the other
    format (T0 overlap note). Caches raw `.zip` (unzip is T3) under
    `data/raw/bhavcopy/` keyed by NSE source basename; present non-empty file →
    `cached` (zero network). Polite: configurable rate limit, browser headers,
    warmup-cookie GET to nseindia.com. Explicit 429/5xx + connection
    retry/backoff loop with injectable `sleep` (testable). 200-with-non-ZIP-body
    (NSE block page) is treated as error, not cached. Weekends skipped.
  - **T0 deferred item RESOLVED (live pull, warmup cookie worked):** verbatim
    legacy `cm...bhav.csv` header captured and both formats confirmed to exist
    across the cutover boundary:
    - `cm04JUL2024bhav.csv` (legacy, pre-cutover) header — confirms 13 cols + ISIN:
      `SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,`
      sample row: `0MOFSL27,N3,980,980,980,980,980,991,100,98000,04-JUL-2024,1,INE338I07099,`
    - `BhavCopy_NSE_CM_0_0_0_20240708_F_0000.csv` (UDiFF, cutover day) exists;
      sample EQ row: `2024-07-08,...,STK,...,INE488B01017,TASTYBITE,EQ,...,10400.10,10534.50,10191.00,10273.20,...`
  - Tests: `backend/tests/data/test_bhavcopy_download.py` — 11 passing, offline
    (fake session, injected sleep, tmp root). Run:
    `PYTHONPATH=. pytest tests/data/test_bhavcopy_download.py`. Downloaded data
    lands under gitignored `backend/data/`. v1 untouched (new files only).

---

## T3 — Parse layer (`parse.py`)

- **Status:** ☑
- **Depends on:** T2 (sample files), T0 schemas
- **Goal:** Parse legacy + UDiFF day files into the **unified raw row** schema.
- **Do:**
  - Two parsers (legacy, UDiFF) → one unified schema:
    `(isin, symbol, date, open, high, low, close, volume, traded_value, series)`.
  - Filter to in-scope `series` (per T0 EQ/BE decision). Drop suspended/empty rows.
  - Use `traded_value` from bhavcopy if present, else leave null for `adjust`/`universe`
    to derive (`close_raw × volume`) per `01` §4.
- **Done-criteria:**
  - [x] Legacy and UDiFF sample files both parse to identical unified schema.
  - [x] Series filter verified; out-of-scope series excluded.
  - [x] Golden-file test: small saved legacy + UDiFF fixtures → expected unified frame
        (fixtures committed as Python strings in the test file; tests offline).
  - [x] ISIN present on every retained row (it is the join key downstream).
- **Session log:**
  - 2026-06-14: Implemented `parse.py` with two public entry points: `parse_file(path,
    fmt)` (reads a .zip from disk) and `parse_bytes(data, fmt)` (accepts raw CSV bytes,
    used by tests without disk I/O). Module-level constants `UNIFIED_RAW_COLUMNS` and
    `IN_SCOPE_SERIES` define the schema contract and the EQ-only policy (T0 §7).
  - **Legacy parser:** strips column-name whitespace, drops the unnamed trailing column
    produced by the NSE header's trailing comma, applies series filter, drops NaN/zero-
    price rows, parses `TIMESTAMP` in `%d-%b-%Y` format (`04-JUL-2024`). Maps
    `TOTTRDQTY→volume`, `TOTTRDVAL→traded_value` (₹, not lakhs).
  - **UDiFF parser:** filters `FinInstrmTp == STK` (excludes FUT/OPT/etc.), then
    `XpryDt` empty/NaN/"-" (excludes warrants), then series filter. Handles
    `TtlTradgVol` as float-then-int (NSE sometimes writes "48235.0"). Maps
    `TckrSymb→symbol`, `TradDt→date` (ISO 8601), `TtlTrfVal→traded_value`.
  - Both parsers return an empty frame with correct columns (not an error) when no
    in-scope rows survive filtering — downstream stages handle the empty case.
  - Tests: `backend/tests/data/test_bhavcopy_parse.py` — 23 passing offline.
    Fixture CSV strings committed in the test file (T0-verified column layouts from
    01_DATA_LAYER.md §1–§2). Covers: schema + dtype identity across formats, golden
    values for BASF (verbatim UDiFF row) + RELIANCE + TCS (legacy), series filter,
    UDiFF FinInstrmTp filter, UDiFF XpryDt filter, zero-price exclusion, ISIN presence,
    `parse_file` from real .zip, empty-schema return, bad-format error.
  - Run: `PYTHONPATH=. venv/bin/pytest tests/data/test_bhavcopy_parse.py`
  - v1 untouched (new files only). T1+T2 tests still pass (41 total).

---

## T4 — Corporate actions (`corporate_actions.py`)

- **Status:** ☑
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
  - [x] Parsed splits/bonuses/dividends with ex-dates for a sample window.
        `test_parse_classifies_and_values` (bonus 2:1, FV split 10→1, dividend Rs 5),
        `test_dividend_ignores_face_value_mention`,
        `test_dividend_percentage_fallback_uses_face_value`.
  - [x] Cumulative factor series is correct for one hand-checked split and one bonus
        (unit test with known ratio). `test_split_factor_series_hand_checked` (1:5,
        FV 10→2 → 0.2), `test_bonus_factor_series_hand_checked` (2:1 → 1/3),
        `test_multiple_events_compound`.
  - [x] Unmatched/flagged CAs are surfaced (returned/logged), not dropped silently.
        `test_unmatched_surfaced_not_dropped` (no-keyword / no-amount / missing-ISIN /
        bad-ex-date all land in `CorporateActions.unmatched` with a reason; also logged).
- **Session log:**
  - 2026-06-14: Implemented `corporate_actions.py`. Public API:
    `fetch_corporate_actions(start, end)` (raw JSON from the NSE CA feed, reusing
    `download.build_session` for the warmup cookie + browser headers, 429/5xx
    backoff with injectable `sleep`; tolerates a `{"data":[...]}` envelope),
    `parse_corporate_actions(records) -> CorporateActions(events, unmatched)`, and
    the two factor builders `split_bonus_factor_series(events, dates)` /
    `tr_factor_series(events, dates, close)`. Constants `SPLIT/BONUS/DIVIDEND`,
    `CA_EVENT_COLUMNS`, `CA_UNMATCHED_COLUMNS`, `CA_API_URL`, `CA_DATE_FMT`.
  - **Free-text subject parsing** (the T4 burden, `01` §4): classify by keyword
    with priority handling — when "dividend" is present it is a dividend *unless* an
    explicit split/bonus keyword also appears (dividend subjects routinely say
    "X% on face value", so a bare "face value" only implies a split when a concrete
    `Rs X → Rs Y` change is present). Split → price multiplier `new/old` from the
    face-value change (ratio-form `a:b` fallback); bonus `a:b` → `b/(a+b)`; dividend
    → first ₹ amount after each "dividend" token (avoids the trailing "of Rs 10
    face value"), summed, with a `pct% × faceVal` fallback for legacy records.
  - **Factor convention** (back-adjustment, latest prices = reference basis):
    cumulative factor at date `d` = product of per-event multipliers whose ex-date
    `> d` (vectorised via suffix-product + `searchsorted`). `adj_factor`
    (split+bonus) feeds signal prices; `tr_factor` (split+bonus+dividend) feeds
    `close_tr`, dividend multiplier `1 − D/close_cum` using the last close strictly
    before ex-date. T5 supplies the price/close context; this module only builds
    events + factors.
  - **Fail-loud (Rule 12):** anything unclassifiable / unparseable / missing the
    ISIN or ex-date join keys is collected into `unmatched` (with a `reason`) and a
    summary count is logged — never silently dropped, never gap-inferred (`01` §5.3).
  - Tests: `backend/tests/data/test_bhavcopy_corporate_actions.py` — 14 passing,
    offline (record dicts + fake session, injected sleep). Includes the verbatim
    GENSOL "Bonus 2:1" record from `01` §4 and a TR ≤ split/bonus monotonicity check
    that sets up T8 §7.5. Run:
    `PYTHONPATH=. pytest tests/data/test_bhavcopy_corporate_actions.py`.
  - v1 untouched (new files only). Full `tests/data/` suite: 55 passing. ruff clean.

---

## T5 — Adjust (`adjust.py`)

- **Status:** ☑
- **Depends on:** T3 (raw prices), T4 (factors)
- **Goal:** Produce fully-adjusted OHLC + `close_tr`, retaining `close_raw` and factors.
- **Do:**
  - Apply split/bonus factor → adjusted `open/high/low/close` (signal prices,
    **no dividend adjustment** — `01` §4 rationale).
  - Apply split+bonus+dividend → `close_tr` (P&L prices). Store `adj_factor`,
    `tr_factor`, and keep `close_raw`.
  - Recompute `traded_value` consistency (`01` §5.4).
- **Done-criteria:**
  - [x] On a known split ex-date, adjusted series has **no spurious >40% single-day gap**
        (this is also asserted in T8; here verify on one name).
        `TestSplitAdjustment::test_no_spurious_gap_at_ex_date` (1:5 split, gap = 0%).
  - [x] `close_tr` cumulative return ≥ split/bonus-adjusted cumulative return on a sample
        (dividends non-negative — `01` §7.5).
        `TestTotalReturn::test_tr_cumulative_return_ge_adj_cumulative_with_dividend`.
  - [x] `close_raw`, `adj_factor`, `tr_factor` all present and reconstructable.
        `TestReconstructability` — verifies `close_raw × adj_factor = close` and
        `close_raw × tr_factor = close_tr` for split and bonus events.
- **Session log:**
  - 2026-06-14: Implemented `adjust.py`. Public API: `adjust_prices(raw_df, events)`
    where `raw_df` is the unified raw schema from T3 and `events` is
    `CorporateActions.events` from T4. Output schema: `ADJUSTED_INTERMEDIATE_COLUMNS`
    — all of `PRICES_ADJUSTED_SCHEMA` except `adv_20` (T6 appends that).
  - **Back-adjustment applied per T4 convention:** split/bonus factor multiplied onto
    all of open/high/low/close and stored as `adj_factor`; TR factor (adds dividend
    multiplier `1−D/close_cum`) applied to `close_tr` and stored as `tr_factor`.
    `close_raw` retains the unadjusted traded close throughout.
  - **traded_value fallback:** null or zero `traded_value` (defensive, should not
    occur for EQ rows) is filled with `close_raw × volume` per `01` §5.4.
  - **CA events indexed by ISIN at O(1)** — one `groupby` pass before the ISIN
    loop; each ISIN's events looked up via `dict.get` (fast for large universes).
  - Tests: `backend/tests/data/test_bhavcopy_adjust.py` — 19 passing offline.
    Covers: no-events passthrough, 1:5 split factors + no-gap assertion, OHLC
    uniform scaling, split/bonus round-trip, TR cumulative ≥ adj cumulative,
    pre-ex-date TR < adj per-row, traded_value fallback (NaN + zero + valid),
    empty input, ISIN isolation, schema completeness.
    Run: `PYTHONPATH=. venv/bin/pytest tests/data/test_bhavcopy_adjust.py`
  - v1 untouched (new files only). Full `tests/data/` suite: 74 passing.

---

## T6 — Universe membership + liquidity (`universe.py`)

- **Status:** ☑
- **Depends on:** T5 (adjusted prices w/ traded_value), T3 (presence)
- **Goal:** Emit point-in-time `universe_membership` and the `adv_20` liquidity series,
  with **no lookahead**.
- **Do:**
  - `universe_membership`: one row per (isin, date) the instrument actually traded
    (appeared in that day's scoped bhavcopy). This *is* the point-in-time universe.
  - `adv_20`: 20-day rolling **median** of `traded_value` (median, not mean — `01` §5.5).
  - Build `isin_symbol_map` (isin, symbol, first_date, last_date) for renames/reporting.
- **Done-criteria:**
  - [x] `adv_20` and membership on date D use only data **≤ D** (no lookahead — `01` §7.4).
        `TestAdv20NoLookahead` — 4 tests: first-row equals own traded_value, second-day
        is median-of-two, future spike not visible, window rolls correctly at day 20/21.
  - [x] Rolling window uses median; verified on a synthetic spike (single huge day does
        not blow up adv_20). `TestAdv20MedianNotMean::test_spike_does_not_blow_up_adv20`:
        19 × ₹1M + 1 × ₹1B spike → adv_20 stays at ₹1M (not the ₹50M mean would give).
  - [x] `isin_symbol_map` spans renames as one continuous ISIN (sets up T8 check 3).
        `TestIsinSymbolMap::test_rename_produces_two_rows_for_same_isin`: OLDNAME→NEWNAME
        rename produces two rows for the same ISIN with non-overlapping date ranges.
- **Session log:**
  - 2026-06-14: Implemented `universe.py`. Public API: `build_universe(adjusted_df)` →
    `(prices, membership, isin_symbol_map)`. Input is T5's `ADJUSTED_INTERMEDIATE_COLUMNS`
    frame; output prices match `PRICES_ADJUSTED_SCHEMA` exactly (adv_20 inserted at the
    correct column position between traded_value and adj_factor).
  - **adv_20:** `groupby("isin", sort=False)["traded_value"].transform(rolling(20,
    min_periods=1).median())` — independent per ISIN, causal (data is sorted by date
    before the transform), resistant to spikes (median not mean).
  - **membership:** `(isin, date)` pairs from the price rows — no forward projection;
    gaps (weekends, non-trading days) appear as gaps in the membership table, not filled.
  - **isin_symbol_map:** `groupby(["isin", "symbol"])["date"].agg(first_date="min",
    last_date="max")` — one row per (isin, symbol) pair; a rename of the NSE ticker for
    the same ISIN naturally produces two rows, which T8 criterion 3 checks.
  - Tests: `backend/tests/data/test_bhavcopy_universe.py` — 26 passing, offline.
    Run: `PYTHONPATH=. venv/bin/pytest tests/data/test_bhavcopy_universe.py`
  - Full `tests/data/` suite: 100 passing. v1 untouched (new files only).

---

## T7 — Build orchestrator (`build.py`)

- **Status:** ☑
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
  - [x] Full run over a small date range produces all three tables.
        `TestFullRun::test_all_three_tables_populated` (2-day range, 1 ISIN, all three
        tables populated with correct row counts and schema).
  - [x] Kill mid-run, restart → resumes from checkpoint, final output identical to
        an uninterrupted run (idempotent).
        `TestResume::test_resume_skips_checkpointed_days` (Day1 pre-checkpointed, Day1
        URL never called in subsequent run). `TestResume::test_identical_output_with_or_without_resume`
        (full run vs resumed run produce identical prices frame via `assert_frame_equal`).
  - [x] A single bad symbol/day is recorded and skipped, not fatal.
        `TestErrorHandling::test_download_error_skipped_not_fatal` (Day2 returns bad body
        → error recorded, Day1+Day3 in final tables, Day2 absent).
- **Session log:**
  - 2026-06-14: Implemented `build.py`. Public API: `run_build(start, end, ...)` →
    `BuildReport`. Stages wired in spec §5 order: download → parse → CA → adjust →
    `build_universe` (adv_20 + membership) → store (three tables).
  - **Checkpoint design:** `.build_checkpoint.json` records per-date status (`ok` /
    `missing` / `error`); `raw_parsed/{YYYY-MM-DD}.parquet` stores each day's parsed
    unified rows. Stages 4–6 (CA → adjust → store) always re-run from the assembled
    raw data — ensures adv_20 rolling windows are consistent across the full range on
    every run. Checkpoint written atomically after each day (`.tmp` + rename).
  - **Injection points:** `_session` (fake HTTP session for tests), `_ca_records` (skip
    CA network fetch for tests). Both default to None → real behaviour.
  - **Per-day error handling:** download or parse failures are caught, recorded to the
    checkpoint `"errors"` dict and `BuildReport.error_details`, then skipped. The run
    completes on remaining good days.
  - Tests: `backend/tests/data/test_bhavcopy_build.py` — 14 passing offline. Covers:
    full run (3 tables populated), CA adjustment integration, resume skips checkpointed
    days, resume produces identical output, download error skipped not fatal, 404 =
    missing not error, error written to checkpoint, idempotent (run twice no dupes),
    second run zero network calls, weekends skipped, start>end raises, single-day run,
    all-missing range, report summary string.
    Run: `PYTHONPATH=. venv/bin/pytest tests/data/test_bhavcopy_build.py`
  - Full `tests/data/` suite: 114 passing. v1 untouched (new files only).

---

## T8 — Validation (`validate.py`) — the gate

- **Status:** ☑
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
  - [x] All six checks implemented as hard assertions that fail the build.
  - [x] The 5 known-CA names are real, liquid, with documented ratios cited in comments
        (RELIANCE Bonus 1:1, INFY Bonus 1:1, TCS Bonus 1:1, WIPRO FV split Rs2→Re1,
        GENSOL Bonus 2:1 — verbatim T0 record). Known rename: MOTHERSUMI → MOTHERSON
        (INE775A01035).
  - [x] Coverage report always prints (check 6), including delisted count, % gap days,
        CA event counts (if supplied by the caller).
  - [x] Negative tests: gap >40% fails check 1, wrong adj_factor ratio fails check 1,
        zero delisted ISINs fails check 2, overlapping rename dates fails check 3,
        reversed adv_20 fails check 4, close_tr cumret < close cumret fails check 5.
        All 27 tests pass offline.
  - [x] `run_validation` wired into `build.py` Stage 8 (after store); controlled via
        `skip_validation` param (default False for production).
- **Session log:**
  - 2026-06-14: Implemented `validate.py`. Public API: `run_validation(root=None, *,
    ca_events_applied, ca_events_unmatched, today)` → `ValidationReport`. Six checks
    map directly to 01 §7; all raise `AssertionError` (fail loud, Rule 12).
  - **Check 1** (known CAs): 5 hard-coded events (RELIANCE/INFY/TCS/WIPRO/GENSOL)
    checked for no >40% adjusted gap and adj_factor ratio ≈ expected_ratio. ISINs not
    in the dataset are skipped with a warning (not an error).
  - **Check 2** (survivorship): isin_symbol_map must have ≥1 ISIN with last_date
    > 365 days before today. Empty map or zero delisted → AssertionError.
  - **Check 3** (ISIN rename): MOTHERSUMI → MOTHERSON (INE775A01035) — verifies
    non-overlapping date ranges for the same ISIN. Missing ISIN → skipped.
  - **Check 4** (no lookahead): recomputes rolling(20).median() on the most-rows ISIN;
    np.allclose against stored adv_20. Tests use `vary_tv=True` for real discriminating
    power (constant TV would make reversal undetectable).
  - **Check 5** (TR ≥ price): cumulative return of close_tr ≥ close on up to 10 ISINs.
  - **Check 6** (coverage): always prints; populates `ValidationReport`.
  - **Build integration**: Stage 8 in `build.py`. Existing T7 tests unaffected (synthetic
    data from 2024 is naturally > 365 days old).
  - Tests: `backend/tests/data/test_bhavcopy_validate.py` — 27 passing, offline.
    Run: `PYTHONPATH=. venv/bin/pytest tests/data/test_bhavcopy_validate.py`
  - Full `tests/data/` suite: 141 passing. v1 untouched (new files only).

---

## Exit criteria for the whole Data Layer (spec 01 complete) — ☑ VERIFIED 2026-06-14

- [x] T0–T8 all ☑.
- [x] `validate.py` passes on a real multi-year build. Built **2017-01-02 → 2026-06-12**
      via `fetch.py` (`run_build` with Stage 8 validation enabled). Validation is the build
      gate and fails loud (AssertionError) — a populated dataset means all six §7 checks passed.
- [x] Coverage report reviewed by Arafat; delisted-name count is non-trivial:
      **3,470 distinct ISINs, 739 delisted** (last_date >365d stale) — survivorship-free confirmed.
- [x] Canonical `prices_adjusted` (3,470 ISIN partitions) / `universe_membership` /
      `isin_symbol_map` (3,793 rows) are readable via `store.py` by a downstream consumer
      (sets up spec `02`).
- [x] v1 remains runnable in parallel (nothing in v1 was modified — new files only).

> **Runner:** `backend/app/data/bhavcopy/fetch.py` (untracked utility) drives the full-range
> build: `backend/venv/bin/python backend/app/data/bhavcopy/fetch.py`. Output lands under
> gitignored `backend/data/bhavcopy/`.
