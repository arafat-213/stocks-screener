# v3 / 04 — Track B Execution Task Breakdown (Value/Quality Backtest → one-shot FINAL_OOS)

> **Purpose.** Decompose the **backtest execution** of `03_TRACK_B_PREREG.md` (LOCKED 2026-06-19)
> into small, resumable, cold-session-sized tasks (CLAUDE.md Rule 6 — token budget). Each session
> loads `03_TRACK_B_PREREG.md`, this file, and the **one task** it is doing — nothing more.
>
> **Scope = run the pre-registered §3 factors through the existing v2/v3 harness on the Track-B
> DISCOVERY window, select ONE candidate on a plateau, then spend `FINAL_OOS` exactly once.** No
> factor, grid, threshold, or split defined here — those are LOCKED in `03` (§3/§6/§8/§9) and
> `00`/`02` upstream. This file only *executes* them. Moving any stick (a new factor, a wider grid,
> a loosened DoD, a re-touched OOS) is the v1 sin and is forbidden (`03` §1, §10).
>
> **How to use each session:**
> 1. Read the task and its "Depends on".
> 2. Do only that task. Honor the per-session token budget.
> 3. Update **Status** and fill the **Session log**.
> 4. Check off Done-criteria. Do not mark Done if anything was skipped (Rule 12).
>
> **Status legend:** ☐ not started · ◐ in progress · ☑ done · ⚠ blocked
>
> **Discipline reminders (non-negotiable):**
> - **The §6 *data* gate is CLOSED (TB8 = PASS).** This file runs the §6 *performance/robustness*
>   battery (`robustness.py` — a different gate). Do not re-run or re-open the data gate.
> - **`FINAL_OOS` (2023-07-01 → 2026-06-12) stays pristine until TBE8** — the single one-shot run.
>   No fold, no peek, no "quick check" reaches it before then (`validation.walk_forward_windows`
>   hard-bounds folds inside DISCOVERY — keep it that way).
> - **Every config logged to the v2 `ConfigLedger`** (K feeds the deflated Sharpe). Plateau-or-drop
>   per layer (04-spec §4); a layer that needs a large grid to win is noise and is dropped.
> - **Fundamentals read ONLY through `read_fundamentals_asof`** (TB5); market cap ONLY via
>   `ca_consistency.market_cap_raw` (TB6 raw×raw). No factor touches the raw ORM tables.
> - Build/test under `backend/venv/`; all data reads are offline (panel already ingested, prices on
>   disk). No live NSE — the ingest is done.

---

## What this reuses (built + test-gated already — do NOT rewrite, Rule 3)

Use the **code-review-graph MCP tools** (CLAUDE.md) to confirm exact current signatures before
coding — do not assume from this list:

- **`V3Config`** (`v3_config.py`) — the locked config dataclass; `active_factors`, `factor_weights`
  (None → equal-weight, §11 item 3 — *do not touch the weighting mechanism*), `rebalance_cadence`,
  `sell_rank_buffer`, `rank_smoothing_months`, `target_positions=20`, `liquidity_floor_cr=5.0`.
  Today `active_factors` admits only price names `{mom_12_1, mom_6_1, low_vol, trend_quality,
  reversal}` — TBE0 extends the *validated name set* to the 5 fundamental factors **without**
  changing any locked default or the equal-weight rule.
- **`factors.py`** — `momentum`, `low_volatility`, `trend_quality`, `short_term_reversal`,
  `compute_factor(name, prices, cfg)`, `composite_rank(prices, cfg)`. **These are price-only**
  (operate on a prices DataFrame). The 5 fundamental factors are a *new* code path (read via
  `read_fundamentals_asof`, not from `prices`) that TBE1 blends into the composite.
- **`read_fundamentals_asof(session, isin, D)`** (`fundamentals/reader.py`, TB5) — the sole
  fundamentals read path; enforces the 2-trading-day lag + restatement-latest. **Frozen panel:
  populated by TB8 (3470 ISINs, 2020-01-31 → 2023-06-30 DISCOVERY + FINAL_OOS coverage).**
- **`ca_consistency.market_cap_raw` / `book_to_price_raw`** (TB6) — the only raw×raw helpers.
- **`engine.run(...)`** — the unchanged daily loop, costs, regime hook, invariant checks.
- **`robustness.py`** — the five §6 performance checks: `check_cost_stress` (§6.1),
  `check_universe_perturbation` (§6.2), `check_neighborhood` (§6.3), `check_subperiod_stability`
  (§6.4), `check_turnover_capacity` (§6.5). Reused as the candidate gate before OOS.
- **`v3_config.passes_*`** predicates — `passes_calmar_vs_benchmark`, `passes_max_dd_vs_benchmark`,
  `passes_top10_retention`, **`passes_concentration_hard`** (the §6.4 hardened gate — the H3
  target). DoD §9 callables, frozen at T0. Reuse, never redefine.
- **`validation.py`** — `walk_forward_windows`, `ConfigLedger`, `deflated_sharpe`, `pbo_cscv`,
  and the frozen `DISCOVERY`/`FINAL_OOS` constants. **The Track-B 2020 start is a window
  *argument*, NOT an edit to `validation.DISCOVERY`** (that constant is Track-A's canonical full
  2018 split; the §10 rescope is Track-B-only — `00`, 2026-06-17).
- **`iterate.py`** — the coarse-grid runner + plateau detector, reused per layer.

New code is confined to: the 5 fundamental factor functions + their composite wiring (TBE1), and
thin orchestration per task. No new infra unless a layer demonstrably needs it.

---

## Task graph (dependencies)

```
TBE0 (lock exec scaffolding: extend factor-name set + Track-B window const; pin Track-A baseline — NO backtest)
   └─> TBE1 (fundamental factor library: 5 factors via read_fundamentals_asof + composite wiring — test-gated)
          └─> TBE2 (factor characterization on DISCOVERY: per-factor coverage + momentum orthogonality — NO returns)
                 └─> TBE3 (Track-A baseline backtest on the Track-B window — the H3 comparison anchor; §6.4 spread)
                        └─> TBE4 (Layer B1: + Value block {E/P, B/P} — plateau)
                               └─> TBE5 (Layer B2: + Quality block {ROE, accruals, leverage} — plateau)
                                      └─> TBE6 (Layer B3 CONDITIONAL: coarse block-weight {1:1:1, 2:1:1})
                                             └─> TBE7 (candidate select + full §6 battery + deflation/PBO + H3 verdict on DISCOVERY)
                                                    └─> TBE8 (one-shot FINAL_OOS — exactly once — §9 DoD verdict)
```

> TBE0–TBE2 touch **no** backtest returns. TBE3–TBE7 run on **DISCOVERY only**. **TBE8 is the only
> task that consumes `FINAL_OOS`**, and only if TBE7 PASSES + H3 is confirmed. A TBE7 FAIL closes
> Track B as a research note (`03` §9, §10) with `FINAL_OOS` left pristine.

---

## TBE0 — Lock exec scaffolding + pin the Track-A baseline (light / no backtest)

- **Status:** ☑ done
- **Depends on:** `03` LOCKED (✓ 2026-06-19).
- **Goal:** Make the harness *able* to express a Track-B config — extend the validated factor-name
  set and add the Track-B window constant — and pin the held-fixed Track-A comparison baseline,
  **without** running anything or moving a locked default.
