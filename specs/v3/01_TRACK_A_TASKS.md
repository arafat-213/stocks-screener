# v3 / 01 — Track A Task Breakdown & Build Tracker

> **Purpose.** Decompose the Track-A portion of `00_PREREGISTRATION.md` into small,
> resumable, session-sized tasks (CLAUDE.md Rule 6 — token budget). Each session loads
> `00_PREREGISTRATION.md`, this file, and the **one task** it is doing — nothing more.
>
> **Scope = Track A only** (price/volume factors, computable from the existing OHLCV data
> layer). Track B (fundamentals) is NOT in scope and is not started unless the prereg §11
> gate re-opens it.
>
> **How to use each session:**
> 1. Read the task and its "Depends on".
> 2. Do only that task. Honor the per-session token budget.
> 3. Update **Status** and fill the **Session log**.
> 4. Check off Done-criteria. Do not mark Done if anything was skipped (Rule 12).
>
> **Status legend:** ☐ not started · ◐ in progress · ☑ done · ⚠ blocked
>
> **Discipline reminders (from prereg §1, non-negotiable):** one layer at a time on
> `DISCOVERY` only; plateau-not-peak selection; every config logged to the v2 `ConfigLedger`;
> `FINAL_OOS` consumed exactly once at the very end; no factor without a pre-registered
> rationale; no fine weight optimization; never slice `DISCOVERY`.

---

## What this reuses (built + test-gated in v2 — do NOT rewrite, Rule 3)

- `engine.run(prices, config, *, index_prices, regime_config, cost_level, signal_store)`
  — the daily loop, costs, regime hook, 02 §10 invariants. Selection logic (top-N, buffer-M)
  is driven by whatever `signal_store.eligible_ranked(day, universe)` returns → the ranker
  swap is a **signal-layer** change, not an engine change.
- `costs.py` (3 levels), `benchmark.py` (3 TRIs + real price index), `regime.py` (overlay).
- `validation.py` — `DISCOVERY` / `FINAL_OOS`, walk-forward, `ConfigLedger`,
  `deflated_sharpe`, `pbo_cscv`.
- `iterate.py` — coarse-grid runner + `plateau_check`.
- `robustness.py` — the five §6 checks (adapt the candidate, not the checks).
- `store.read_prices_adjusted()` — OHLCV + adv_20 (no fundamentals — Track A constraint).

Keep **entirely separate** from v2's frozen `MomentumConfig` (config.py field-lock) — v3
gets its own config dataclass so v2 stays runnable.

---

## Task graph (dependencies)

```
T0 (lock: V3Config dataclass, factor list, grids+splits as constants — light)
   └─> T1 (factors.py: 5 Track-A factors + rank-blend composite + smoothing + tests)
            └─> T2 (composite signal store wired through engine's signal_store seam + tests)
                     ├─> T3 (engine rebalance-cadence knob: monthly/quarterly/semi-annual + tests)
                     │
                     └─> T4 (PARITY + TURNOVER layers: momentum-only parity vs v2 floor;
                     │        then cadence / buffer-M / smoothing on DISCOVERY — H1)
                              └─> T5 (FACTOR layers: +low-vol, +trend-quality, +6-1, +reversal — H2)
                                       └─> T6 (robustness battery on chosen candidate — §6 gate)
                                                └─> T7 (one-shot FINAL_OOS + DoD — §7)
```

T3 (cadence infra) is a prerequisite for the cadence sub-layer in T4 but is independent of
the factor work; it may be done in parallel with T1/T2 if convenient.

---

## T0 — Lock V3Config, factor list, grids & splits as constants (light / minimal code)

