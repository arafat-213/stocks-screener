# v3 / 02 — Track B Data-Layer Task Breakdown & Build Tracker

> **Purpose.** Decompose the **data-layer build** of `02_TRACK_B_DATA.md` into small,
> resumable, cold-session-sized tasks (CLAUDE.md Rule 6 — token budget). Each session loads
> `02_TRACK_B_DATA.md`, this file, and the **one task** it is doing — nothing more.
>
> **Scope = the Track-B fundamentals DATA LAYER only.** No Track-B factor is defined here, no
> backtest is run, and `FINAL_OOS` is **not touched** — this is a data build whose acceptance
> gate (§6 of `02_TRACK_B_DATA.md`) is a *data-quality* gate, not a performance measurement.
> Factor definitions and the H3 test live in `03_TRACK_B_PREREG.md`, written **only after**
> TB7 passes. Do not start a factor or a backtest from this file (that would move the stick).
>
> **How to use each session:**
> 1. Read the task and its "Depends on".
> 2. Do only that task. Honor the per-session token budget.
> 3. Update **Status** and fill the **Session log**.
> 4. Check off Done-criteria. Do not mark Done if anything was skipped (Rule 12).
>
> **Status legend:** ☐ not started · ◐ in progress · ☑ done · ⚠ blocked
>
> **Discipline reminders (non-negotiable):** §8 thresholds are **pre-committed in TB0 before
> any ingest** — never tuned to whatever the ingest yields (the v1 sin applied to data).
> Ingest is **idempotent + checkpointed** (CLAUDE.md §1); per-ISIN failures log to
> `PipelineError` via `classify_error`, never crash the run. **Every schema change has an
> Alembic migration** (CLAUDE.md §2); SQLAlchemy ORM only, no raw SQL. **ISIN is the key**;
> `.NS` suffix wherever a symbol is used; UTC for all stored timestamps. **Tests mock every
> exchange fetch** — never hit live NSE/BSE (CLAUDE.md §5). Build/test under `backend/venv/`.

---

## What this reuses (built + test-gated already — do NOT rewrite, Rule 3)

Before writing code, use the **code-review-graph MCP tools** (CLAUDE.md) to locate the exact
current signatures — do not assume from this list:

- **`PipelineCheckpoint`** — resume-from-last-successful-ISIN for every ingest stage (CLAUDE.md §1).
- **`PipelineError` + `classify_error`** — per-ISIN failure logging; never let one name crash a run.
- **`cleanup_zombie_runs` / concurrency guard** — if any ingest stage is registered as a run.
- **The v2 price layer's survivorship-free universe** (`store.read_prices_adjusted()` and
  whatever assembles its ISIN set) — TB2 cross-checks against it; ISIN must match so the
  price and fundamentals layers join cleanly.
- **Alembic** setup (`alembic/` + `alembic upgrade head`) — the only sanctioned schema path.
- **Frozen splits** `DISCOVERY` (2018-02-06 → 2023-06-30) / `FINAL_OOS` (2023-07-01 →
  2026-06-12) from `validation.py` — import for date-range references only; **consume neither**.

New code lives in a **new `backend/app/fundamentals/` package** (§8.7), kept entirely separate
from `backtest_v2/` so the existing pipeline stays runnable.

---

## Task graph (dependencies)

```
TB0 (lock §8 decisions as committed constants — light, NO ingest code)
   └─> TB1 (storage schema: Alembic migration + ORM models for the PIT tables)
            ├─> TB2 (survivorship-free universe master — populate + cross-check v2)
            │      └─> TB3 (filing-index ingest — the PIT clock)
            │             └─> TB4 (XBRL parser → standardized line items + restatement WRITE-side)
            │                    └─> TB5 (as-of reader — chokepoint API + restatement READ-side)
            │                           └─> TB6 (corporate-action consistency with price layer)
            │                                  └─> TB7 (§6 data acceptance gate — 5 checks → PASS/FAIL)
            └─────────────────────────────────────────────────────────────────────────┘
```

§3.4 **Restatement handling** is split across TB4 (keep all versions keyed by
`available_date` on write) and TB5 (pick the latest version with `available_date ≤ D − lag`
on read) — there is no standalone restatement task; the two halves are cross-referenced.

---

## TB0 — Lock §8 decisions as committed constants (light / no ingest)

- **Status:** ☐ ready — §8 locked in the spec 2026-06-17; remaining work = transcribe into `data_config.py`.
- **Depends on:** Arafat locking §8 — ✓ done (`02_TRACK_B_DATA.md` §8, COMMITTED 2026-06-17).
- **Goal:** Pre-commit every data-layer threshold as a code constant **before any ingest**, so
  no later session can tune the §6 gate to whatever the ingest happens to yield.