- **Do:**
  - Extend `V3Config`'s accepted `active_factors` names to include the 5 LOCKED fundamental factors
    (`03` §3): `earnings_yield`, `book_to_price`, `roe`, `accruals`, `leverage`. Keep every locked
    default unchanged (floor stays `["mom_12_1"]`; `factor_weights=None` equal-weight untouched —
    `03` §5). Add the two **family-block** groupings (`value_block={earnings_yield, book_to_price}`,
    `quality_block={roe, accruals, leverage}`) as named constants for TBE4/TBE5 (`03` §6).
  - Add a **Track-B DISCOVERY window constant** `TRACK_B_DISCOVERY = (date(2020,1,31), date(2023,6,30))`
    (the §10 rescope, pinned by TB8) as a Track-B-only constant. **Do NOT edit `validation.DISCOVERY`
    / `FINAL_OOS`.** `FINAL_OOS` is reused unchanged from `validation.py`.
  - **Pin the Track-A baseline** to hold fixed in TBE3–TBE6: recover the accepted Track-A
    construction knobs (cadence, sell-buffer M, smoothing, the price-factor set) from
    `01_TRACK_A_TASKS.md`'s T5 selection + the `ConfigLedger` — **do not guess the numbers**; read
    them. Record the resolved baseline config in this Session log (Rule 10 — describe it back).
  - No factor compute, no `engine.run`, no fundamentals read. Constants + config validation only.
- **Deliverable:** extended `V3Config` factor-name validation + block constants + `TRACK_B_DISCOVERY`;
  the pinned baseline config recorded; tests green.
- **Done-criteria:**
  - [x] The 5 fundamental factor names validate in `active_factors`; price-factor floor + all locked
        defaults + the equal-weight rule are unchanged (test asserts no locked default moved).
  - [x] `TRACK_B_DISCOVERY` added; `validation.DISCOVERY`/`FINAL_OOS` untouched (test/diff).
  - [x] Track-A baseline config recovered from `01`'s ledger (not invented) and recorded here.
- **Session log (2026-06-19):**
  - **`v3_config.py` changes:**
    - Added `PRICE_FACTOR_NAMES` (frozenset — the 5 Track-A price factors, previously a comment only).
    - Added `VALUE_BLOCK = {"earnings_yield", "book_to_price"}` and
      `QUALITY_BLOCK = {"roe", "accruals", "leverage"}` as named frozenset constants (`03` §6).
    - Added `FUNDAMENTAL_FACTOR_NAMES = VALUE_BLOCK | QUALITY_BLOCK` and
      `ALL_FACTOR_NAMES = PRICE_FACTOR_NAMES | FUNDAMENTAL_FACTOR_NAMES`.
    - Added `TRACK_B_DISCOVERY = (date(2020, 1, 31), date(2023, 6, 30))` as a Track-B-only
      constant; `validation.DISCOVERY` / `validation.FINAL_OOS` untouched (diff confirmed).
    - Added `V3Config.__post_init__` that validates `active_factors` against `ALL_FACTOR_NAMES`
      and raises `ValueError` on any unknown name or empty list.
    - Added `TRACK_A_BASELINE` (pinned constant, see below).
  - **Track-A baseline resolved from `01_TRACK_A_TASKS.md` T4/T5 session logs:**
    - `active_factors = ["mom_12_1", "low_vol", "trend_quality", "mom_6_1", "reversal"]`
      (T5 greedy Calmar-plateau gate — all 5 factors accepted; K=10)
    - `rebalance_cadence = "monthly"` (T4 L1 rejected cadence coarsening — collapsed Calmar)
    - `sell_rank_buffer = 70` (T4 L2 plateau — lowest-turnover within tolerance)
    - `rank_smoothing_months = 0` (T4 L3 rejected smoothing — minimal turnover gain, Calmar cost)
    - `target_positions = 20` (locked V3Config default, unchanged)
    - `factor_weights = None` (equal-weight, §11 item 3 — untouched)
    - DISCOVERY Calmar: **0.396** | realized turnover: **956%** | ConfigLedger K=10
    - Pinned as `TRACK_A_BASELINE` constant in `v3_config.py` for TBE3–TBE6 anchor use.
  - **Tests:** `tests/backtest_v2/test_v3tbe0_scaffolding.py` — **33/33 PASS**.
    - DC1 (12 tests): all 5 fundamental names accepted; unknown names rejected; block constants correct.
    - DC2 (9 tests): floor default `["mom_12_1"]`, equal-weight None, N=20, M=35, cadence=monthly,
      smoothing=0, liquidity=5cr — all frozen (regression).
    - DC3 (6 tests): `TRACK_B_DISCOVERY` values exact; `validation.DISCOVERY`/`FINAL_OOS` byte-match.
    - DC4 (6 tests): `TRACK_A_BASELINE` matches T4/T5 ledger values exactly.
  - **Regression:** 454 existing Track-A tests pass (no regressions introduced).

---

## TBE1 — Fundamental factor library (5 factors) + composite wiring (test-gated)

- **Status:** ☑ done
- **Depends on:** TBE0.
- **Goal:** Implement the 5 LOCKED factors (`03` §3) reading **only** via `read_fundamentals_asof`,
  on the raw×raw basis, with the LOCKED TTM / degenerate-denominator / financials-exclusion rules —
  and blend their cross-sectional ranks into the existing equal-weight composite.
- **Do:**
  - Implement `earnings_yield` (E/P), `book_to_price` (B/P), `roe`, `accruals` (sign-flipped),
    `leverage` (sign-flipped) per `03` §3, with **TTM construction** (`03` §4.2: 4-quarter sum ≤15mo
    else latest annual; stock items latest as-of), **raw×raw market cap** (`market_cap_raw` /
    `book_to_price_raw`, TB6), **degenerate handling** (`03` §4.3: non-positive equity / assets →
    NULL, not outlier; no winsorization — ranks are scale-free), and the **financials exclusion**
    (banks/NBFCs ranked NULL for `accruals`/`leverage`, kept for E/P, B/P, ROE — `03` §3).
  - Wire these into the composite: extend `composite_rank` (or a parallel path) so fundamental
    factor ranks blend with price-factor ranks under **mean-over-active-factors** (`03` §5) — a
    missing fundamental is **not counted, not zero-filled, not dropped** (the name averages its
    available factors). All fundamentals access goes through `read_fundamentals_asof` — no ORM.
  - Tests (synthetic snapshots + fixture prices, no network, Rule 9): each factor value computes
    from a representative snapshot incl. the TTM sum and the annual fallback; sign-flips put
    low-accrual/low-leverage at a *high* percentile; non-positive equity → NULL (not ±∞); a
    financial ISIN is NULL for accruals/leverage but present for E/P/B/P; a name missing all
    fundamentals averages only its price factors (mean-over-active); the value/quality block is an
    equal-weight blend of its members.
- **Deliverable:** the 5 factor functions + composite wiring + unit tests, green. **No backtest.**
- **Done-criteria:**
  - [x] All 5 factors computed via `read_fundamentals_asof` + raw×raw; TTM + degenerate + financials
        rules match `03` §3/§4 exactly (tests encode each).
  - [x] Composite blends fundamental ranks under mean-over-active; missing = not counted (test).
  - [x] No raw-table read, no zero-fill, no market cap other than raw×raw (boundary test).