- **Status:** ☑
- **Depends on:** prereg §11 locked. ✓
- **Goal:** Pre-commit every v3 choice as code constants so no later session moves the stick.
- **Do:**
  - Add `app/backtest_v2/v3_config.py` (or `factors_config.py`): a `V3Config` dataclass —
    a **separate** type from `MomentumConfig` — carrying: the active factor list, composite
    weighting (equal), rank-smoothing window, `sell_rank_buffer` (M), `reconstitution`/
    `rebalance` cadence, plus the v2 fields the engine needs. Default = the **v3 floor**
    (momentum-12-1-only, monthly, M=35) so the floor reproduces v2's candidate ranker.
  - Freeze the §6 coarse grids (prereg §6) and decision predicates as module constants.
  - Reuse v2 frozen `DISCOVERY` / `FINAL_OOS` from `validation.py` (import, do not redefine).
  - No data probe needed — span unchanged from v2 T0 (2018-02-06 → 2026-06-12). Confirm by
    import, not re-read.
- **Deliverable:** `V3Config` + frozen grids/predicates; a `## Locked decisions (T0)` block
  appended to the top of `00_PREREGISTRATION.md`.
- **Done-criteria:**
  - [x] `V3Config` dataclass exists, separate from `MomentumConfig`; v3-floor defaults set.
  - [x] §6 grids + decision predicates frozen as constants.
  - [x] Frozen splits imported from `validation.py` (not redefined).
- **Session log:** 2026-06-17 — Created `backend/app/backtest_v2/v3_config.py`: `V3Config` dataclass with v3-floor defaults (`active_factors=["mom_12_1"]`, monthly, M=35); all four coarse grids frozen as module constants; five decision-predicate functions (Calmar vs bench, max-DD ratio, top-10 retention, concentration hard-FAIL); `DISCOVERY`/`FINAL_OOS` re-exported from `validation.py`. `## Locked decisions (T0)` block appended to `00_PREREGISTRATION.md`. All done-criteria met.

---

## T1 — Factor library (`factors.py`) + composite + tests

- **Status:** ☑
- **Depends on:** T0.
- **Goal:** The reusable, pure factor primitives — no engine wiring yet.
- **Do:**
  - `factors.py`: each Track-A factor (prereg §4) as a **pure cross-sectional** function
    over the prices frame: momentum-12-1, momentum-6-1, low-volatility, trend-quality,
    short-term-reversal. Each returns a per-(day, isin) score.
  - `composite_rank(...)`: percentile-rank each active factor cross-sectionally, equal-weight
    average → one composite rank. Optional rank-smoothing (N-month average) per prereg §3.1.
  - Unit tests (Rule 9 — encode WHY): each factor's sign/monotonicity on a synthetic series;
    composite of one factor == that factor's rank; rank-blend is robust to a single-factor
    outlier (the reason we rank-blend not z-blend); smoothing reduces rank churn on a noisy
    fixture. Mock all data (no live yfinance/NSE).
- **Deliverable:** `factors.py` + test module, all green.
- **Done-criteria:**
  - [x] All 5 Track-A factors implemented as pure functions, unit-tested.
  - [x] Composite rank-blend + smoothing implemented + tested (outlier-robustness test).
- **Session log:** 2026-06-17 — Created `backend/app/backtest_v2/factors.py`: five Track-A
  factors as pure functions over the long prices frame, each returning a wide (date × isin)
  raw frame oriented higher-is-better — `momentum` (reused for 12-1 & 6-1, via v2's
  `_momentum_12_1` integer-position helper, Rule 3), `low_volatility` (negated annualised
  vol, same formula as `signals.py`), `trend_quality` (fraction of up-days), and
  `short_term_reversal` (negated 1M return). `composite_rank` percentile-ranks each active
  factor cross-sectionally (`rank(axis=1, pct=True)`), equal-weight blends (require-all-present
  NaN semantics), and applies optional N-month (N×21 trading-day) smoothing. Tests:
  `tests/backtest_v2/test_v3t1_factors.py` — 15 cases, all green; factor sign/monotonicity,
  single-factor composite == pct rank, equal-weight blend, outlier-magnitude invariance (the
  rank-blend-not-z-blend guard), smoothing-reduces-churn. v2 `test_t3_signals.py` regression
  intact (32 passed). **Note for T2/T4 parity:** the v3 floor factor `mom_12_1` is RAW 12-1
  return (prereg §4), whereas v2's candidate ranks by `momentum_12_1 / vol`. So the
  *momentum-only composite* reproduces v2's *eligibility/direction* but not its exact
  vol-adjusted ordering — the T2 "reproduces v2 ranking order" / T4 parity check must be read
  against the prereg's raw-momentum definition, or `low_vol` added to recover vol-adjustment.
  Flagged, not resolved here (out of T1 scope).