- **Locked §8 values (transcribe verbatim — do not reinterpret):**
  - `EXCHANGE_PRIORITY` = NSE-primary, BSE fallback (no cross-exchange reconcile) — §8.1
  - `COVERAGE_THRESHOLD_WEIGHT` = 0.90 **AND** `COVERAGE_THRESHOLD_NAME` = 0.75 (dual gate, both must hold) — §8.2
  - `RECON_SAMPLE_N` = 30, `RECON_TOLERANCE` = 0.02 (±2% per line item) — §8.3
  - `SAFETY_LAG_TRADING_DAYS` = 2 (revised up from 1 on review — quarterly data, look-ahead insurance) — §8.4
  - `RESTATEMENT_POLICY` = as-of-latest-version-known — §8.5
  - scope = historical PIT panel only (no live refresh) — §8.6
  - build vehicle = `backend/app/fundamentals/` + Alembic, `backend/venv/`, mocked fetches — §8.7
- **Do:**
  - Create `app/fundamentals/data_config.py` — a small module of frozen constants holding the
    locked §8 values above, plus the in-window start (~2017-01) for TTM lookback.
  - The §8 spec resolution + DRAFT→COMMITTED flip is **already done** (this session) — TB0 no
    longer touches the spec; constants only. No ingest, no schema, no network.
- **Deliverable:** `data_config.py` with the locked constants.
- **Done-criteria:**
  - [ ] All §8 values recorded as frozen constants in `data_config.py`, matching the spec verbatim.
  - [x] `02_TRACK_B_DATA.md` §8 resolved; doc status = COMMITTED (done 2026-06-17, this session).
  - [ ] No ingest/schema code added (TB0 is the lock, not the build).
- **Session log:** _(fill at end)_

---

## TB1 — Storage schema: Alembic migration + ORM models for the PIT tables

- **Status:** ☐
- **Depends on:** TB0.
- **Goal:** The tables the whole layer writes to, created the only sanctioned way (Alembic),
  with the restatement-versioning key baked into the schema.
- **Do:**
  - SQLAlchemy ORM models (no raw SQL) for: **universe master** (ISIN, names/symbols over time,
    list/delist dates, exchange); **filing index** (ISIN, `period_end`, `available_date`,
    statement type, document pointer); **line-item versions** (ISIN, `period_end`,
    `available_date`, standardized line items — *all* versions kept, never overwritten →
    unique key includes `available_date` so a restatement is a new row, §3.4 write-side).
  - One **Alembic migration** creating them (CLAUDE.md §2); confirm `upgrade head` then
    `downgrade` are both clean. Indexes on `(isin, available_date)` and `(isin, period_end)`.
  - All stored timestamps **UTC** (`datetime.now(datetime.timezone.utc)`).
  - Tests: migration up/down clean; the version key admits two rows for the same
    `(isin, period_end)` differing only by `available_date` (the restatement invariant, Rule 9);
    inserting a duplicate `(isin, period_end, available_date)` is rejected (idempotency guard).
- **Deliverable:** ORM models + Alembic migration + tests, green; `alembic upgrade head` works.
- **Done-criteria:**
  - [ ] PIT tables created via Alembic only; up/down both clean.
  - [ ] Schema permits multiple `available_date` versions per `(isin, period_end)` (restatement);
        rejects exact-duplicate versions (idempotency).
- **Session log:** _(fill at end)_

---

## TB2 — Survivorship-free universe master (populate + cross-check v2)

- **Status:** ☐
- **Depends on:** TB1.
- **Goal:** The ISIN set listed at *any* point in-window, including later delisted/merged names —
  the survivorship-free spine the rest of the layer hangs on (§3.1, problem §1.2).