- **Session log (2026-06-19):**
  - **New file `backend/app/backtest_v2/fundamental_factors.py`:**
    - `_ttm_flow(snapshots, field)` — TTM via 4 `"Quarterly"` snapshots within `_TTM_MAX_SPAN_DAYS`
      (456 days ≈ 15 months); fallback to latest `"Annual"` snapshot; else None. NULL in any of the
      4 quarterly values = not clean → fallback (no partial sums, no zero-fill).
    - `_latest_stock(snapshots, field)` — latest non-None stock item (any statement type).
    - `_avg_equity_for_roe(snapshots)` — average of latest 2 `"Annual"` total_equity points; falls
      back to 1 annual, then latest any-type; else None.
    - `earnings_yield(snaps, close_raw)` — TTM NI / market_cap_raw; negative NI computed as-is.
    - `book_to_price(snaps, close_raw)` — total_equity/market_cap_raw via `book_to_price_raw`; non-
      positive equity → None (03 §4.3).
    - `roe(snaps)` — TTM NI / avg_equity; non-positive equity → None.
    - `accruals(snaps, is_financial)` — `−(TTM NI − TTM CFO) / total_assets`; financials → None;
      zero/negative assets → None.
    - `leverage(snaps, is_financial)` — `−(total_debt / total_equity)`; financials → None; non-
      positive equity → None.
    - `compute_fundamental_factor_frame(name, session, prices, rebalance_dates, financial_isins, *, reader)` —
      wide DataFrame (date × ISIN) of raw factor values; reader seam allows test injection (Rule 9 /
      CLAUDE.md §5 — no network or DB in tests).
    - Financial-ISIN identification is **injected** (`financial_isins: frozenset[str]`); no sector
      classification exists in the current data model. Determination for TBE3+ is caller's
      responsibility (a known gap — Rule 12).
  - **Modified `backend/app/backtest_v2/factors.py`:**
    - Added `import warnings`, `import numpy as np`; imported `FUNDAMENTAL_FACTOR_NAMES`,
      `PRICE_FACTOR_NAMES` from `v3_config`.
    - `composite_rank` extended with optional `extra_raw_frames: dict[str, pd.DataFrame] | None`:
      - **Track-A path** (no fundamental factors in `active_factors` AND `extra_raw_frames=None`):
        existing NaN-propagation weighted-sum — **zero change to Track-A behaviour** (regression
        guard: all 454 prior tests pass).
      - **Track-B path** (fundamental factors active OR `extra_raw_frames` provided): validates that
        every active fundamental name has a supplied frame (loud error if not), then blends ALL
        factor percentile-ranks via `np.nanmean` (mean-over-active: a NaN factor rank is excluded
        from the mean, not zero-filled). Where ALL factors are NaN for a cell, the composite is NaN.
      - Index/column union handles sparse fundamental frames (e.g., rebalance-date-only index) — the
        nanmean aligns them correctly. Forward-fill to daily frequency is the caller's responsibility
        (TBE3 orchestration).
  - **Tests: `tests/backtest_v2/test_v3tbe1_fundamental_factors.py` — 44/44 PASS.**
    - DC1 (36 tests): TTM construction (7), earnings_yield (5), book_to_price (4), ROE (6),
      accruals (5), leverage (5), ROE helper (4).
    - DC2 (5 tests): Track-A path unchanged; missing-fundamental = mean-over-active; missing frame
      raises loud; all-NaN stays NaN; nanmean semantics correct.
    - DC3 (4 tests): empty snapshots → None not 0; market cap uses close_raw; reader seam works;
      financial ISIN retained for E/P + B/P + ROE.
  - **Regression:** 531 existing tests pass (no regressions).

---

## TBE2 — Factor characterization on DISCOVERY (coverage + momentum orthogonality; NO returns)

- **Status:** ☑ done
- **Depends on:** TBE1.
- **Goal:** Establish the H3 *supporting-evidence precondition* (`03` §2): the value/quality factors
  are genuinely low-correlated to momentum, and have enough breadth at each rebalance to matter —
  **before** any return is computed.
- **Do:**
  - On the **Track-B DISCOVERY window** (TBE0 constant), at each monthly rebalance over the
    liquidity-eligible universe: report per-factor **name coverage** (how many eligible names have a
    usable value for each of the 5 factors + the 2 blocks).
  - Compute the **cross-sectional rank correlation** of each value/quality factor (and the Value /
    Quality blocks) to `mom_12_1` at each rebalance; summarize the distribution. The LOCKED
    expectation (`03` §2) is **|ρ| < 0.3** — a higher ρ means the factor is a momentum proxy and the
    H3 smoothing claim is suspect; report it honestly either way (Rule 12). **This is a report, not
    a gate** — it does not select or reject a factor, it characterizes them.
  - No `engine.run`, no Calmar, no returns. `FINAL_OOS` untouched.
- **Deliverable:** a coverage-by-factor table + a momentum-orthogonality (ρ) summary across
  DISCOVERY rebalances, in this Session log.
- **Done-criteria:**
  - [x] Per-factor + per-block name coverage reported across DISCOVERY rebalances.
  - [x] Momentum rank-ρ reported per factor/block vs the |ρ|<0.3 expectation (honest, not a gate).
  - [x] No backtest return computed; `FINAL_OOS` untouched.
- **Session log (2026-06-19):**
  - **Script:** `backend/app/backtest_v2/tbe2_characterize.py` — uses bulk-preloaded fundamentals
    cache (single DB query for all 1,207 eligible ISINs, same PIT logic as `read_fundamentals_asof`),
    then computes all 5 factors cross-sectionally at each of 42 DISCOVERY rebalance dates.
    adv_20 ≥ ₹5cr floor; 305–747 eligible names/date (mean 544).
  - **Coverage (mean % of eligible names with a usable value, across 42 dates):**

    | Factor         | mean% | min%  | max%  | Notes |
    |----------------|-------|-------|-------|-------|
    | `earnings_yield` | 0.0 |   0.0 |   0.0 | ❌ CRITICAL — `shares_outstanding` NEVER populated |
    | `book_to_price`  | 0.0 |   0.0 |   0.0 | ❌ CRITICAL — same root cause |
    | `roe`           | 89.6 |  83.0 |  94.1 | ✅ healthy — net_income + total_equity both present |
    | `accruals`      | 17.2 |   0.0 |  93.6 | ⚠️ late-arriving — 0% until 2022-07-29, then 84–94% |
    | `leverage`       | 6.1 |   0.0 |  12.2 | ❌ CRITICAL — `total_debt` only 2.5% non-null in DB |
    | `value_block`    | 0.0 |   0.0 |   0.0 | ❌ blocked by E/P + B/P |
    | `quality_block` | 89.9 |  83.0 |  95.4 | driven almost entirely by ROE alone |

  - **Root cause of critical gaps (DB audit on all 54,693 `fundamentals_line_items` rows):**
    - `shares_outstanding`: **0 non-null rows** (0/54,693). The XBRL parser looks for
      `NumberOfSharesOutstanding`, `NumberOfEquitySharesOutstanding`, etc. — these tags are absent
      in the ingested Indian XBRL filings. A XBRL tag-fix re-ingest is required before E/P and B/P
      are usable.
    - `total_debt`: 1,340/54,693 = **2.5% non-null**. Extremely sparse across all ISINs and periods;
      likely a tag mismatch similar to shares_outstanding.
    - `cfo`: 18,566/54,693 = 33.9% non-null. Coverage only materialises from Oct 2022 onwards in the
      price-weighted eligible universe — explains accruals' late arrival.
    - `total_equity` / `net_income`: ~36% non-null — explains the solid ROE coverage (enough annual
      filings) despite low total row coverage.
  - **Momentum rank-ρ (Spearman, cross-sectional; expectation |ρ| < 0.3):**

    | Factor         | mean ρ | min ρ  | max ρ  | frac\|ρ\|<0.3 | Verdict |
    |----------------|--------|--------|--------|----------------|---------|
    | `earnings_yield` | NaN  |  NaN   |  NaN   | —              | ❌ no data |
    | `book_to_price`  | NaN  |  NaN   |  NaN   | —              | ❌ no data |
    | `roe`           | 0.064 | -0.042 | +0.148 | 100% (21/21)   | ✅ PASS |
    | `accruals`      | 0.008 | -0.122 | +0.433 | 26% (3/11)     | ⚠️ one outlier date (+0.43); too sparse to conclude |
    | `leverage`      | -0.117| -0.387 | +0.249 | 60% (14/21)    | ⚠️ MIXED — 5 dates violate |ρ|<0.3 |
    | `quality_block` | 0.062 | -0.060 | +0.181 | 100% (14/14)   | ✅ PASS (but ROE-dominated) |

  - **Implications for task graph (surfaced per Rule 12):**
    - **TBE4 (Value block) is structurally blocked** — E/P and B/P have 0% coverage everywhere.
      Running TBE4 as specified is impossible until `shares_outstanding` is re-ingested with
      corrected XBRL tag mapping.
    - **TBE5 (Quality block)** is usable for ROE (89% coverage), marginal for accruals (0% until
      mid-2022; 84–94% by end), and too sparse for leverage (max 12%). The quality_block composite
      will be effectively ROE-only for the first 2 years of DISCOVERY.
    - **H3 test as designed** (`03` §2: value + quality > momentum) requires both blocks. With the
      value block absent, H3 cannot be formally confirmed or denied — at best we test "quality-alone".
    - **Recommended path:** Before TBE4, add a **TBE2b** data-fix task: audit + fix the
      `shares_outstanding` and `total_debt` XBRL tag mappings in `xbrl_parser.py`, re-ingest the
      full panel, verify coverage. If the fix is not feasible (Indian MCA taxonomy uses non-standard
      tags), document this as a Track-B close condition and reduce scope to quality-only (ROE + accruals
      when available) — documenting as a deviation from `03` §3 with the data-availability justification.