---

## T2 — Composite signal store wired through the engine seam + tests

- **Status:** ☑
- **Depends on:** T1.
- **Goal:** Make the multi-factor signal runnable through the **unchanged** engine via the
  `signal_store` seam.
- **Do:**
  - Build a v3 signal store exposing the same interface the engine calls —
    `eligible_ranked(day, universe)` and `entry_gate(day, isin)` — but ranking by the T1
    composite. Reuse the v2 entry gate (`close > 200-MA AND liquidity floor`, plus the
    momentum-positive gate while momentum is active).
  - A `precompute_*` builder that computes all active factor scores once (like v2's
    `precompute_signals`) so sweeps don't recompute.
  - Unit tests: engine runs end-to-end with the composite store on a small fixture; with
    momentum-only active, ranking matches a **raw-momentum v2 reference ranker** (v2 engine
    driven by raw `momentum_12_1`, NOT `mom/vol`) — see prereg **Erratum (T1→T2)**; the
    historical vol-adjusted candidate is NOT the equality target; ledger/determinism unaffected.
- **Deliverable:** v3 signal store + builder + tests, green; an engine run on a fixture.
- **Done-criteria:**
  - [x] Engine runs with the composite store via the existing `signal_store` param — no
        engine edit required for the ranker.
  - [x] Momentum-only composite matches the **raw-momentum v2 reference** ranker exactly (test),
        per prereg Erratum (T1→T2) — not the vol-adjusted `mom/vol` candidate.
- **Session log:** 2026-06-17 — Created `backend/app/backtest_v2/signals_v3.py`: `V3SignalStore`
  exposing the exact engine seam (`entry_gate`, `eligible_ranked`) but ordering eligible names by
  the T1 `composite_rank` instead of v2's `mom/vol`. Gate inputs (close, EMA_200, momentum_12_1,
  adv_20) are reused **verbatim** from v2's `precompute_signals` via a `_gate_config` projection
  (Rule 3), so the gate is byte-identical to v2's for the floor. The absolute-momentum filter
  (`mom>0`) is applied **only while `mom_12_1` is active** (prereg Erratum) — a non-momentum
  composite must not inherit it. `precompute_v3_signals` builds it once (sweep-ready). Tests:
  `tests/backtest_v2/test_v3t2_signal_store.py` — 8 cases, all green: end-to-end engine run via
  the **unchanged** engine (`signal_store` param, no engine edit); **parity** = momentum-only floor
  ordering equals the raw-momentum v2 reference (v2 `entry_gate` + raw `momentum_12_1` order), NOT
  the `mom/vol` candidate — scores are percentiles in [0,1] (monotone transform → same order);
  floor eligibility == v2 gate on warmed-up rebalances; conditional-gate (low-vol composite admits
  a superset of the momentum gate); determinism. v2 regression intact (`test_t3_signals`,
  `test_t7_engine`, `test_v3t1_factors` — 58 passed). Both T2 done-criteria met.

---

## T3 — Engine rebalance-cadence knob (monthly / quarterly / semi-annual) + tests