- **Do:**
  - Build the universe master: every ISIN listed at any point ~2017-01 → 2026-06, with
    list/delist dates and exchange. Source from exchange listing/delisting records (fixtures in
    test; real fetch behind the same mockable seam).
  - **Cross-check against the v2 price universe** (locate it via the graph): every ISIN the price
    layer carries must be representable here; flag any price-layer ISIN missing from the master
    (Rule 12 — surface, don't silently drop).
  - Idempotent + checkpointed populate; per-ISIN failures → `PipelineError` via `classify_error`.
  - Tests (mock all fetches): a known delisting (e.g. DHFL) is present with its real trading
    window; re-running the populate is idempotent (no dup ISINs); a price-ISIN absent from the
    master is flagged, not swallowed.
- **Deliverable:** populated universe master + cross-check report + tests, green.
- **Done-criteria:**
  - [ ] Universe master populated survivorship-free (delisted names present with windows).
  - [ ] Cross-check vs v2 price universe run; discrepancies surfaced (Rule 12).
  - [ ] Populate is idempotent + checkpointed; per-ISIN failures logged.
- **Session log:** _(fill at end)_

---

## TB3 — Filing-index ingest (the PIT clock)

- **Status:** ☐
- **Depends on:** TB1, TB2.
- **Goal:** For each ISIN, the table of filings carrying the **`available_date`** (public filing
  timestamp) — *this table is the look-ahead guard* (§3.2, problem §1.1).
- **Do:**
  - Ingest the filing index per ISIN: `period_end`, `available_date` (the public
    filing/submission timestamp — **never** period-end), statement type, document pointer.
    Exchange priority/dedup per the TB0-locked §8.1 constant.
  - Idempotent + checkpointed (resume from last ISIN); per-ISIN failures → `PipelineError`.
  - **Hard invariant test (Rule 9):** `available_date > period_end` for every row (a filing
    cannot pre-date the period it reports) — any violation fails loud, it is the PIT contract.
  - Tests (mock all fetches): filings land with distinct `available_date`s; the
    `available_date > period_end` invariant holds; re-ingest is idempotent.
- **Deliverable:** populated filing index + invariant tests, green.
- **Done-criteria:**
  - [ ] Filing index populated with `available_date` (filing date, not period-end) per ISIN.
  - [ ] `available_date > period_end` invariant enforced + tested (hard fail on violation).
  - [ ] Ingest idempotent + checkpointed; per-ISIN failures logged.
- **Session log:** _(fill at end)_

---

## TB4 — XBRL parser → standardized line items (+ restatement write-side, §3.4)

- **Status:** ☐
- **Depends on:** TB1, TB3.
- **Goal:** Map heterogeneous Ind-AS XBRL tags to the fixed line-item schema, writing **every**
  version as its own row (§3.3 + §3.4 write-side).
- **Do:**
  - Parse each indexed filing's XBRL into the fixed schema: `revenue`, `net_income`, `ebit`,
    `total_equity`, `total_assets`, `total_debt`, `shares_outstanding`, `cfo`. Map Ind-AS tag
    variants to these targets.
  - **Unmapped / odd taxonomies are logged, never silently zero-filled** (Rule 12) — a missing
    line item is NULL + a `PipelineError`, not a 0.
  - Restatement write-side: a re-filed period writes a **new** line-item row keyed by its
    `available_date` (never an overwrite) — relies on the TB1 version key.
  - Idempotent + checkpointed; per-filing failures → `PipelineError` via `classify_error`.
  - Tests (fixture XBRL, no network): each target line item parses from a representative tag set;
    an unmapped tag → logged + NULL, not zero; a restated period produces a second row with a
    later `available_date` (the original row is untouched).
- **Deliverable:** parser + standardized rows + tests, green.
- **Done-criteria:**
  - [ ] All 8 line items parsed from fixture XBRL into the fixed schema.
  - [ ] Unmapped tags logged + left NULL (never zero-filled) (Rule 12).
  - [ ] Restatement writes a new versioned row; original preserved (§3.4 write-side).
- **Session log:** _(fill at end)_

---

## TB5 — As-of reader (the chokepoint API + restatement read-side, §3.4)

- **Status:** ☐
- **Depends on:** TB4.
- **Goal:** `read_fundamentals_asof(isin, D) → line items` — the single API every Track-B factor
  will call. No factor reads the raw tables directly (§3.5 + §3.4 read-side).
- **Do:**
  - Implement `read_fundamentals_asof(isin, D)`: return the latest line-item version with
    `available_date ≤ D − lag`, where `lag = SAFETY_LAG_TRADING_DAYS` (the TB0-locked §8.4
    constant = 2 trading days). Returns NULL/empty when nothing is yet available — never a
    future-filed figure.
  - This is the **only** sanctioned read path for fundamentals (enforce by package boundary +
    docstring; factors in `03` import this, not the ORM).
  - Tests (synthetic rows, no network, Rule 9): at a `D` between two filings the **earlier**
    version is returned; a figure filed on `D` itself is **excluded** until `D + lag` (the
    look-ahead guard); with two versions of one period, the latest `available_date ≤ D − lag`
    wins (restatement read-side); a `D` before the first filing returns empty, not a guess.
- **Deliverable:** `read_fundamentals_asof` + tests, green.
- **Done-criteria:**
  - [ ] As-of reader honors `available_date ≤ D − lag`; never returns a future-filed figure.
  - [ ] Restatement read-side picks the latest qualifying version (test).
  - [ ] Is the sole fundamentals read path (raw tables not read by factors) (test/boundary).
- **Session log:** _(fill at end)_

---

## TB6 — Corporate-action consistency with the price layer

- **Status:** ☐
- **Depends on:** TB5.
- **Goal:** Make per-share / shares-outstanding figures consistent with the v2 price layer's
  adjustment basis, so earnings-yield and B/P are internally coherent (§3.6).
- **Do:**
  - Reconcile `shares_outstanding` and any per-share figures against the v2 price layer's
    split/bonus adjustment basis (locate it via the graph). A fundamentals figure dated `D` must
    combine with a price dated `D` on the **same** adjustment footing — surface any basis mismatch.
  - Document the chosen convention (e.g. raw shares × adjusted price, or both adjusted) so `03`'s
    factor math is unambiguous.
  - Tests (synthetic split fixture): around a known split date, `market_cap` and `book_to_price`
    computed from this layer + the price layer are continuous (no artificial 2× jump from a
    basis mismatch) (Rule 9).
- **Deliverable:** consistency layer + convention note + tests, green.
- **Done-criteria:**
  - [ ] Shares/per-share figures reconciled to the price layer's adjustment basis; mismatches surfaced.
  - [ ] Convention documented for `03`; continuity-across-split test green.
- **Session log:** _(fill at end)_

---

## TB7 — Data acceptance gate (§6 five checks → PASS / FAIL)

- **Status:** ☐
- **Depends on:** TB1–TB6.
- **Goal:** Subject the assembled panel to all five §6 checks, against the **TB0-locked
  thresholds** — the gate that decides whether `03_TRACK_B_PREREG.md` may be written at all.
- **Do:** Run, each with an explicit pass/fail (Rule 12); all on the **historical panel**, no
  factor returns, no Calmar, `FINAL_OOS` untouched. Thresholds come from `data_config.py`
  (TB0) — **do not** introduce a threshold here that TB0 did not fix.
  1. **Coverage (dual)** — ≥ `COVERAGE_THRESHOLD_WEIGHT` (0.90) of DISCOVERY by market-cap
     weight **AND** ≥ `COVERAGE_THRESHOLD_NAME` (0.75) by name has ≥ 1 usable TTM set at each
     monthly rebalance date. Both must hold; the by-name floor is the breadth guard.
  2. **PIT integrity** — automated replay: every figure the as-of reader returns at a sample of
     historical `D`s satisfies `available_date ≤ D − lag`. **Zero** violations — hard fail on any.
  3. **Survivorship presence** — a pre-listed, independently-assembled set of known in-window
     delistings is present for the dates they traded. Hard fail if any is silently absent.
  4. **Look-ahead replay** — reconstruct "as known on" a historical date; confirm no later-filed
     or restated figure leaks in (TB4 + TB5 end-to-end).
  5. **Reconciliation** — a random `RECON_SAMPLE_N` ISIN-quarters reconcile computed line items
     against the actual filed statements within `RECON_TOLERANCE` (logged spot-audit).
- **Deliverable:** a per-check PASS/FAIL table (mirroring T6's table) + an overall verdict line.
- **Done-criteria:**
  - [ ] All five §6 checks run; each an explicit pass/fail against the TB0-locked thresholds.
  - [ ] No new/loosened threshold introduced here (Rule 12 — surface, don't move the stick).
  - [ ] Overall verdict stated plainly: PASS → `03_TRACK_B_PREREG.md` may be written;
        any FAIL → Track B stops as a research note, `FINAL_OOS` stays pristine (spec §7).
- **Session log:** _(fill at end)_

---

## Exit criteria for the Track-B data layer

- [ ] TB0 locked (§8 thresholds frozen as constants; spec committed, no longer DRAFT).
- [ ] TB1–TB6 built one layer at a time, each test-gated, ingest idempotent + checkpointed,
      every schema change via Alembic, all exchange fetches mocked in tests.
- [ ] TB7 §6 gate run; honest per-check pass/fail against the pre-committed thresholds.
- [ ] If TB7 PASSES → write `03_TRACK_B_PREREG.md` (value/quality factors + H3 test + coarse
      grids) **before any backtest** — a separate prereg, separately approved.
- [ ] If TB7 FAILS → Track B closes as a research note (spec §7 / prereg §10); `FINAL_OOS`
      left pristine. Manufacturing coverage by loosening §6 after the fact is forbidden.

> This file builds **only** the data layer. The one-shot `FINAL_OOS` run belongs to a future
> Track-B execution task created from `03_TRACK_B_PREREG.md` — never from here.