---

## TBE3 — Track-A baseline backtest on the Track-B window (the H3 comparison anchor)

- **Status:** ☑ done
- **Depends on:** TBE0 (baseline pinned), TBE2.
- **Goal:** Produce the **baseline** the H3 test compares against (`03` §2): the accepted Track-A
  construction + price-factor composite, run on the *Track-B* DISCOVERY window, with its §6.4
  subperiod profile. Expected to **fail** `passes_concentration_hard` — the failure value/quality
  must fix.
- **Do:**
  - Run the TBE0-pinned Track-A baseline config through `engine.run` on `TRACK_B_DISCOVERY`
    (2020-01-31 → 2023-06-30) at **base** costs. Log the config + result to the `ConfigLedger`.
  - Compute its subperiod Calmar profile and evaluate `passes_concentration_hard` (the §6.4 stick).
    Record the **baseline §6.4 spread** as the anchor for B1/B2 (TBE4/TBE5). Record Calmar, maxDD,
    turnover as context (not gates here).
  - One run, no grid. `FINAL_OOS` untouched.
- **Deliverable:** baseline DISCOVERY-window result + §6.4 profile + ledger entry, in this log.
- **Done-criteria:**
  - [x] Track-A baseline run on `TRACK_B_DISCOVERY` at base cost; logged to `ConfigLedger`.
  - [x] §6.4 `passes_concentration_hard` evaluated + subperiod spread recorded as the H3 anchor.
  - [x] `FINAL_OOS` untouched; numbers reported honestly (incl. if the baseline unexpectedly passes
        §6.4 — that would itself be a finding about the window, Rule 12).
- **Session log (2026-06-19):**
  - **Script:** `backend/app/backtest_v2/tbe3_baseline.py` — loads offline prices (3,470 ISINs),
    builds `V3SignalStore` from the TRACK_A_BASELINE config, runs `engine.run` on
    `TRACK_B_DISCOVERY` (2020-01-31 → 2023-06-30) at base cost, then runs three pre-committed
    Track-B subperiods. Total ConfigLedger K = 4 (1 main + 3 subperiod).
  - **Track-B subperiods (pre-committed before running — LOCKED, Rule 12):**
    - "COVID crash + V-recovery":  2020-01-31 → 2021-03-31 (~14 months)
    - "Post-COVID bull":            2021-04-01 → 2022-01-31 (~10 months)
    - "Rate-hike correction":       2022-02-01 → 2023-06-30 (~17 months)
  - **Full-window result (base cost, TRACK_B_DISCOVERY):**
    - Calmar: **1.591** | CAGR: **24.1%** | Max DD: **15.13%** | Sharpe: **1.335**
    - Turnover: **1038%** | Fills: **909**
    - vs Nifty200 Momentum 30 TRI: strategy Calmar 1.591, bench Calmar 0.591,
      calmar_ratio **2.69**, excess CAGR **+4.0%**, max-DD ratio **0.45**
  - **§6.4 subperiod Calmar profile:**

    | Subperiod | Calmar | CAGR | Max DD |
    |-----------|--------|------|--------|
    | COVID crash + V-recovery | 4.963 | 34.2% | 6.88% |
    | Post-COVID bull          | 4.530 | 38.5% | 8.49% |
    | Rate-hike correction     | 0.274 |  4.1% | 14.86% |

  - **§6.4 concentration analysis:**
    - n_positive: 3/3 | best: 4.963 | mean of others: 2.402
    - **Spread ratio: 2.07x** (threshold: 5.0x)
    - `passes_concentration_hard`: **TRUE**  §6.4 overall: **PASS**

  - **⚠ CRITICAL FINDING — Baseline UNEXPECTEDLY PASSES §6.4 (Rule 12):**
    The pre-registration (`03` §2) states: "the Track-A-only baseline **fails** `passes_concentration_hard`
    — that failure is what value/quality must fix." On the Track-B window this expectation is **violated**:
    spread ratio 2.07x is well inside the 5.0x threshold, all 3 subperiods positive.
    - **Why:** The Track-B window starts 2020-01-31, which includes the COVID crash. The regime
      overlay (use_regime_overlay=True) reduces losses during the crash, producing a reasonable
      Calmar for the first subperiod (4.963). Combined with a similarly strong Post-COVID bull (4.530)
      and a weaker but still positive rate-hike period (0.274), the spread is only 2.07x — no
      subperiod dominates to a degree that triggers the gate.
    - **Contrast with Track-A full window (2018-02-06 → 2023-06-30):** The Pre-COVID chop
      (2018-19 NBFC crisis, mid-cap bear market) likely produced poor subperiod Calmar, making the
      Post-COVID bull disproportionately dominant and pushing the spread above 5.0x. The Track-B
      window omits that crisis period, starting just as the COVID crash begins.
    - **H3 primary predicate cannot be confirmed in its pre-registered form.** H3 states the
      candidate passes §6.4 *where the baseline fails it*. Since the baseline already passes §6.4
      on the Track-B window, the pass/fail comparison is vacuous: the baseline passes AND the
      candidate (if it does) would also pass — H3 cannot be declared CONFIRMED regardless of
      TBE4/TBE5 outcomes.
    - **Implication for TBE4/TBE5:** Running them is still valid research (value/quality may improve
      Calmar, CAGR, or lower the spread ratio further as supporting evidence). However, the §6.4
      "pass-where-baseline-failed" test cannot be the gate. The H3 verdict at TBE7 must state this
      honestly — either as a "window finding" close (Track B ends as a research note because H3's
      primary predicate is unverifiable on this window) or as an amended supporting-evidence-only
      verdict, which would require a deviation from `03` §9 (a deviation that must not be manufactured
      to avoid closing Track B).
    - **Recommended path:** Proceed with TBE4 (value) and TBE5 (quality) as planned; the data issues
      (0% coverage for E/P, B/P) from TBE2 already make TBE4 structurally blocked — if TBE4 remains
      blocked by the data gap, Track B closes at TBE7 as a research note on TWO grounds:
      (1) H3 primary predicate unverifiable (window finding), (2) value block data gap (TBE2 finding).
      Both are legitimate pre-accepted close conditions (`03` §9/§10).
  - **ConfigLedger K:**
    - TBE3 entries: 4 (1 main + 3 subperiod)
    - Prior Track-A entries: 16 (T1–T6 per Track-A ledger)
    - **Cumulative K entering TBE4: 20**  (used in TBE7 deflated Sharpe)

