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
   └─> TB0.5 (feasibility probe — fail-fast: is §6.1 by-name coverage even reachable?)
          └─> TB1 (storage schema: Alembic migration + ORM models for the PIT tables)
            ├─> TB2 (survivorship-free universe master — populate + cross-check v2)
            │      └─> TB3 (filing-index ingest — the PIT clock)
            │             └─> TB4 (XBRL parser → standardized line items + restatement WRITE-side)
            │                    └─> TB5 (as-of reader — chokepoint API + restatement READ-side)
            │                           └─> TB6 (corporate-action consistency with price layer)
            │                                  └─> TB7 (§6 data acceptance gate — 5 checks → PASS/FAIL)
            │                                         └─> TB8 (production ingest + gate RUN → actual verdict)
            └─────────────────────────────────────────────────────────────────────────┘
```

> TB0–TB7 are **test-gated machinery** (all fetches mocked, CLAUDE.md §5). **TB8 is the only task
> that touches live NSE data** and is the only one that produces an actual §6 verdict — the gate
> branches (write `03` / close as research note) hang off TB8, not TB7.

§3.4 **Restatement handling** is split across TB4 (keep all versions keyed by
`available_date` on write) and TB5 (pick the latest version with `available_date ≤ D − lag`
on read) — there is no standalone restatement task; the two halves are cross-referenced.

---

## TB0 — Lock §8 decisions as committed constants (light / no ingest)

- **Status:** ☑ done 2026-06-17 — `data_config.py` created with all 9 locked §8 constants.
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
  - [x] All §8 values recorded as frozen constants in `data_config.py`, matching the spec verbatim.
  - [x] `02_TRACK_B_DATA.md` §8 resolved; doc status = COMMITTED (done 2026-06-17, this session).
  - [x] No ingest/schema code added (TB0 is the lock, not the build).
- **Session log:** 2026-06-17 — Created `backend/app/fundamentals/` package (`__init__.py`
  + `data_config.py`). Transcribed all 9 locked §8 values verbatim as frozen module
  constants: `EXCHANGE_PRIORITY=("NSE","BSE")` (§8.1), `COVERAGE_THRESHOLD_WEIGHT=0.90` &
  `COVERAGE_THRESHOLD_NAME=0.75` (§8.2), `RECON_SAMPLE_N=30` & `RECON_TOLERANCE=0.02`
  (§8.3), `SAFETY_LAG_TRADING_DAYS=2` (§8.4), `RESTATEMENT_POLICY="as-of-latest-version-known"`
  (§8.5), `SCOPE="historical-panel-only"` (§8.6), plus `PANEL_START=2017-01-01` (TTM-lookback
  boundary, not a §8 threshold). Verified clean import + value match under `backend/venv/`.
  No pytest file: a constants module test would just restate the spec (Rule 9 tautology); the
  import/assert check is the verification. No ingest/schema/network — TB0 is the lock only.
  TB0.5 (feasibility probe) is now unblocked.

---

## TB0.5 — Feasibility probe (fail-fast, before the heavy build)

- **Status:** ☑ done 2026-06-17 — probe chain complete (initial → broader → tightening →
  STEP-1 hole-fill). **Verdict = GO.** Decision resolved + pre-registered: **`DISCOVERY_START`
  rescoped ≈2020, NSE-only (BSE not built)** — see `00_PREREGISTRATION.md` → "Track-B
  `DISCOVERY_START` rescope (2026-06-17)". Exact start month pinned at TB7 (full panel, not
  probe samples). **TB1 is unblocked.** See Session logs below for the measurement trail.
- **Depends on:** TB0.
- **Goal:** Answer in **days, not weeks** whether the locked §6.1 by-name coverage floor (75%)
  is even reachable for self-ingested XBRL — so a "data too dirty" outcome stops the program
  *before* TB1–TB6 are built (the reviewer's "don't waste two months" risk).
- **Do:**
  - Compute the **§6.1 denominator** for a small handful (e.g. 3–4) of DISCOVERY rebalance
    dates: the ISINs passing the v2 entry-gate `adv_20` liquidity floor on those dates
    (liquidity-eligible universe — *not* raw `universe_membership`). Reuse the existing v2 gate
    inputs; locate via the graph, do not reimplement the floor.
  - For that name set, **estimate STANDARD-TAG-parseable coverage — not file existence.**
    "Usable" for the probe = the **minimal core line items** the Track-B factors actually need
    (at least `net_income` and `total_equity`; `revenue`/`total_assets` if cheap) **resolve to
    standard Ind-AS taxonomy tags** in the filing. **A filing whose core items sit in
    custom/extension taxonomy namespaces counts as a MISS** (the "file exists but is
    unparseable by a standard schema" case — the dominant Indian failure mode, esp. below the
    top 500). Checking only "does an XBRL file exist?" overestimates and is **forbidden** here.
  - Keep it **conservative by construction** so the estimate is a *lower bound*: custom-tag →
    miss, ambiguous mapping → miss, missing file → miss. A "go" from a conservative probe is
    trustworthy; a "no-go" is honest. This is a *thin* standard-tag extraction on a sample —
    **not** TB4's full mapping table, restatement logic, or all 8 fields. Mock/fixture network
    in tests; a real one-off measurement run is fine but logged and bounded.
  - Report by-name coverage % vs the 75% floor **with the three-way breakdown** per sampled
    date: (a) no filing, (b) filing present but core items in custom/extension tags
    (unmappable), (c) core items resolve to standard tags. The (b) bucket is the signal that
    most directly informs buy-vs-build — a large (b) means self-ingest parsing will be painful
    even where filings exist.
- **Deliverable:** a short coverage-feasibility estimate (by-name %, sample dates, name counts)
  in the session log — a **report, not a gate edit**.
- **Done-criteria:**
  - [x] Liquidity-eligible denominator computed for the sampled dates (reusing the v2 floor).
  - [x] **Standard-tag-parseable** (not file-exists) by-name coverage reported against the 75%
        floor, conservative (custom/extension tags = miss), with the (a)/(b)/(c) breakdown.
  - [x] Explicit go / no-go recommendation stated (Rule 12): **qualified NO-GO** on the heavy
        build as narrowly probed → widen the source (§8.1-sanctioned) and re-probe **before**
        TB1. The probe did not lower any §6 threshold.
- **Session log:** 2026-06-17 — Probe built in `app/fundamentals/tb0_5_probe.py` (Part A offline,
  Part B `--live`). **Part A — §6.1 denominator** (liquidity-eligible = v2 entry-gate `adv_20`
  ≥ ₹5 cr, NOT raw membership), 4 DISCOVERY rebalance dates over a 2,452-ISIN price panel:
  2018-02-28 → 417 names; 2019-11-29 → 304; 2021-09-30 → 637; 2023-06-30 → 747. So the 75%
  floor needs standard-tag fundamentals for ~225–560 names/date.
  **Part B — standard-tag parseability** (LIVE NSE annual financial-results XBRL; std namespace
  `in-bse-fin`; usable = both `net_income`=`ProfitLossForPeriod` AND `total_equity`=`Equity`/
  `EquityAttributableToOwnersOfParent` OR the standard component pair `PaidUpValueOfEquity
  ShareCapital`+`ReserveExcludingRevaluationReserves`; conservative lower bound; seed=20260617,
  20 names/date):

  | rebalance | (a) no XBRL | (b) non-std/custom | (c) usable | by-name % | vs 75% |
  |-----------|-------------|--------------------|------------|-----------|--------|
  | 2018-02-28 | 17 | 2 | 1 | 5%  | FAIL |
  | 2019-11-29 |  7 | 0 | 13 | 65% | FAIL |
  | 2021-09-30 |  2 | 4 | 14 | 70% | FAIL |
  | 2023-06-30 |  2 | 1 | 17 | 85% | PASS |

  **Finding 1 — the blocker is AVAILABILITY (bucket a), not PARSEABILITY (bucket b).** The
  reviewer's feared dominant Indian failure mode (core items in custom/extension taxonomy
  namespaces) is *small* here: (b) = 0–4/20. When a structured XBRL exists it maps to standard
  Ind-AS tags cleanly; the residual (b) misses are almost all **banks/NBFCs** (SOUTHBANK,
  DCBBANK, BANKINDIA → bank P&L under a non-standard element; CHOLAFIN → NBFC equity) — a known,
  bounded gap. **Finding 2 — coverage is strongly TIME-DEPENDENT:** ~5% (2018) → 65% (2019) →
  70% (2021) → 85% (2023). FY2017-era filings are `format="Old"` with the `xbrl` field = `"-"`
  (URL 404s) — **structured NSE results XBRL did not exist yet for early DISCOVERY.** **Caveat —
  these are a conservative LOWER BOUND:** the probe used `period=Annual` only, so names whose
  full-year balance sheet arrives via their Q4 quarterly/half-yearly filing show up as (a)
  "no-annual-filings" (e.g. TATAMOTORS, SPICEJET) though their data likely exists under another
  filing type. True coverage is somewhat higher than the table.
  **Recommendation (Rule 12): QUALIFIED NO-GO on building TB1–TB6 against NSE annual-results
  XBRL alone** — it cannot clear the 75% by-name floor across the *full* pre-registered DISCOVERY
  window (2018 ≈ 5% is a hard floor breach). **Do NOT lower §6 (HARKing).** Because the failure
  is availability not parseability, two §8.1-sanctioned "more INPUT, same threshold" levers
  should be re-probed cheaply *before* the heavy build: (1) broaden the filing source beyond
  `period=Annual` to include Q4 quarterly + half-yearly XBRL (recovers the TATAMOTORS-type (a)
  misses); (2) add BSE XBRL fallback for NSE-missing names. If 2019+ then clears 75%, proceed to
  TB1 with the panel start set where structured XBRL becomes dense. **The 2018 hole may be
  structural** (no exchange published results XBRL for FY2017) — if the re-probe confirms it, the
  only honest fixes are a later `PANEL_START` / a shorter DISCOVERY (a **pre-registration**
  change for Arafat to decide, §10) or a non-XBRL structured source for the early years — never a
  threshold edit. `FINAL_OOS` untouched; no schema, no ingest tables, no factor.

- **Session log — BROADER RE-PROBE (2026-06-17):** Ran the first §8.1 lever. `tb0_5_probe.py`
  extended to **pool the Annual + Half-Yearly + Quarterly NSE feeds** (`_PERIODS`), modelling the
  real as-of reader: a line item counts as available if it resolves to a standard tag in *any*
  filing ≤ as_of. Same seed/sample/classifier → apples-to-apples. **Implementation note (a real
  bug, fixed):** Indian **Quarterly** results XBRL is **P&L-only** — `total_equity` (the balance
  sheet) appears only in **Annual / Half-Yearly** filings. A first newest-first download walk
  spent the per-name budget on quarterly P&L docs and never reached the BS, manufacturing a mass
  of false `missing-standard:total_equity` (it dropped 2019→15%, 2021→25%). Fixed by ordering
  candidates **by filing-type (Annual→Half-Yearly→Quarterly), newest within each** so a
  BS-bearing filing is checked first (yields both items in one download). Corrected result:

  | rebalance | (a) none | (b) non-std | (c) usable | by-name % | vs 75% | Δ vs annual-only |
  |-----------|----------|-------------|------------|-----------|--------|------------------|
  | 2018-02-28 | 17 | 2 | 1  | 5%  | FAIL | unchanged |
  | 2019-11-29 |  4 | 3 | 13 | 65% | FAIL | (a)→(b); coverage flat |
  | 2021-09-30 |  1 | 5 | 14 | 70% | FAIL | (a)→(b); coverage flat |
  | 2023-06-30 |  1 | 2 | 17 | 85% | PASS | unchanged |

  **Finding — source-broadening recovered AVAILABILITY but did NOT lift coverage.** Bucket (a)
  fell at every date (TATAMOTORS-type misses recovered), but the recovered names landed in (b),
  not (c): they are **recent IPOs with a quarterly P&L on file but no annual balance sheet yet**
  (SWSOLAR, AFFLE, HUDCO @2019) — so `total_equity` is *genuinely* unavailable at that date, a
  real miss, not an artifact. **2019 stays 65%, 2021 stays 70% — both still FAIL.** The residual
  (c)-blockers changed character and are now identifiable: (i) **2018 = structural** (17/20 have
  no XBRL document — unfixable within NSE); (ii) **banks/NBFCs** consistently in (b) across
  2021/2023 (SOUTHBANK, DCBBANK, CHOLAFIN, BANKINDIA, KARURVYSYA — sector-specific P&L/equity
  elements not mapped to the non-financial standard tags — a **TB4 parser-scope** item, bounded);
  (iii) a few **probe-side symbol-resolution misses** ("no-filings" for TATAMOTORS/SPICEJET/NIACL/
  L&TFH — the bhavcopy symbol on that date didn't resolve at NSE's results API; a real TB3
  ISIN→symbol PIT map would recover these). (i) is structural; (ii)+(iii) are build-addressable,
  so the *measured* 65/70% for 2019+ is still a conservative lower bound on what TB3+TB4 could
  reach. **Refined recommendation (Rule 12): the early-window NO-GO HARDENS.** Broadening the NSE
  source — the cheapest lever — did not clear 75% for 2019/2021, and **2018 is a structural XBRL
  desert that no NSE source-broadening can fix.** The honest forward path is therefore a
  **pre-registration decision for Arafat (§10), not a threshold edit:** move `PANEL_START` /
  `DISCOVERY_START` forward to where structured XBRL is dense (≥2022 by this probe) — but that
  shortens DISCOVERY materially (~2018–2023 → ~1.5 yr), a research-design tradeoff, not a
  data-quality fix. The two remaining cheap levers (BSE fallback for the symbol-miss/no-filings
  names; bank/NBFC tag mapping folded into TB4 scope) target (ii)+(iii) but **cannot rescue
  2018**, so they don't change the rescope decision — they only matter *after* a forward
  `DISCOVERY_START` is chosen. **BSE fallback not yet run** (deferred: it cannot move the binding
  2018 constraint, so it is not on the critical path to the rescope call). `FINAL_OOS` untouched;
  still no schema, no ingest tables, no factor — data-feasibility measurement only.

- **Session log — TIGHTENING re-probe (2026-06-17, Arafat: "tighten 2019+ first"):** Measured the
  *buildable ceiling* by closing the two non-structural miss-modes the broader re-probe exposed.
  **Diagnostics (live, targeted):** (iii) the "no-filings" names (TATAMOTORS/SPICEJET/NIACL)
  return a **genuinely empty** list from NSE's `corporates-financial-results` API across all
  periods — **not** symbol typos (other names resolve on the same session); so (iii) is **not** a
  cheap TB3 symbol-map fix — these names need a **different source (BSE / NSE archive)**, folding
  into the BSE lever. (ii) the bank/NBFC `missing-standard:net_income` misses are **not**
  custom-namespace: banks file under the **standard `in-bse-fin`** namespace but use the PAT
  element **`ProfitLossForThePeriod`** / `ProfitLossFromOrdinaryActivitiesAfterTax`, which the
  recognizer's `_NET_INCOME_TAGS` (`ProfitLossForPeriod` only) didn't match — a **false** miss.
  Completing `_NET_INCOME_TAGS` with these *verified-standard* variants tightens the lower bound
  toward true coverage **without touching the 75% floor** (not HARKing — correctly counting
  filings that genuinely carry the item under a standard tag). **Tightened result (same
  seed/sample):**

  | rebalance | (a) none | (b) non-std | (c) usable | by-name % | vs 75% | Δ vs broadened |
  |-----------|----------|-------------|------------|-----------|--------|----------------|
  | 2018-02-28 | 17 | 2 | 1  | 5%  | FAIL | unchanged (structural) |
  | 2019-11-29 |  4 | 3 | 13 | 65% | FAIL | unchanged |
  | 2021-09-30 |  1 | 2 | 17 | **85%** | **PASS** | +15pp (3 names flipped to c) |
  | 2023-06-30 |  1 | 0 | 19 | **95%** | **PASS** | +10pp (2 banks flipped to c) |

  **Finding — 2021 & 2023 clear 75% decisively; the "bank gap" was a probe artifact.** Binding
  constraints isolate to two windows: (1) **2018 = structural XBRL desert** (17/20 no document —
  unfixable in any source); (2) **2019 = 65%, fully non-structural** — residual = 4 NSE-API-empty
  names (BSE-fallback recoverable), 2 genuine Aug-2019 IPOs with no annual BS yet (SWSOLAR/AFFLE —
  truly unavailable), 1 equity-tag variant (HUDCO, resolves to (c) by 2023). 2019's buildable
  ceiling is plausibly ~80–90% **once BSE fallback is added** — the one untested lever — but is
  **not yet measured ≥75%**. **Refined verdict (Rule 12): CONDITIONAL GO.** Self-ingested NSE XBRL
  (with the standard PAT recognizer) clears §6.1 from ~2020/2021 onward; 2018 cannot be rescued.
  Forward = the §10 **`DISCOVERY_START` rescope** (Arafat's): (A) start ~2021 — already PASS, no
  more data work, shorter clean window; or (B) start ~2019 + run the **BSE-fallback lever** to
  confirm 2019 ≥75% before committing. Either way **no §6 threshold moves.** `FINAL_OOS` untouched;
  no schema, no ingest tables, no factor.

- **Session log — STEP-1 NSE-only hole-fill re-probe (2026-06-17, Arafat: "re-probe 2019 (BSE)
  first" → "Step-1 first, then reassess"):** Before building any BSE fetcher, filled the
  previously-unmeasured 2020 / 2021-H1 band with the **existing NSE-only** classifier (added a
  `--dates` CLI snap-to-nearest-rebalance override; default 4-date sample unchanged, Rule 3).
  Same seed=20260617, 20 names/date. **Sampling note:** the RNG advances once per date, so each
  date's 20-name draw depends on date order — 2019-11 here (55%) is a *different* subsample than
  the tightening run's 2019-11 (65%); both are noisy 20-name point estimates of the same date.

  | rebalance | (a) none | (b) non-std | (c) usable | by-name % | vs 75% |
  |-----------|----------|-------------|------------|-----------|--------|
  | 2019-11-29 | 7 | 2 | 11 | 55% | FAIL |
  | 2020-06-30 | 0 | 0 | 20 | 100% | PASS |
  | 2020-12-31 | 4 | 0 | 16 | 80% | PASS |
  | 2021-03-31 | 1 | 1 | 18 | 90% | PASS |

  **Finding — NSE-only crosses the 75% floor between Nov-2019 and Jun-2020, not "~2021".** The
  prior A-vs-B framing assumed NSE-only cleared 75% only around 2021, making BSE the *only* route
  to a pre-2021 start — **that assumption is now falsified.** 2019 fails hard (55–65%); 2020-06,
  2020-12, 2021-03 all PASS (80–100%; noisy 20-name samples but all clear). A **`DISCOVERY_START`
  ≈ 2020 is feasible on NSE alone**: clears the 75% by-name floor, yields **2–3 expanding
  walk-forward folds** (`validation.walk_forward_windows`, `min_is_months=24`+`oos_months=6` ⇒
  30-month floor — the ~2021 window gives 0–1), and **retains the Mar-2020 COVID-crash regime**,
  the largest regime event in DISCOVERY and exactly the contrast H3 is built to test. **BSE is
  therefore OFF the critical path:** it could only attempt to rescue 2019 ((a)-bucket misses =
  IBULHSGFIN/IBREALEST/INFRATEL/SBILIFE/LTI/SPICEJET/BANKBARODA + recent-IPO (b) AFFLE/INDIAMART),
  buying at most the one extra 2018-19 NBFC-crisis year for the full scrip-map+fetcher build, and
  **cannot** rescue 2018 (structural). **Recommendation (Rule 12): do NOT build BSE; rescope
  `DISCOVERY_START` ≈ 2020** — exact durable-≥75% month to be pinned by TB7 over the *full*
  liquidity-eligible panel (not 20-name samples), never by moving §6. Final §10 pre-registration
  choice is Arafat's. No §6 threshold moved; `FINAL_OOS` untouched; no schema, no ingest tables,
  no factor — data-feasibility measurement only.

---

## TB1 — Storage schema: Alembic migration + ORM models for the PIT tables

- **Status:** ☑ done 2026-06-17 — ORM models + Alembic migration `c4e1f7a9b2d3`
  (single head), 5 invariant tests green. See Session log.
- **Depends on:** TB0, TB0.5 (probe go).
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
  - [x] PIT tables created via Alembic only; up/down both clean (verified — see Session log caveat
        on Postgres vs SQLite).
  - [x] Schema permits multiple `available_date` versions per `(isin, period_end)` (restatement);
        rejects exact-duplicate versions (idempotency).
- **Session log:** 2026-06-17 — **Models** in new `app/fundamentals/models.py` (registered on the
  shared `app.db.models.Base` — one metadata / one Alembic chain; package boundary is by code
  location, not a separate DB). **Four tables** (`fundamentals_` prefix):
  `fundamentals_universe` (survivorship-free spine, ISIN PK, list/delist dates, exchange);
  `fundamentals_symbol_history` (ISIN→symbol PIT history, `.NS`, valid_from/valid_to — the
  symbols-over-time half the probe flagged TB3 needs); `fundamentals_filing_index` (the PIT clock:
  `period_end`, `available_date` (filing date, never period-end), statement_type, source_exchange,
  document_url); `fundamentals_line_items` (the 8 standardized items — revenue/net_income/ebit/
  total_equity/total_assets/total_debt/shares_outstanding/cfo, all NULLable, never zero-filled).
  **Restatement key** = `UniqueConstraint(isin, period_end, available_date)` on line items: admits
  two rows for one `(isin, period_end)` differing only by `available_date`, rejects an exact dup
  (idempotency). Filing index dedups on `(isin, period_end, available_date, statement_type)` so an
  Annual + a Quarterly can share a period/date. **Indexes** `(isin, available_date)` &
  `(isin, period_end)` on both versioned tables. FKs `isin → fundamentals_universe.isin`. All
  timestamps `DateTime(timezone=True)`, UTC python defaults (repo convention). **Migration**
  `c4e1f7a9b2d3` (down_revision = prior head `934e63731fa2`; `alembic heads` = single head).
  `migrations/env.py` now imports the models so autogenerate sees them and never proposes dropping
  them. **Tests** `tests/unit/test_fundamentals_models.py` (5, green): restatement keeps both
  versions; exact-dup version rejected; unmapped item is NULL not 0; filing-index idempotent on the
  full version key; distinct statement_types coexist. **Verification caveat (Rule 12):** the Docker
  daemon was down so Postgres (5434) was unreachable — `upgrade`/`downgrade` were verified by
  isolating this revision on a throwaway SQLite DB (`alembic stamp 934e63731fa2` → `upgrade head`
  creates all 4 tables + 6 indexes → `downgrade -1` drops them clean). The full chain can't replay
  on SQLite (earlier migrations use Postgres-only `ALTER ... DROP CONSTRAINT`), and the ORM↔DDL
  match is corroborated by the SQLite `create_all` the tests run on. **CAVEAT CLOSED (2026-06-17,
  docker up):** `alembic upgrade head` ran clean against the real Postgres (5434): `934e63731fa2 →
  c4e1f7a9b2d3`, `alembic current` = `c4e1f7a9b2d3 (head)`; all 4 `fundamentals_*` tables, 6 named
  indexes, and 3 unique constraints confirmed present in `pg_tables`/`pg_indexes`. No ingest, no
  network, no factor; `FINAL_OOS` untouched.

---

## TB2 — Survivorship-free universe master (populate + cross-check v2)

- **Status:** ☑ done 2026-06-17 — `app/fundamentals/universe.py` (populate + cross-check),
  5 invariant tests green. See Session log.
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
  - [x] Universe master populated survivorship-free (delisted names present with windows).
  - [x] Cross-check vs v2 price universe run; discrepancies surfaced (Rule 12).
  - [x] Populate is idempotent + checkpointed; per-ISIN failures logged.
- **Session log:** 2026-06-17 — **Module** `app/fundamentals/universe.py`. `populate_universe(
  session, source, run_id, *, resume=True)` idempotently upserts the `fundamentals_universe`
  master from an injectable `ListingSource` (`Callable[[], Iterable[ListingRecord]]`) — ISIN is
  the PK so a re-run never duplicates (upsert via `session.get`, refresh-in-place on hit);
  `resume=True` skips ISINs already checkpointed for the run (crash-recovery), `resume=False`
  forces a full re-process. **Checkpoint/error plumbing reuses the existing primitives** (Rule 3):
  `PipelineCheckpoint` (one row per `run_id`+`phase="tb2_universe"`, completed ISINs as the JSON
  `completed_symbols` array), `PipelineError` + `classify_error` for per-ISIN failures — counters
  increment **only after a durable commit** (a failed row is rolled back, logged, and skipped, never
  double-counted or fatal). Empty-ISIN records are rejected as a per-ISIN failure (can't key the
  master). **Survivorship-free** = `delist_date` retained for delisted names, `NULL` = still-listed
  open window. **Cross-check** `cross_check_against_price_universe(session, price_isins)` →
  `CrossCheckReport` flags every price-layer ISIN absent from the master (`missing_from_master`,
  `.ok`) — surfaced, never dropped (Rule 12); `read_price_universe_isins()` is the thin IO seam over
  the v2 price layer (`store.read_isin_symbol_map` — one row per ISIN), kept separate so the
  cross-check is testable without Parquet/disk. **Tests** `tests/unit/test_fundamentals_universe.py`
  (5, green): DHFL delisting retained with its closed window; re-run idempotent (no dup ISIN,
  refresh-in-place); a price-ISIN absent from the master is flagged + the clean case is `.ok`; a
  per-ISIN failure is logged to `PipelineError` (`error_type="unknown"`) and the run continues with
  the good rows landing; a checkpointed ISIN is skipped on resume. **Scope call (Rule 1/7,
  surfaced):** TB2 builds the populate *machinery* + cross-check, test-gated against fixture sources
  (CLAUDE.md §5 — no live NSE in tests). **No concrete exchange listings/delistings fetcher exists in
  the repo yet** and the source isn't pinned (TB0.5 = NSE-only ≈2020); the production seam
  `fetch_exchange_listings()` therefore **fails loud** (`NotImplementedError`) rather than fabricating
  a universe — wiring the real NSE source is a follow-on ingest-source task, and a real populate run
  against live data has **not** been executed. No schema change (TB1's tables), no network, no
  factor; `FINAL_OOS` untouched.

---

## TB3 — Filing-index ingest (the PIT clock)

- **Status:** ☑ done 2026-06-18 — `app/fundamentals/filing_index.py` (populate +
  concrete NSE fetcher), 5 invariant tests green. See Session log.
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
  - [x] Filing index populated with `available_date` (filing date, not period-end) per ISIN.
  - [x] `available_date > period_end` invariant enforced + tested (hard fail on violation).
  - [x] Ingest idempotent + checkpointed; per-ISIN failures logged.
- **Session log:** 2026-06-18 — **Module** `app/fundamentals/filing_index.py`.
  **Scope calls resolved before coding (Rule 1):** (1) One-shot NSE API diagnostic on RELIANCE
  confirmed the public dissemination field is `broadCastDate` ("22-Apr-2024 19:47:12") — not
  `submissionDate` or `toDate`; `filingDate` is a minutes-precision fallback. (2) Concrete NSE
  fetcher built (1A+2A — Arafat's choice) so TB3 ships with a production-ready ingest path
  rather than a stub. (3) Consolidated/Non-Consolidated dedup: both share the same calendar
  `available_date`, which would violate the unique key if both inserted — resolved by preferring
  Consolidated within each `(period_end, statement_type)` group (no schema change).
  **`available_date`** = `broadCastDate` date portion from NSE API (public dissemination
  timestamp, never period_end). **`FilingSource`** = `Callable[[str, str], Iterable[FilingRecord]]`
  (isin, symbol) — injectable seam; tests mock, production passes `fetch_nse_filing_index`.
  **`fetch_nse_filing_index(isin, symbol)`** — pools Annual + Half-Yearly + Quarterly NSE
  feeds (§8.1 source-broadening; same endpoint as TB0.5 probe), deduplicates by
  `(period_end, statement_type)` preferring Consolidated, uses `broadCastDate`→`filingDate` as
  `available_date`. **`PITViolationError`** — raised for any `available_date ≤ period_end` row;
  logged to `PipelineError` + row skipped + `pit_violations` counter (never stored, never silent).
  **`populate_filing_index(session, source, symbol_map, run_id, *, resume=True)`** — takes
  injected `symbol_map: dict[str, str]` (isin→symbol, resolved by caller from v2 price layer
  or `FundamentalsSymbolHistory`) so the populate function is source-agnostic and testable.
  Source-level failures fail the ISIN (not checkpointed → retried on resume); per-row DB errors
  log + continue (ISIN still checkpointed). Checkpoint/error plumbing reuses `PipelineCheckpoint`
  + `PipelineError` + `classify_error` (Rule 3). **Tests** `tests/unit/test_fundamentals_filing_index.py`
  (5, green): available_date stored as broadcast date not period_end; PIT violation logged +
  zero rows stored (two violation modes tested: equal + before); idempotent re-run produces one
  row; checkpointed ISIN skipped on resume (tracking source confirms no re-fetch); per-ISIN
  source failure logged + good ISIN still lands. All 15 fundamentals unit tests green (TB1+TB2+TB3,
  no regressions). No schema change; no Alembic migration (TB1's tables unchanged). `FINAL_OOS`
  untouched.

---

## TB4 — XBRL parser → standardized line items (+ restatement write-side, §3.4)

- **Status:** ☑ done 2026-06-18 — `app/fundamentals/xbrl_parser.py` (parser + populate),
  5 invariant tests green, 20/20 total fundamentals tests green. See Session log.
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
  - [x] All 8 line items parsed from fixture XBRL into the fixed schema.
  - [x] Unmapped tags logged + left NULL (never zero-filled) (Rule 12).
  - [x] Restatement writes a new versioned row; original preserved (§3.4 write-side).
- **Session log:** 2026-06-18 — **Module** `app/fundamentals/xbrl_parser.py`. **Parser
  design** (`parse_xbrl(xbrl_text) -> XBRLParseResult`) is pure / no I/O — all 8 items
  resolved from the standard `in-bse-fin` namespace via regex (same approach as TB0.5 probe,
  Rule 3). Three composite derivations: (1) **EBIT** = `ProfitBeforeExceptionalItemsAndTax` +
  `FinanceCosts` (no direct EBIT element in Ind-AS XBRL; both components must be present else
  NULL); (2) **total_equity** = `Equity` direct OR `PaidUpValueOfEquityShareCapital +
  ReserveExcludingRevaluationReserves` component sum (from TB0.5 tightening probe); (3)
  **total_debt** = `Borrowings` direct OR `LongTermBorrowings + ShortTermBorrowings` sum
  (zero-fill per component so LT-only debt is still captured). Tag coverage: `revenue`
  (Revenue/RevenueFromOperations/+3 fallbacks); `net_income` (4 PAT variants including bank
  tags from TB0.5 tightening); `total_assets` (Assets/TotalAssets); `shares_outstanding`
  (NumberOfSharesOutstanding/+2 count-element variants); `cfo` (4 operating-cashflow variants).
  Non-standard namespace → all NULL (conservative — no false positives). **`XBRLFetcher =
  Callable[[str], str]`** — injectable seam; tests mock, production passes
  `fetch_xbrl_document` (requests, local import). **`populate_line_items(session, fetcher,
  run_id, *, resume=True)`** — reads `FundamentalsFilingIndex` rows with `document_url IS NOT
  NULL`, grouped by ISIN (checkpoint granularity = ISIN, consistent with TB2/TB3, Rule 3);
  per-filing: fetch → parse → check for existing row (idempotency) → write
  `FundamentalsLineItemVersion`; unmapped items → NULL + one `PipelineError` per filing listing
  them; fetcher/parse failures → `PipelineError` + continue. Restatement write-side: two
  filings for the same `period_end` with different `available_date`s each write their own row
  (TB1 unique key admits them; rejects exact duplicates). Checkpoint/error plumbing reuses
  `PipelineCheckpoint` + `PipelineError` + `classify_error` (Rule 3). **Tests**
  `tests/unit/test_fundamentals_xbrl_parser.py` (5, green): all 8 items parse from fixture
  XBRL including EBIT derivation (PBT=130k + FC=20k → ebit=150k) and debt component sum
  (LT=200k + ST=50k → total_debt=250k); unmapped items are NULL not 0 + PipelineError logged
  listing fields; restatement writes 2 rows, original net_income=100k untouched alongside
  restated 115k; idempotent re-run produces 1 row + skipped_existing=1; per-filing fetch
  failure logs to PipelineError + other ISIN's row lands. All 20 fundamentals unit tests green
  (TB1+TB2+TB3+TB4, no regressions). No schema change; no Alembic migration (TB1 tables
  unchanged). `FINAL_OOS` untouched.

---

## TB5 — As-of reader (the chokepoint API + restatement read-side, §3.4)

- **Status:** ☑ done 2026-06-18 — `app/fundamentals/reader.py` (as-of reader),
  5 invariant tests green, 25/25 total fundamentals tests green. See Session log.
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
  - [x] As-of reader honors `available_date ≤ D − lag`; never returns a future-filed figure.
  - [x] Restatement read-side picks the latest qualifying version (test).
  - [x] Is the sole fundamentals read path (raw tables not read by factors) (test/boundary).
- **Session log:** 2026-06-18 — **Module** `app/fundamentals/reader.py`.
  **`FundamentalsSnapshot`** — frozen dataclass carrying all 8 standardized line items +
  `(isin, period_end, available_date, statement_type)` metadata; immutable so factors
  cannot accidentally mutate shared state and the session can be closed after the read.
  **`read_fundamentals_asof(session, isin, as_of_date)`** — queries
  `FundamentalsLineItemVersion` for all rows where `isin == isin AND available_date ≤
  cutoff` (cutoff = `numpy.busday_offset(as_of_date, -SAFETY_LAG_TRADING_DAYS)`; Mon–Fri
  business days; the 2-day locked buffer absorbs any Indian-holiday edge case). Groups by
  `period_end`; for each group picks the row with the highest `available_date` (restatement
  read-side §3.4); returns a list of `FundamentalsSnapshot` ordered by `period_end`
  descending (most recent period first, ready for TTM slicing). Returns `[]` when nothing
  qualifies — never a guess. **Sole read-path boundary** enforced by docstring + test:
  `test_result_is_frozen_snapshot_not_orm_row` verifies the return type is the immutable
  dataclass (not a live ORM row) and that all 8 fields are present on the interface.
  **No schema change; no Alembic migration** (TB1 tables unchanged). **Tests**
  `tests/unit/test_fundamentals_reader.py` (5, green): (1) two filings both pre-cutoff →
  both periods returned, newest first; (2) `available_date == D` → excluded; becomes
  visible at `D + 2 bd` (lag guard test with intermediate step); (3) original + restatement
  for same period → original returned when only it qualifies, restatement returned once it
  qualifies; (4) `D` before first filing → empty list; (5) return type is frozen
  `FundamentalsSnapshot`, not ORM row; all 8 fields present; mutation raises. All 25
  fundamentals unit tests green (TB1+TB2+TB3+TB4+TB5, no regressions). `FINAL_OOS`
  untouched; no factor.

---

## TB6 — Corporate-action consistency with the price layer

- **Status:** ☑ done 2026-06-18 — `app/fundamentals/ca_consistency.py` (convention +
  reconciler), 5 invariant tests green, 30/30 total fundamentals tests green. See Session log.
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
  - [x] Shares/per-share figures reconciled to the price layer's adjustment basis; mismatches surfaced.
  - [x] Convention documented for `03`; continuity-across-split test green.
- **Session log:** 2026-06-18 — **Module** `app/fundamentals/ca_consistency.py`.
  **Price-layer investigation (graph + store.py + adjust.py):** The v2 price layer stores three
  price columns per day: `close` (split+bonus back-adjusted signal price = `close_raw × adj_factor`),
  `close_raw` (unadjusted traded close, retained for audit), and `adj_factor` (cumulative
  back-adjustment factor — latest date = 1.0, earlier dates < 1.0 wherever a split/bonus occurred).
  `shares_outstanding` from XBRL is the raw share count reported in the filing.
  **Basis mismatch identified:** A naïve `market_cap = close × shares_outstanding` fails around
  a 2:1 split — the adjusted price halves retroactively across ALL pre-split dates while the XBRL
  shares step upward only at the fiscal period containing the ex-date, creating an artificial ×2
  discontinuity in market cap.
  **CHOSEN CONVENTION — Raw × Raw (locked here for 03 factors):**
  `market_cap(D) = close_raw(D) × shares_outstanding_from_snapshot(D)`. Both quantities are on
  the unadjusted basis for any given date, so the product is continuous across split/bonus events
  (pre-split: 1000 × 100M = 100B; post-split: 500 × 200M = 100B). For book-to-price:
  `b2p = total_equity / (close_raw × shares_outstanding)`. `total_equity` is a monetary total
  (₹), not per-share, so it is already continuous — no additional adjustment needed.
  **What NOT to do (enforced by docstring):** `close × shares_outstanding` or
  `close_tr × shares_outstanding` — both adjusted price, raw shares → discontinuity.
  **`PriceReader = Callable[[isin, start, end], DataFrame]`** — injectable seam; tests mock,
  production passes `read_prices_adjusted` (bhavcopy store). **Public helpers** (the only
  sanctioned paths for 03 factors): `market_cap_raw(close_raw, shares_outstanding)` and
  `book_to_price_raw(total_equity, close_raw, shares_outstanding)` — both enforce the raw × raw
  convention; `book_to_price_raw` returns None when any input is None or market_cap is zero.
  **`reconcile_ca_consistency(session, price_reader, isin_list, start, end)`** — for each ISIN:
  reads adj_factor series from the price layer, detects steps > 5% (split/bonus events via
  `_adj_factor_steps`), then for each step reads XBRL `shares_outstanding` straddling the
  ex_date (via `read_fundamentals_asof` at `ex_date` for before, at `ex_date + 400 days` for
  after), compares observed shares ratio against the expected multiplier (= adj_factor step ratio),
  flags divergence beyond `RECON_TOLERANCE` (2%) to `CaConsistencyReport.mismatches` (Rule 12 —
  never silent). ISINs with no price data, no CA events, or no XBRL snapshots → `skipped_isins`.
  All-OK ISINs → `ok_isins`. **Tests**
  `tests/unit/test_fundamentals_ca_consistency.py` (5, green): (1) `market_cap_raw` continuous
  (1000×100M = 500×200M = 100B, split-invariant); (2) `book_to_price_raw` continuous (10B/100B
  = 0.1 both sides); (3) adjusted price × raw shares gives ×2 discontinuity — proves the basis
  mismatch that makes raw × raw necessary; (4) reconciler marks ISIN ok when shares ratio matches
  adj_factor step (200M/100M = 2.0 = adj_factor 0.5→1.0); (5) reconciler surfaces mismatch when
  XBRL shows only +10% shares (110M) against a 2× adj_factor step. All 30 fundamentals unit tests
  green (TB1+TB2+TB3+TB4+TB5+TB6, no regressions). No schema change; no Alembic migration.
  `FINAL_OOS` untouched; no factor.

---

## TB7 — Data acceptance gate (§6 five checks → PASS / FAIL)

- **Status:** ☑ done 2026-06-18 — `app/fundamentals/gate.py` (5-check gate),
  6 invariant tests green, 36/36 total fundamentals tests green. See Session log.
- **Depends on:** TB1–TB6.
- **Goal:** Subject the assembled panel to all five §6 checks, against the **TB0-locked
  thresholds** — the gate that decides whether `03_TRACK_B_PREREG.md` may be written at all.
- **Do:** Run, each with an explicit pass/fail (Rule 12); all on the **historical panel**, no
  factor returns, no Calmar, `FINAL_OOS` untouched. Thresholds come from `data_config.py`
  (TB0) — **do not** introduce a threshold here that TB0 did not fix.
  1. **Coverage (dual)** — over the **liquidity-eligible DISCOVERY universe** (names passing the
     v2 entry-gate `adv_20` floor on each rebalance date — the §6.1 pinned denominator, *not*
     raw `universe_membership`), ≥ `COVERAGE_THRESHOLD_WEIGHT` (0.90) by market-cap weight
     **AND** ≥ `COVERAGE_THRESHOLD_NAME` (0.75) by name has ≥ 1 usable TTM set at each monthly
     rebalance date. Both must hold; the by-name floor is the breadth guard.
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
  - [x] All five §6 checks run; each an explicit pass/fail against the TB0-locked thresholds.
  - [x] No new/loosened threshold introduced here (Rule 12 — surface, don't move the stick).
  - [x] Overall verdict stated plainly: PASS → `03_TRACK_B_PREREG.md` may be written;
        any FAIL → Track B stops as a research note, `FINAL_OOS` stays pristine (spec §7).
- **Session log:** 2026-06-18 — **Module** `app/fundamentals/gate.py`. **Architecture:**
  thin injectable-seam design — `EligibleOnDate = Callable[[date], list[(isin, weight)]]` for
  the price-layer query (§6.1) and `ReconReader = Callable[[list[(isin, period_end)]], dict]`
  for the reconciliation reference (§6.5); tests inject fixtures, production passes the real
  Parquet reader and an XBRL re-parser. All five check functions are individually callable AND
  composed by `run_acceptance_gate(...)` which returns a `GateResult` (`verdict="PASS"|"FAIL"`,
  `.summary()` for logging). **Five checks (all from TB0-locked §8 constants — no new thresholds):**
  (1) `check_coverage(session, eligible_on_date, rebalance_dates)` — for each rebalance date calls
  `read_fundamentals_asof` per eligible ISIN, computes by-name and by-weight coverage fractions;
  fails if EITHER floor (name≥75% / weight≥90%) is below threshold on ANY date. (2)
  `check_pit_integrity(session, sample_isins, sample_dates)` — two-pass: (a) direct DB scan for
  `available_date ≤ period_end` rows (safety net for any that bypassed TB3's PITViolationError);
  (b) reader replay at each sample date to confirm `available_date ≤ _cutoff(D)` for every
  returned snapshot; zero tolerance. (3) `check_survivorship(session, known_delistings)` — loads
  `fundamentals_universe`, flags any known in-window delisting absent from the master (Rule 12 /
  survivorship guard). (4) `check_lookahead_replay(session, test_cases)` — for each
  `(isin, period_end, D_pre, D_post)`, calls reader at both dates and verifies every returned
  snapshot for that period satisfies `available_date ≤ _cutoff(D)`; validates the TB4+TB5
  end-to-end restatement pipeline (v1 only at D_pre, v2 winning at D_post). (5)
  `check_reconciliation(session, sample_isin_periods, reference_reader)` — fetches latest stored
  row per sampled (isin, period_end), compares 4 core items (revenue/net_income/total_equity/
  total_assets) against `reference_reader` output; flags any relative deviation > RECON_TOLERANCE
  (2%); NULL in either stored or reference = skip (unavailability ≠ mismatch).
  **Tests** `tests/unit/test_fundamentals_gate.py` (6, green): (1) coverage dual gate — weight=95%
  but name=25% → FAIL (proves both floors independently enforced; a cap-heavy/name-thin panel is
  caught); (2) PIT integrity — row with `available_date == period_end` bypassing ingest validator →
  gate DB scan catches it → FAIL; (3) survivorship — known delisted ISIN absent from master → FAIL
  with ISIN in detail (not swallowed); (4) look-ahead replay — v1 (avail=2022-05-10, ni=100) and v2
  (avail=2022-08-01, ni=115) correctly stored; gate PASS + reader cross-check confirms v1 at
  D_pre=2022-07-15 and v2 at D_post=2022-10-03 (dates chosen as valid business days — 2022-10-01
  is Saturday); (5) reconciliation — revenue stored=1100 vs reference=1000 (10% deviation >
  RECON_TOLERANCE=2%) → FAIL with "revenue" and "err=" in detail; (6)
  `test_run_acceptance_gate_fail_aggregation` — `run_acceptance_gate` with §6.1 failing → overall
  `GateResult.verdict == "FAIL"`, confirms aggregation is AND not OR. All 36 fundamentals unit
  tests green (TB1+…+TB7, no regressions). No schema change; no Alembic migration (TB1 tables
  unchanged). `FINAL_OOS` untouched; no factor. **NOTE:** the gate module and tests constitute the
  complete §6 acceptance machinery — a production gate run over the real panel requires the universe
  master, filing index, and line-items tables to be populated (TB2/TB3/TB4 ingest), which depends on
  wiring the concrete `fetch_exchange_listings` source (currently `NotImplementedError` per TB2
  scope call). The gate logic and all threshold constants are complete and test-gated; the ingest
  production run is a follow-on operational step.

---

## TB8 — Production ingest + §6 gate run (the actual PASS/FAIL verdict)

- **Status:** ☐ not started — scoped 2026-06-18 (this session); to be executed in a fresh cold
  session. **This is the only Track-B data task that touches LIVE NSE data.**
- **Depends on:** TB1–TB7 (all ☑). Requires Postgres up (5434) + the v2 price layer already
  ingested on disk (`store.read_prices_adjusted` / `read_universe_membership` /
  `read_isin_symbol_map` return data).
- **Goal:** Populate the real PIT panel (NSE-only, `DISCOVERY_START` ≈2020 per the pre-registered
  rescope), then run `run_acceptance_gate(...)` over it to produce the **first actual §6 PASS/FAIL
  verdict** — the thing that decides whether `03_TRACK_B_PREREG.md` may be written or Track B closes
  as a research note. TB7 built and test-gated the gate *machinery*; TB8 *runs* it on real data.
- **Why this is a separate task (Rule 1/6):** every prior TBx mocked exchange fetches (CLAUDE.md
  §5). TB8 is the operational ingest run — live NSE, hundreds of ISINs × ~6 years, multi-hour,
  bounded. It must stay idempotent + checkpointed so it resumes after any crash without re-fetching.

### What this REUSES — do NOT rebuild (Rule 3; signatures verified on disk 2026-06-18)

| Need | Already exists | File |
|---|---|---|
| Universe populate (idempotent/checkpointed) | `populate_universe(session, source, run_id, *, resume=True)` | `universe.py` |
| Filing-index populate + **live NSE fetcher** | `populate_filing_index(session, source, symbol_map, run_id, *, resume=True)` + `fetch_nse_filing_index(isin, symbol)` | `filing_index.py` |
| XBRL parse/populate + **live XBRL fetcher** | `populate_line_items(session, fetcher, run_id, *, resume=True)` + `fetch_xbrl_document(url)` | `xbrl_parser.py` |
| As-of reader (sole read path) | `read_fundamentals_asof(session, isin, D)` | `reader.py` |
| Gate (5 checks + AND-aggregation) | `run_acceptance_gate(...)` → `GateResult` | `gate.py` |
| Liquidity-eligible denominator (= gate's `EligibleOnDate` minus weight) | `liquidity_eligible_isins(prices_on_day, floor)` | `tb0_5_probe.py` |
| Raw×raw market-cap weight (TB6 convention) | `market_cap_raw(close_raw, shares_outstanding)` | `ca_consistency.py` |
| Price/membership/symbol-map readers | `read_prices_adjusted` · `read_universe_membership` · `read_isin_symbol_map` | `bhavcopy/store.py` |

### The 3 seams TB8 must wire (the only new code)

1. **`fetch_exchange_listings()`** — currently the lone `NotImplementedError` (`universe.py:107`).
   **Recommended source: derive from the v2 `universe_membership`** (already survivorship-free,
   ISIN-keyed, bhavcopy-built): first-seen → `list_date`, last-seen → `delist_date` (NULL if seen
   through window end). This makes the universe stage **fully offline + reproducible** and makes
   TB2's cross-check pass by construction (same ISIN spine). *Alternative:* a live NSE
   listings/delistings scrape — more faithful to "exchange records" but adds live surface and a new
   scraper for marginal gain. **Decision pending (Arafat) — see Open decisions.**
2. **`EligibleOnDate` adapter for the gate** — per rebalance date: `read_prices_adjusted(date)` →
   `liquidity_eligible_isins(..., floor=₹5cr)` → attach weight via
   `ca_consistency.market_cap_raw(close_raw, shares_outstanding)` (TB6 raw×raw convention). Returns
   `list[(isin, weight)]` — the §6.1 pinned denominator (liquidity-eligible, **not** raw membership).
3. **`ReconReader` for §6.5** — re-parse the stored XBRL doc for `RECON_SAMPLE_N`=30 random
   ISIN-quarters via `fetch_xbrl_document` + `parse_xbrl`; returns the reference line items the gate
   diffs against `RECON_TOLERANCE`=±2%.

### Orchestration — new `tb8_ingest.py` (one `PipelineRun`, idempotent + checkpointed)

```
0. cleanup_zombie_runs + concurrency guard on entry (CLAUDE.md §1); --resume from last checkpoint
1. populate_universe(source = membership-derived listings)               [OFFLINE]
2. cross_check_against_price_universe(...)  → must be clean (Rule 12)     [OFFLINE]
3. symbol_map = read_isin_symbol_map() (+ FundamentalsSymbolHistory)     [OFFLINE]
4. populate_filing_index(source = fetch_nse_filing_index, symbol_map)    [LIVE NSE — bounded]
5. populate_line_items(fetcher = fetch_xbrl_document)                    [LIVE NSE XBRL — long pole]
6. run_acceptance_gate(eligible_on_date, recon_reader,
                       rebalance_dates = monthly 2020 → DISCOVERY_END)