- **Status:** ☑
- **Depends on:** T0 (config). Independent of T1/T2 — may run in parallel.
- **Goal:** The membership-turnover lever #1: trade less often. Surgical engine change.
- **Do:**
  - Generalize the engine's hardcoded `_month_end_dates` to honor a cadence param
    (monthly = current behavior **default**, quarterly, semi-annual). v2's `MomentumConfig`
    path must be byte-for-byte unchanged (default monthly) — v2 stays runnable.
  - Tests: quarterly cadence yields exactly the quarter-end trading days; monthly default
    unchanged (regression — Rule 1/5); no-lookahead invariant still holds.
- **Deliverable:** cadence-aware rebalance-date generator + tests, green; v2 regression intact.
- **Done-criteria:**
  - [x] Cadence param drives rebalance dates; monthly default = unchanged v2 behavior (test).
  - [x] 02 §10 invariants still pass.
- **Session log:** 2026-06-17 — Generalized the engine's hardcoded
  `_month_end_dates(calendar)` call (engine.py §3) to `_rebalance_dates(calendar,
  config.rebalance)`. New `_rebalance_dates` is a *thin filter on the untouched*
  `_month_end_dates`: a `_CADENCE_MONTHS` map gives `monthly → None` (return
  `_month_end_dates(calendar)` verbatim — so v2's MomentumConfig path is
  byte-for-byte unchanged), `quarterly → {3,6,9,12}`, `semi-annual → {6,12}`;
  unknown cadence raises `ValueError` (Rule 12). Reads the pre-existing
  `MomentumConfig.rebalance` field (T0), no config/schema change. Tests
  (`test_v3t3_cadence.py`, 8): generator — monthly == `_month_end_dates`
  byte-for-byte, quarterly/semi-annual == exact calendar quarter/half-year ends,
  strict nesting semi ⊂ quarterly ⊂ monthly (the lever trades less often, Rule 9),
  unknown-cadence fail-loud; engine — monthly default reproduces v2 scheduling
  end-to-end through `run()`, quarterly schedules only quarter-ends and strictly
  fewer of them; no-lookahead — every fill has a strictly-earlier rebalance
  decision under quarterly (02 §10 / DC2 queue discipline intact). v2 regression
  green (`test_t7_engine`, `test_t3_signals`, `test_v3t1_factors`,
  `test_v3t2_signal_store` — 74 passed total). Both done-criteria met.

---

## T4 — Parity + turnover layers on DISCOVERY (H1)

- **Status:** ☐
- **Depends on:** T2, T3.
- **Goal:** Confirm the v3 floor reproduces v2, then test whether the turnover levers cut
  realized turnover without wrecking Calmar (prereg H1).
- **Do:**
  - **Parity check first (like-for-like wiring test — see prereg Erratum T1→T2):** the v3
    floor is RAW momentum-only, so it is NOT expected to reproduce v2's vol-adjusted candidate.
    Exact target = a **raw-momentum v2 reference** (unchanged v2 engine driven by raw
    `momentum_12_1`); the v3 floor must match it to numerical tolerance — a mismatch is a wiring
    bug, fix before proceeding (Rule 12). The historical `Calmar ~0.265 / turnover ~934%` are a
    **sanity band only** (same order of magnitude, turnover ~900%), NOT an equality target.
  - Then run, one layer at a time via `iterate.py` (coarse grids, prereg §6, log to ledger):
    Layer 1 cadence {monthly, quarterly, semi-annual}; Layer 2 buffer M {35, 50, 70};
    Layer 3 smoothing {none, 2-mo, 3-mo}. Plateau-select each.
  - Report **realized** turnover (executed fills, per `diag_turnover_decomp` method), not just
    planned Σ|Δw|, plus Calmar — for each layer.
- **Deliverable:** parity confirmation + per-layer turnover/Calmar plateau verdicts in the log.
- **Done-criteria:**
  - [ ] v3 floor matches the **raw-momentum v2 reference** to tolerance (or wiring bug fixed);
        historical 0.265/934% checked as a sanity band only — per prereg Erratum (T1→T2).
  - [ ] 3 turnover layers run on DISCOVERY; plateau verdicts stated; realized turnover reported.