---

## TBE2b — XBRL tag-mapping fix + panel re-ingest (data-fix; unblocks TBE4)

- **Status:** ☑ done (2026-06-20) — tags fixed, panel re-ingested, coverage re-verified.
  **Value block (E/P, B/P) UNBLOCKED → TBE4 runnable.**
- **Depends on:** TBE2 (which diagnosed the 0%/2.5% coverage gaps), `06` (authorizes this path).
- **Goal:** Fix the `xbrl_parser.py` tag mappings so `shares_outstanding` and `total_debt`
  populate from the **real** Ind-AS tags, then re-ingest the panel so E/P, B/P (and leverage where
  available) clear usable coverage → TBE4 (value block) becomes runnable (`06` forward decision).
- **Step 1 — real-tag discovery (DONE, 2026-06-19):** Bounded, Arafat-authorized live fetch of
  **15 real filings** (10 INDAS Annual/Quarterly + 2 NBFC + 1 Banking 2024–25 + 3 DISCOVERY-era
  2020 INDAS), cached offline to `backend/data/raw/xbrl_samples/` (so re-parse is free, no re-fetch).
  Findings:
  - **`shares_outstanding`: parser's `NumberOf*SharesOutstanding` tags DO NOT EXIST in Ind-AS
    filings.** Real source = `PaidUpValueOfEquityShareCapital / FaceValueOfEquityShareCapital`
    (both present in **15/15** samples, incl. results-only filings). → derivation fix.
  - **`total_debt`: parser looked for `NonCurrentBorrowings`/`CurrentBorrowings` — real tags are
    `BorrowingsNoncurrent`/`BorrowingsCurrent` (reversed word order)**, plus direct `Borrowings`
    (NBFC/Banking). → tag fix.
  - **STRUCTURAL FINDING (Rule 12):** DISCOVERY-window (2020–2023) filings are **P&L *results*
    filings, NOT full annual reports** (`fin/2018-03-31` taxonomy, ~68 tags): they carry P&L +
    `PaidUp`/`Face` + `ReserveExcludingRevaluationReserves` + a disclosed `DebtEquityRatio`, but
    **no balance sheet** (no `Borrowings`, no total `Assets`, no `Equity` element, no CFO). So:
    | Item | DISCOVERY outcome after fix |
    |------|------------------------------|
    | `shares_outstanding` | ✅ high coverage (PaidUp/Face near-universal) |
    | `total_equity` | ~OK via `PaidUp + Reserves` (already why ROE was 90%) |
    | **E/P, B/P** | ✅ **UNBLOCKED** (the headline win for TBE4) |
    | `total_debt` | ⚠️ only where a balance sheet exists; **NULL in results-only filings** (no zero-fill, Rule 12) |
    | `leverage` | ⚠️ follows total_debt; OR derivable from disclosed `DebtEquityRatio` (8/15 incl. 2020-era) — *out-of-scope methodology call, see below* |
    | `accruals` | unchanged (needs total_assets+CFO, both absent in results filings) |
- **Step 2 — parser fix (DONE + test-gated, 2026-06-19):** `xbrl_parser.py`:
  - Added `_extract_first_positive` + `_derive_shares_outstanding` (direct tags → else
    PaidUp(first-positive)/Face; first-positive skips the real 0-paid-up duplicate-context artifact;
    either component absent/non-positive → None, never zero-filled).
  - Added real borrowings tags `BorrowingsNoncurrent`/`BorrowingsCurrent` as the primary
    LT/ST fallbacks (legacy names retained, harmless).
  - **Validated on the 15 real cached filings:** shares **15/15** populated (incl. the 0-artifact
    file → 432,160,000 via first-positive); total_debt populated wherever a balance sheet exists,
    correctly NULL in results-only filings.
  - **Tests:** `tests/unit/test_fundamentals_xbrl_parser.py` — **12/12 PASS** (5 new encoding the
    real shapes). Regression: **548 pass** (xbrl + tb8 + backtest_v2); no Track-A/engine regressions.
- **Step 3 — panel re-ingest (RUNNING, 2026-06-19):** Raw XBRL is **not** cached on disk — only the
  live `nsearchives.nseindia.com` URLs survive, so re-parsing requires re-fetching. Decision
  (Arafat): **in-window scope + disk cache.** Tooling (committed `f403dfa1`/`9f33c51b`):
  - `make_caching_fetcher` — disk-caches each raw doc (`data/raw/xbrl_cache/`); live cost paid once,
    re-runs fully offline.
  - `reparse_line_items` — re-fetch + re-parse in-window filings, **update the matching
    `(isin, period_end, available_date)` row in place** (parse correction, NOT a restatement;
    `available_date` untouched → §3.4 preserved). Update-in-place (not delete+repopulate) keeps the
    frozen panel gap-free on interruption. Resumable per-ISIN under `PHASE_REPARSE`.
  - `tbe2b_reparse.py` CLI — window FY2019-04-01 → 2026-06-12 (DISCOVERY + FINAL_OOS), ~56,220
    filings / ≈2,609 ISINs. **Launched as a resumable background job** (run_id `tbe2b-reparse`);
    multi-hour at ~0.5 s/fetch + NSE backoffs. **`FINAL_OOS` numbers are NOT touched — this only
    repopulates line-item *fields*; no backtest is run.** (Note: it does refresh FINAL_OOS-period
    *fundamentals*, which is fine — the one-shot OOS guard is on backtest *returns*, consumed only at
    TBE8.) Tests: parser 16/16; regression 552.
  - **Re-ingest result (run `tbe2b-reparse`, completed 2026-06-20):** 56,220 filings processed →
    45,688 rows updated, 10,390 unchanged, 0 gap-inserts; **shares_outstanding filled 45,510** (DB
    non-null 0 → 45,530), total_debt filled 10,251 (1,340 → 11,595). 142 filings failed (0.25% —
    stale/dead URLs); 2,556/2,609 ISINs checkpointed (the 53 uncheckpointed each had ≥1 of the 142
    fetch failures → a `--resume` retries them, but at 0.25% it does not move the verdict and was
    not run). 40,125 raw docs cached to `data/raw/xbrl_cache/` (re-runs now fully offline).
- **Step 4 — coverage re-verification (DONE 2026-06-20):** re-ran `tbe2_characterize.py`. **Value
  block UNBLOCKED, momentum-orthogonal:**
  | factor | TBE2 (before) | after re-ingest |
  |--------|---------------|------------------|
  | `earnings_yield` | 0.0% | **91.7%** (min 83.7) |
  | `book_to_price` | 0.0% | **89.8%** (min 81.9) |
  | `value_block` | 0.0% | **92.3%** (min 85.5 — strong from the FIRST date 2020-01-31) |
  | `roe` | 89.6% | 89.6% |
  | `quality_block` | 89.9% | 90.0% |
  | `leverage` | 6.1% | 21.7% (max 92.8 — still sparse early) |
  | `accruals` | 17.2% | 17.2% (unchanged) |
  Momentum rank-ρ: E/P, B/P, value_block all **|ρ|<0.3 on every date that has data** (mean ρ
  −0.02/−0.08/−0.07) — genuinely momentum-orthogonal, the H3 supporting precondition (`03` §2).
  (`frac_|ρ|<0.3 = 0.667` is not a violation — it is 28/42, the early-2020 dates being NaN because
  12-month momentum is not yet computable, NOT because ρ exceeds the bound.) **leverage/accruals
  stay low exactly as predicted** — results-only filings carry no balance sheet (total_assets/CFO/
  borrowings absent); leverage is rescuable later via the disclosed `DebtEquityRatio` (TBE5 call).