7. Emit per-check PASS/FAIL table + overall verdict; pin durable-≥75% DISCOVERY_START month
```
Steps 4–5 are the only live surface — per-ISIN, already failure-isolated to `PipelineError` via
`classify_error`, resumable from the last checkpointed ISIN.

### Discipline guardrails (non-negotiable)

- **HARKing tripwire:** if coverage FAILS at some 2020 rebalances, the *only* sanctioned response is
  the already-pre-registered `DISCOVERY_START` ≈2020 rescope (a §10 decision) — **never** nudge the
  90/75 floors. The gate reads `data_config.py`; TB8 adds **no** threshold.
- **`FINAL_OOS` (2023-07-01 → 2026-06-12) stays pristine** — gate runs on the DISCOVERY panel only.
- **`DISCOVERY_START` is currently NOT a constant** (`data_config.py` has only
  `PANEL_START=2017-01-01`); TB7 deferred pinning the exact month to a real run. **The gate's
  coverage check across monthly rebalances is what pins it** — a genuine TB8 output, not a guess.
- **No `FINAL_OOS`, no factor, no backtest** — TB8 ends at the data verdict (spec §7).

### Open decisions for Arafat (gate the live run — resolve at the top of the TB8 session)

- **Source for `fetch_exchange_listings`:** membership-derived (offline, recommended) vs. live NSE
  scrape?
- **Dry-run first?** Recommend a small end-to-end smoke (e.g. ~20 ISINs through steps 1–7) to
  confirm the wiring before committing to the full multi-hour panel ingest.

- **Deliverable:** `tb8_ingest.py` orchestrator + the 3 wired seams; a populated panel; a per-check
  PASS/FAIL table + overall verdict line + the pinned `DISCOVERY_START` month, recorded in this
  Session log.
- **Done-criteria:**
  - [ ] 3 seams wired (`fetch_exchange_listings`, `EligibleOnDate`, `ReconReader`); no new threshold.
  - [ ] Panel populated via the idempotent/checkpointed orchestrator (resumable; per-ISIN failures
        → `PipelineError`, never crash the run); cross-check clean.
  - [ ] `run_acceptance_gate` executed over the real DISCOVERY panel; all five §6 checks reported
        with an explicit PASS/FAIL each + an overall verdict (Rule 12).
  - [ ] Durable-≥75%-by-name `DISCOVERY_START` month pinned from the coverage check (not 20-name
        probe samples); `FINAL_OOS` untouched.
- **Session log:** _(empty — TB8 not yet started; to be filled by the executing session.)_

---

## Exit criteria for the Track-B data layer

- [x] TB0 locked (§8 thresholds frozen as constants; spec committed, no longer DRAFT).
- [x] TB0.5 feasibility probe run (2026-06-17); by-name coverage reported (5/65/70/85% across
      DISCOVERY); **qualified NO-GO** stated — re-probe broader source before any TB1–TB6 build;
      no §6 threshold lowered.
- [x] TB0.5 **broader re-probe** run (2026-06-17): pooled Annual+Half-Yearly+Quarterly NSE feeds.
      Recovered availability but coverage held (5/65/70/85%) — 2019/2021 still FAIL 75%; 2018 is a
      structural XBRL desert. Forward path = `PANEL_START`/`DISCOVERY_START` rescope (a **§10
      pre-registration decision for Arafat**, not a threshold edit). No §6 threshold moved.
- [x] TB0.5 **tightening re-probe** run (2026-06-17): completed `_NET_INCOME_TAGS` with the
      verified-standard bank PAT variants → **2021=85% PASS, 2023=95% PASS**; 2019=65% (non-
      structural residual: BSE-recoverable + 2 genuine recent-IPO gaps); 2018=5% structural.
      **Verdict = CONDITIONAL GO** — clears §6.1 from ~2020/2021 on; 2018 unrescuable. Decision for
      Arafat: rescope `DISCOVERY_START` to (A) ~2021 (already PASS) or (B) ~2019 + BSE-fallback
      lever. No §6 threshold moved.
- [x] TB0.5 **STEP-1 hole-fill re-probe** run (2026-06-17): NSE-only coverage **crosses 75%
      between Nov-2019 and Jun-2020** (2019-11=55% FAIL; 2020-06=100%, 2020-12=80%, 2021-03=90%
      PASS) → BSE off the critical path. **DECISION RESOLVED (Arafat, 2026-06-17): rescope
      `DISCOVERY_START` ≈2020, NSE-only, no BSE** — pre-registered in `00_PREREGISTRATION.md`;
      exact month pinned at TB7. No §6 threshold moved; `FINAL_OOS` pristine. **Probe = GO.**
- [x] TB1–TB6 built one layer at a time, each test-gated, ingest idempotent + checkpointed,
      every schema change via Alembic, all exchange fetches mocked in tests.
      (TB1 ☑ TB2 ☑ TB3 ☑ TB4 ☑ TB5 ☑ TB6 ☑)
- [x] TB7 §6 gate built + test-gated (2026-06-18); honest per-check pass/fail against the pre-committed thresholds. Production gate run over the real panel is a follow-on operational step (depends on wiring the concrete exchange listings source — see TB2/TB7 session logs).
- [ ] **TB8 — production ingest + §6 gate RUN** (scoped 2026-06-18; not started). Wires the 3
      remaining seams, populates the real DISCOVERY panel (NSE-only, ≈2020), and executes
      `run_acceptance_gate` to produce the **actual** PASS/FAIL verdict + the pinned
      `DISCOVERY_START` month. The two branches below are gated on **TB8's** verdict — TB7's
      machinery alone yields no verdict (no panel was ingested).
- [ ] If TB8 PASSES → write `03_TRACK_B_PREREG.md` (value/quality factors + H3 test + coarse
      grids) **before any backtest** — a separate prereg, separately approved.
- [ ] If TB8 FAILS → Track B closes as a research note (spec §7 / prereg §10); `FINAL_OOS`
      left pristine. Manufacturing coverage by loosening §6 after the fact is forbidden.

> This file builds **only** the data layer. The one-shot `FINAL_OOS` run belongs to a future
> Track-B execution task created from `03_TRACK_B_PREREG.md` — never from here.