- **Session log:** _(fill at end)_

---

## T5 — Factor layers on DISCOVERY (H2)

- **Status:** ☐
- **Depends on:** T4 (a turnover-stable base config).
- **Goal:** Add price/volume factors one at a time on the T4 base; test whether the composite
  broadens selection (prereg H2 — §6.2 concentration).
- **Do:**
  - Add, one layer at a time (plateau, ledger): +low-vol, +trend-quality, +momentum-6-1,
    +short-term-reversal. Each holds prior-accepted knobs fixed (04 §4).
  - Track the §6.2-style top-10-drop retention as a running diagnostic (not the final gate,
    but the signal we care about) alongside Calmar.
- **Deliverable:** per-factor plateau verdicts + concentration trend in the log; the chosen
  v3 candidate config.
- **Done-criteria:**
  - [ ] Each factor added on a plateau or rejected, honestly stated.
  - [ ] A single v3 candidate config selected for robustness.
- **Session log:** _(fill at end)_

---

## T6 — Robustness battery on the v3 candidate (§6 gate)

- **Status:** ☐
- **Depends on:** T5.
- **Goal:** Subject the v3 candidate to all five §6 checks before it nears FINAL_OOS.
- **Do:** Reuse `robustness.py`'s five checks (cost stress, universe perturbation, neighborhood,
  subperiod, turnover/capacity) on the v3 candidate — adapt the candidate config, not the
  checks. **Strengthen §6.4** to a hard concentration FAIL (the v2 coded-check gap: one period
  > 5× the mean of other positive periods → FAIL), per the T4-v2 diagnosis note.
- **Deliverable:** per-check pass/fail table for the v3 candidate.
- **Done-criteria:**
  - [ ] All five §6 checks run; each explicit pass/fail (Rule 12); any fail blocks T7.
  - [ ] §6.4 concentration hardened.
- **Session log:** _(fill at end)_

---

## T7 — One-shot FINAL_OOS + Definition of Done (§7)

- **Status:** ⚠ BLOCKED until T6 passes all five checks.
- **Depends on:** T6 (all pass).
- **Goal:** Run the single pre-committed v3 candidate on `FINAL_OOS` **exactly once**; assemble
  the §9 / spec-04 §7 DoD verdict.
- **Do:** Run on FINAL_OOS once (log the trial). If it fails, it fails — no iteration. Fill the
  DoD checklist (beats Mom30 on Calmar after base costs, maxDD ≤ 70% of bench on discovery;
  holds at pessimistic + subperiods; passes one-shot OOS without re-tuning; tradeable on
  realized turnover/capacity). Report raw Sharpe, K, deflated Sharpe, PBO together.
- **Deliverable:** FINAL_OOS numbers + completed DoD checklist + one-line verdict.
- **Done-criteria:**
  - [ ] FINAL_OOS consumed exactly once (ledger shows it).
  - [ ] DoD filled item-by-item; verdict stated plainly — "validated" only if every box checks,
        else "research note" (Rule 12).
- **Session log:** _(fill at end)_

---

## Exit criteria for Track A

- [x] T0 locked (V3Config, grids, predicates, splits reused).
- [ ] T1–T3 infra green (factors, composite signal store, cadence knob) with v2 regression intact.
- [ ] T4 parity confirmed; turnover layers plateau-selected; realized turnover reported.
- [ ] T5 factor layers added one at a time; v3 candidate chosen.
- [ ] T6 robustness battery run; honest pass/fail.
- [ ] T7 FINAL_OOS consumed once; DoD verdict labeled truthfully.

> If Track A's candidate clears §6 but H3 (regime concentration) is still weak, that is the
> trigger to consider **Track B (fundamentals)** — a separate data build, separately scoped
> and approved. Track A ending as a research note is an acceptable, honest outcome (prereg §10).