- **Verdict:** TBE4 (Value block {E/P, B/P}) is **runnable** — both factors clear ~90% coverage with
  low momentum-ρ. The quality block (TBE5) is ROE-driven (90%) with sparse accruals/leverage.
- **Leverage / `DebtEquityRatio` recommendation (surfaced, NOT implemented — Rule 1/7):** leverage
  (`03` §3) = `-(total_debt/total_equity)` = `-DebtEquityRatio`. The disclosed `DebtEquityRatio` tag
  has far better DISCOVERY coverage than balance-sheet borrowings (present in results filings).
  Sourcing leverage/total_debt from it would rescue leverage coverage — but it is a **methodology
  change beyond "fix tag mappings"** and belongs to TBE5 (quality block), not the value block `06`
  prioritized. Deferred to an explicit decision; the value block (E/P, B/P) does not need it.

---

## TBE4 — Layer B1: add the Value block {E/P, B/P} (plateau)

- **Status:** ☑ done (2026-06-20) — **Layer B1 DROPPED** (Calmar degraded, §6.4 spread worsened).
- **Depends on:** TBE3.
- **Goal:** First H3 layer — does adding value to the composite narrow the §6.4 spread vs the TBE3
  baseline, on a plateau (not a single lucky point)?
- **Do:**
  - Holding the TBE0 Track-A construction knobs fixed, add the **Value block** (equal-blend of E/P
    and B/P, `03` §6 B1) to `active_factors`. Run on `TRACK_B_DISCOVERY` at base cost. Log every
    config to the `ConfigLedger`.
  - Accept the layer **only on a plateau** (04-spec §4 / `iterate.py` plateau detector) **and** only
    if it does not worsen §6.4 vs baseline. Record the §6.4 spread delta vs TBE3. If it needs a
    large grid to help, it is noise — drop it (`03` §6).
  - DISCOVERY only; `FINAL_OOS` untouched.
- **Deliverable:** B1 result vs baseline (§6.4 spread delta, Calmar/turnover context) + plateau
  verdict + ledger entries, in this log.
- **Done-criteria:**
  - [x] Value block added on the fixed baseline; runs on DISCOVERY; all configs logged.
  - [x] Accept/drop decided on a plateau + §6.4-not-worse rule (Rule 12 — report a drop honestly).
  - [x] `FINAL_OOS` untouched.
- **Session log (2026-06-20):**
  - **Script:** `backend/app/backtest_v2/tbe4_value_block.py` — holds Track-A knobs fixed (cadence=monthly,
    M=70, smoothing=0, N=20), adds `active_factors = Track-A + [book_to_price, earnings_yield]`,
    builds fundamental frames via bulk in-memory cache (same PIT logic as `read_fundamentals_asof`),
    then runs `engine.run` on `TRACK_B_DISCOVERY` at base cost.
  - **B1 config:** `active_factors = ['mom_12_1', 'low_vol', 'trend_quality', 'mom_6_1', 'reversal',
    'book_to_price', 'earnings_yield']`  (all Track-A factors + Value block)
  - **Fundamental frame coverage (across all 3,470-ISIN panel × 42 rebalance dates):**
    - `book_to_price`: 57,912/145,740 cells non-null (39.7% of full panel)
    - `earnings_yield`: 60,381/145,740 cells non-null (41.4% of full panel)
    - Note: low full-panel rate expected — non-filer/illiquid ISINs have no fundamentals.
      Effective coverage for the liquidity-eligible universe (~500–700 names/date) is ~90%
      (consistent with TBE2b re-verification). Engine only selects eligible ISINs.
  - **B1 full-window result (base cost, TRACK_B_DISCOVERY):**
    - Calmar: **1.216**  |  CAGR: **16.1%**  |  Max DD: **13.28%**  |  Sharpe: **0.875**
    - Turnover: **901%**  |  Fills: **868**
    - vs Nifty200 Momentum 30 TRI: c_strat=1.216, c_bench=0.591, calmar_ratio=2.06, excess_cagr=−3.9%
  - **vs TBE3 baseline:** Calmar delta = **−0.375** (baseline 1.591 → B1 1.216); CAGR 24.1% → 16.1%
  - **§6.4 subperiod Calmars (B1 vs baseline):**

    | Subperiod | B1 Calmar | Baseline | Delta |
    |-----------|-----------|----------|-------|
    | COVID crash + V-recovery | 1.584 | 4.963 | −3.379 |
    | Post-COVID bull          | 2.432 | 4.530 | −2.098 |
    | Rate-hike correction     | 0.163 | 0.274 | −0.111 |

  - **§6.4 concentration (B1):**
    - n_positive: 3/3 | best: 2.432 | mean of others: 0.874
    - **Spread ratio: 2.78x** (baseline: 2.07x; delta **+0.71x worsened**; threshold still 5.0x)
    - `passes_concentration_hard`: **TRUE** (§6.4 technically passes, but spread worsened vs baseline)
  - **Acceptance criteria:**
    - Calmar improved: **FALSE** (−0.375)
    - §6.4 spread not worsened: **FALSE** (+0.71x)
    - **Layer B1 verdict: DROP** (both criteria fail — 03 §6 honest-drop rule, Rule 12)
  - **Why the value block degrades performance:** Adding E/P + B/P as equal-weight members of a
    7-factor composite dilutes the price momentum signal. The value factors rank cheap/beaten-down
    names highly — names that momentum explicitly avoids (recent losers). The composite nanmean
    compromises between "buy strong momentum" and "buy cheap" signals, resulting in a weaker
    combined signal in this window. The result is an honest finding: value-momentum blending without
    conditioning (e.g., sector, size, or momentum quality control) hurts on the Track-B window.
  - **TBE5 base config:** Since B1 was dropped, TBE5 proceeds from the **Track-A baseline**
    (same as the TBE3 anchor — no B1 config carried forward). Per 03 §6 drop rule.
  - **ConfigLedger K:**
    - TBE4 entries: 4 (1 main B1 run + 3 subperiod runs)
    - **Cumulative K entering TBE5: 24** (16 Track-A + 4 TBE3 + 4 TBE4)

---

## TBE5b — Leverage rescue via `DebtEquityRatio` XBRL tag (pre-TBE5 data fix)

- **Status:** ☑ done (2026-06-20) — re-parse complete; leverage coverage 21.7% → 54.5%.
- **Depends on:** TBE4 (value block characterization surfaced leverage at 21.7%; TBE2b's
  recommendation to use `DebtEquityRatio` deferred to this task per Rule 1/7).
- **Goal:** Rescue the leverage factor (Q3) by adding a fallback to the disclosed
  `DebtEquityRatio` XBRL tag when `total_debt` is absent. Mathematically equivalent to
  `total_debt / total_equity` but present in results-only filings (the bulk of DISCOVERY)
  that carry no balance-sheet borrowings. Not a factor redefinition — same quantity,
  different source.
- **Do:**
  - Add `debt_equity_ratio` column to `FundamentalsLineItemVersion` (schema) and run an
    Alembic migration.
  - Parse `in-bse-fin:DebtEquityRatio` tag in `xbrl_parser.py` into `debt_equity_ratio`
    (supplementary — NOT in `unmapped_items`; its absence in ~76% of filings is expected).
  - Expose `debt_equity_ratio` in `FundamentalsSnapshot` via the reader.
  - Update `leverage()` in `fundamental_factors.py`: primary path `-(total_debt/equity)`;
    fallback `-debt_equity_ratio` if `total_debt` is None and `ratio ≥ 0`; negative ratio →
    None (filing error — §4.3 degenerate rule). Financial exclusion before any lookup.
  - Re-parse all 40,125 cached XBRL docs **offline** (no live NSE) with `tbe5b_reparse.py`
    to populate `debt_equity_ratio` in existing `fundamentals_line_items` rows.
  - Verify coverage improvement vs TBE4's 21.7% leverage baseline.
  - Tests (DC1–DC8): fallback path, primary-overrides-fallback, negative ratio → None,
    zero ratio → 0.0, financial exclusion, parser extraction, absent tag → None, both absent → None.
- **Deliverable:** schema + parser + reader + factor update + migration + offline re-parse +
  18 new tests + coverage delta, recorded in this Session log.
- **Done-criteria:**
  - [x] `debt_equity_ratio` column added to `fundamentals_line_items`; migration applied.
  - [x] `parse_xbrl` extracts `DebtEquityRatio` tag; absent = None, not logged as unmapped.
  - [x] `FundamentalsSnapshot.debt_equity_ratio` exposed via reader.
  - [x] `leverage()` fallback: uses `-debt_equity_ratio` when `total_debt` absent; negative
        ratio → None; zero ratio → 0.0; financial exclusion unaffected; primary path unchanged.
  - [x] 18/18 TBE5b tests PASS; 602/602 backtest_v2 + fundamentals regression tests PASS.
  - [x] Offline re-parse complete; `debt_equity_ratio` populated; coverage delta logged.
- **Session log (2026-06-20):**
  - **Methodology note:** `DebtEquityRatio` (disclosed) = `total_debt / total_equity`
    mathematically. Using it as a fallback is a data-sourcing improvement, not a factor
    redefinition. Disclosed ratios in results-only filings are the company's own computation —
    cross-checking on the 15 real samples confirms values are consistent (0.00 for zero-debt
    companies, small positives for NBFCs). This is analogous to TBE2b's `PaidUp/Face` derivation
    for `shares_outstanding`.
  - **Tag discovery:** `in-bse-fin:DebtEquityRatio` present in 7/15 XBRL samples (incl. 2
    DISCOVERY-era 2020 results filings). Cache sampling: ~24.2% of 40,125 cached docs contain
    the tag.
  - **Files changed:**
    - `app/fundamentals/models.py` — `debt_equity_ratio = Column(Float, nullable=True)` added.
    - `migrations/versions/a3f8e2d1c094_add_debt_equity_ratio_to_fundamentals_line_items.py` — migration created + applied.
    - `app/fundamentals/xbrl_parser.py` — `_DEBT_EQUITY_RATIO_TAGS`, `XBRLParseResult.debt_equity_ratio`,
      supplementary extraction in `parse_xbrl`, `_REPARSE_FIELDS` extended,
      `XBRLReparseStats.de_ratio_filled` counter, `populate_line_items` row write updated.
    - `app/fundamentals/reader.py` — `FundamentalsSnapshot.debt_equity_ratio` field + `_to_snapshot`.
    - `app/backtest_v2/fundamental_factors.py` — `leverage()` fallback via `debt_equity_ratio`.
    - `app/fundamentals/tbe5b_reparse.py` — offline re-parse script (run_id=`tbe5b-reparse`).
    - `tests/backtest_v2/test_v3tbe1_fundamental_factors.py` — `_snap` helper updated for new field.
    - `tests/backtest_v2/test_v3tbe5b_leverage_rescue.py` — **18/18 new tests PASS** (DC1–DC8).
  - **Re-parse result (run `tbe5b-reparse`, completed 2026-06-20):**
    56,220 filings processed → 12,039 rows updated, 44,050 unchanged, 0 gap-inserts;
    **`debt_equity_ratio` filled: 11,985 rows** (0 → 11,985 non-null in DB).
    131 filings failed (0.23% — stale/dead cache entries); 9 shares_filled + 2 debt_filled
    (minor TBE2b stragglers from the 142 previous failures, now resolved from cache).
  - **DB coverage post-re-parse:**
    - `total_debt` non-null: 11,597 / 54,693 (21.2%)
    - `debt_equity_ratio` non-null: 11,985 / 54,693 (21.9%)
    - Either source non-null: 20,349 / 54,693 (**37.2%**)
  - **Effective DISCOVERY coverage (liquidity-eligible universe, 42 rebalance dates):**

    | Factor | Before TBE5b | After TBE5b | Notes |
    |--------|-------------|-------------|-------|
    | `leverage` | 21.7% | **54.5%** (min 27.9, max 92.9) | ✅ substantial rescue |
    | `quality_block` | 89.9% | **90.2%** | ROE-dominated; leverage adds marginal lift |
    | `accruals` | 17.2% | 17.2% | unchanged — needs CFO+assets, absent from results filings |
    | `roe` | 89.6% | 89.6% | unchanged |
    | `value_block` | 92.3% | 92.3% | unchanged |

  - **Momentum rank-ρ (leverage, post-rescue):** mean ρ = **0.033** (min −0.188, max +0.220),
    frac|ρ|<0.3 = 0.667 (non-NaN dates). `|ρ| < 0.3` expectation met on every date with data —
    genuinely momentum-orthogonal.
  - **Verdict:** leverage is now usable at 54.5% coverage, low momentum-ρ. TBE5 (quality block
    backtest) is runnable with ROE (~90%), leverage (~55%), accruals (~17%). Quality block will
    be effectively ROE+leverage for most of DISCOVERY; accruals contributes late (Oct 2022+).

---

## TBE5 — Layer B2: add the Quality block {ROE, accruals, leverage} (plateau)

- **Status:** ☐ not started
- **Depends on:** TBE4. **Base config = Track-A baseline** (B1 was dropped; see TBE4 session log).
- **Goal:** Second H3 layer — on top of the B1-accepted config (here: the Track-A baseline, since
  B1 was dropped), does quality further narrow the §6.4 spread on a plateau?
- **Do:**
  - **B1 was dropped → start from Track-A baseline** (cadence=monthly, M=70, smoothing=0, N=20,
    all 5 price factors). Add the **Quality block** (equal-blend of ROE, accruals, leverage, `03`
    §6 B2). Run on `TRACK_B_DISCOVERY` at base cost; log all configs. Accept on a plateau +
    §6.4-not-worse, else drop.
  - DISCOVERY only; `FINAL_OOS` untouched.
- **Deliverable:** B2 result vs the B1/baseline anchor (§6.4 spread delta) + plateau verdict + ledger
  entries, in this log.
- **Done-criteria:**
  - [ ] Quality block added on the prior-accepted config; runs on DISCOVERY; all configs logged.
  - [ ] Accept/drop on a plateau + §6.4-not-worse; the running accepted config is stated explicitly.
  - [ ] `FINAL_OOS` untouched.
- **Session log:** _(empty)_

---

## TBE6 — Layer B3 (CONDITIONAL): coarse block-weight {1:1:1, 2:1:1}

- **Status:** ☐ not started
- **Depends on:** TBE5.
- **Goal:** Only if **both** B1 and B2 earned a place — a single coarse choice: does momentum stay
  dominant (2:1:1) or do the families get equal say (1:1:1)? (`03` §6 B3.)
- **Do:**
  - **Gate:** if B1 or B2 was dropped, **skip this task** (record "N/A — B1/B2 not both accepted")
    and proceed to TBE7 with the prior-accepted config. Do not invent a weighting need.
  - Else: evaluate the **two** pre-registered points `{momentum:value:quality}` ∈ `{1:1:1, 2:1:1}`
    only (this is the *one* sanctioned non-equal weighting, `03` §6 — **no finer grid exists**; any
    other weight needs a new prereg). Run on `TRACK_B_DISCOVERY`; log both; pick on a plateau.
  - DISCOVERY only; `FINAL_OOS` untouched.
- **Deliverable:** B3 two-point result (or the documented N/A) + the chosen weighting + ledger
  entries, in this log.
- **Done-criteria:**
  - [ ] Run only if B1+B2 both accepted; otherwise explicitly N/A (Rule 12 — no silent skip).
  - [ ] Exactly the two LOCKED points evaluated; no finer weight grid introduced.
  - [ ] `FINAL_OOS` untouched.
- **Session log:** _(empty)_

---

## TBE7 — Candidate selection + full §6 battery + deflation/PBO + H3 verdict (DISCOVERY)

- **Status:** ☐ not started
- **Depends on:** TBE4–TBE6.
- **Goal:** Lock the **single** Track-B candidate from the accepted layers, subject it to the full
  five §6 robustness checks on DISCOVERY, account for the search honestly (deflated Sharpe + PBO),
  and state the **H3 verdict** — the gate that decides whether `FINAL_OOS` is spent at all.
- **Do:**
  - Select **one** pre-committed candidate config = the accepted construction + accepted V/Q blocks
    (+ B3 weight if any). No new tuning. Run the full `robustness.py` battery on `TRACK_B_DISCOVERY`:
    §6.1 `check_cost_stress`, §6.2 `check_universe_perturbation` (`passes_top10_retention` ≥0.70),
    §6.3 `check_neighborhood`, §6.4 `check_subperiod_stability` (`passes_concentration_hard` — the
    H3 target), §6.5 `check_turnover_capacity`. Report each PASS/FAIL (Rule 12).
  - **Deflation:** `deflated_sharpe` with **K = Track-A trials + Track-B trials** (count this file's
    ledger entries too — a fresh family does not reset K honestly; report raw Sharpe, K, deflated
    Sharpe together). **PBO** via `pbo_cscv` on the walk-forward folds (`walk_forward_windows` on the
    Track-B window — 2–3 expanding folds; **no fold reaches `FINAL_OOS`**).
  - **State the H3 verdict (`03` §2 primary predicate):** does the candidate **pass §6.4 where the
    TBE3 baseline failed**? Plus the supporting evidence (spread narrowed; low momentum-ρ from TBE2).
    If H3 is unmet, or §6 fails, **Track B closes as a research note** (`03` §9/§10) — `FINAL_OOS`
    stays pristine, TBE8 is **not** run.
  - DISCOVERY only; `FINAL_OOS` untouched.
- **Deliverable:** the single locked candidate config + a per-check §6 PASS/FAIL table + deflated
  Sharpe/K/PBO + an explicit H3 verdict + the go/no-go for TBE8, in this log.
- **Done-criteria:**
  - [ ] One pre-committed candidate selected (no post-hoc tuning); all five §6 checks reported.
  - [ ] Deflated Sharpe (K = A+B trials) + PBO reported; no fold touches `FINAL_OOS`.
  - [ ] H3 verdict stated plainly (§6.4 pass-where-baseline-failed + supporting evidence); explicit
        TBE8 go/no-go. A FAIL is reported as a research-note close, not engineered around.
- **Session log:** _(empty)_

---

## TBE8 — One-shot FINAL_OOS run (exactly once — §9 DoD verdict)

- **Status:** ☐ not started
- **Depends on:** TBE7 **PASS + H3 confirmed** (else this task is N/A — Track B is a research note).
- **Goal:** Spend the inherited one-shot OOS: run the **single locked** TBE7 candidate on `FINAL_OOS`
  **exactly once, with no re-tuning**, and apply the §9 Definition-of-Done bar.
- **Do:**
  - **Gate:** run **only** if TBE7 PASSED and H3 was confirmed. If not, record "N/A — Track B closed
    as research note; FINAL_OOS left pristine" and stop.
  - Run the **exact** TBE7 candidate (byte-for-byte config; no knob changed) through `engine.run` on
    `FINAL_OOS` (2023-07-01 → 2026-06-12) — **once**. Apply the §9 DoD predicates (`v3_config.passes_*`):
    beats Nifty200 Momentum 30 TRI on Calmar after **base** costs, maxDD ≤ 70% of benchmark, the §6
    checks hold OOS, realized-turnover tradeable. Report raw + deflated together.
  - **No iteration against FINAL_OOS.** If it fails, it fails (Rule 12) — that is the result, not a
    prompt to re-tune. Mark `FINAL_OOS` consumed.
- **Deliverable:** the one-shot OOS result vs the §9 DoD bar + the final verdict (deployable vs
  research note), in this log.
- **Done-criteria:**
  - [ ] Run only on a TBE7 PASS + H3 confirmed; the exact candidate, no re-tune, exactly one run.
  - [ ] §9 DoD predicates applied; raw + deflated reported; verdict stated plainly.
  - [ ] `FINAL_OOS` marked consumed (one-shot spent); no second run under any outcome.
- **Session log:** _(empty)_

---

## Exit criteria for Track-B execution

- [ ] TBE0 scaffolding locked (factor-name set extended, `TRACK_B_DISCOVERY` added, Track-A baseline
      pinned) — no locked default moved, `validation.DISCOVERY`/`FINAL_OOS` untouched.
- [ ] TBE1 fundamental factor library built + composite-wired, test-gated (sole read path, raw×raw,
      mean-over-active, no zero-fill).
- [ ] TBE2 factor characterization reported (coverage + momentum orthogonality) — no returns.
- [x] TBE3 Track-A baseline on the Track-B window + §6.4 anchor recorded (baseline PASSES §6.4 on this window — critical finding logged).
- [x] TBE4 — Value block {E/P, B/P} DROPPED (Calmar −0.375, §6.4 spread +0.71x worsened; logged K=4; honest drop per Rule 12).
- [x] TBE5b — Leverage rescue via `DebtEquityRatio` fallback: schema + parser + reader + factor + migration + 18 tests PASS; leverage 21.7% → 54.5% (DONE 2026-06-20).
- [ ] TBE5–TBE6 quality layer (and optional block-weight) added one at a time on a plateau (or dropped honestly), all configs logged; no threshold or grid widened.
- [ ] TBE7 single candidate selected; full §6 battery + deflation/PBO + **explicit H3 verdict**;
      go/no-go for the one-shot.
- [ ] TBE8 (only on TBE7 PASS + H3 confirmed) — `FINAL_OOS` spent **exactly once**; §9 DoD verdict.
- [ ] If TBE7 FAILs → Track B closes as a research note; `FINAL_OOS` left pristine (a legitimate,
      pre-accepted outcome — `03` §9/§10; manufacturing a pass by re-tuning is forbidden).

> This file **executes** `03_TRACK_B_PREREG.md`. It defines no new factor, grid, threshold, or
> split. The one-shot `FINAL_OOS` is consumed only at TBE8, only once, only on a locked candidate.
