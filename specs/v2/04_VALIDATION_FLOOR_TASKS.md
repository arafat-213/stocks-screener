# Spec 04 — Validation Floor & Anti-Overfit: Task Breakdown & Build Tracker

> **Purpose.** Decompose `04_VALIDATION_FLOOR.md` into small, resumable,
> session-sized tasks so no single session has to do the whole validation layer
> (too expensive in tokens — CLAUDE.md Rule 6). Each task is self-contained: a
> session loads `00_OVERVIEW.md`, `04_VALIDATION_FLOOR.md`, this file, and the
> **one task** it is doing — nothing more.
>
> **How to use this file each session:**
> 1. Read the task you are picking up (and its "Depends on").
> 2. Do only that task. Honor the per-session token budget (Rule 6).
> 3. Update the task's **Status** and fill its **Session log** at the end.
> 4. Check off the Done-criteria. Do not mark Done if anything was skipped
>    (Rule 12 — fail loud).
>
> **Status legend:** ☐ not started · ◐ in progress · ☑ done · ⚠ blocked
>
> **This spec is different from 01–03.** It is methodology + research discipline,
> not "build a layer." Two consequences:
> - There is a **hard GO/NO-GO gate after the floor (T1).** If the floor badly
>   underperforms even Nifty 50 TRI after costs, the spec says **stop and diagnose
>   the data/costs — do not tune** (`04` §2). T2–T5 do not happen in that case.
> - The back half (T3 iteration, T4 robustness) are open-ended research loops, not
>   deterministic builds. Their exact scope depends on what the floor and each
>   layer reveal. They are framed here, not fully pre-specified. **Commit firmly to
>   T0→T1; treat T2→T5 as the conditional second phase.**

---

## What this layer plugs into (already built — specs 01 + 02 + 03)

The engine, cost model, and benchmark wiring are complete and gated by tests.
Spec 04 **drives** them with discipline; it adds very little new infrastructure.

Confirmed seams (read, do **not** rewrite — `00` §5, Rule 3):

- **`engine.run(prices, config, *, index_prices, cost_level)`** — `cost_level` is
  already a first-class param: `"optimistic" | "base" | "pessimistic"` (spec 03 T4).
  The floor does not need to touch the engine to produce the three-cost report.
- **`app.backtest_v2.run_real`** — already has `_print_three_level_report(...)`,
  `_try_load_benchmark(...)`, and the `02 §10` invariant checks
  (`check_cash_conservation`, `check_determinism`, `check_no_lookahead`). The floor
  runner is a thin, pre-committed-config wrapper on top of this machinery.
- **`app.backtest_v2.benchmark`** — `load_tri(index_name, ...)`, `align_benchmark(...)`,
  and the three TRI constants `TRI_MOMENTUM_30` (primary), `TRI_MIDCAP_MOMENTUM_50`
  (secondary), `TRI_NIFTY_50` (floor). Also `load_price_index(...)` — the **real
  Nifty 50 price** series for the regime 200-DMA (spec 03 §D).
- **`app.backtest_v2.metrics`** — absolute + benchmark-relative metrics, incl.
  Calmar, max-DD ratio, IR, capture, beta (spec 03 T3). These are the pass/fail
  numbers; the floor just renders them.
- **`app.data.bhavcopy.store`** — `read_prices_adjusted(...)` over the built dataset
  (`backend/data/bhavcopy/`, ISIN-partitioned, ~2017-12 → 2025-11 on disk).

### ⚠ Load-bearing integration fact — `run_real.py` feeds the regime a *synthetic* index

`run_real.build_synthetic_index(prices)` is an equal-weighted **placeholder** the
regime overlay currently reads. `04` §2 mandates the regime overlay be ON, driven by
the **real price index 200-DMA** (`02 §8`, `03 §2.3 / §D` — Nifty 50 *price*, not
TRI). **The floor (T1) MUST swap the synthetic index for `benchmark.load_price_index`.**
A floor measured on a synthetic regime signal is not the spec's floor.

---

## Target module layout (proposed — confirm minimalism per task, Rule 2)

```
backend/app/backtest_v2/
  floor.py        # T1 — pre-committed floor config + 3-cost × 3-benchmark report + decision rule
  validation.py   # T2 — FROZEN date splits, walk-forward windows, config ledger, deflated Sharpe / PBO
  iterate.py      # T3 — one-layer coarse-grid runner on discovery only + plateau detector
  robustness.py   # T4 — cost stress, drop-top-N, neighborhood, subperiod, turnover/capacity
  # T5 reuses floor.py + validation.py for the one-shot OOS gate — no new module expected
```

These are proposals. Prefer the fewest modules that stay readable; do not create a
module until its task needs it. Keep **entirely separate** from `backend/app/backtest/`
(v1) — v1 must stay runnable.

---

## Task graph (dependencies)

```
T0 (lock decisions: data span, floor→config map, FROZEN date splits, decision thresholds, PBO method — light/no code)
   └─> T1 (THE FLOOR: pre-committed config, 3 cost levels × 3 benchmarks, real regime index, decision rule)
            │
        ╔═══╧═══════════════════════════════════════════════════════════╗
        ║  GO / NO-GO GATE (04 §2).                                      ║
        ║  Floor underperforms Nifty 50 TRI after base costs  → STOP.    ║
        ║  Diagnose data/costs. Do NOT build T2–T5, do NOT tune.        ║
        ╚═══╤═══════════════════════════════════════════════════════════╝
            │  (only if floor is sound)
            ▼
   T2 (walk-forward + OOS scaffolding: frozen split, rolling windows, config ledger, deflated Sharpe/PBO + unit tests)
            └─> T3 (controlled-iteration harness: one-layer coarse grid on discovery + plateau detector; layer 1 worked example)
                     └─> T4 (robustness checks on the chosen candidate: cost stress, drop-top-N, neighborhood, subperiod, turnover/capacity)
                              └─> T5 (FINAL one-shot OOS gate + Definition of Done — looked at exactly once)
```

T0→T1 is the committed first phase. The gate after T1 decides whether T2→T5 exist.

---

## T0 — Lock decisions: data span, config map, frozen splits, thresholds (light / no production code)

- **Status:** ☑
- **Depends on:** specs 01–03 done (they are).
- **Goal:** Pre-commit every choice that `04` says must be fixed *before* measuring,
  so no later session is tempted to move the measuring stick (the v1 failure mode,
  `04` §5/§7). Output is decisions, not a runner.
- **Do:**
  - **Usable data span.** Confirm from `store.read_prices_adjusted` the first/last
    trading date actually on disk and the count of distinct ISINs. Subtract the
    warmup: a valid `momentum_12_1` needs `i >= 273` per-ISIN trading days (`02` §3),
    so the first *decision* date is ~13 months after data start. Record the real
    usable backtest window.
  - **Floor → `MomentumConfig` map.** Write the exact field values for the `04` §2
    floor and confirm each is already the dataclass default (it should be: N=20,
    M=35, liquidity 5.0cr, EMA_200, monthly, regime ON, cat-stop 25%). Note any
    drift between `04` §2 prose and `config.py` defaults and resolve it explicitly
    (Rule 7 — surface conflicts).
  - **FREEZE the date splits as code constants** (the load-bearing T0 deliverable):
    - `DISCOVERY = (start, end)` — in-sample region for *all* §4 iteration, with
      internal walk-forward folds (`04` §5).
    - `FINAL_OOS = (start, end)` — one contiguous, recent block, looked at **exactly
      once** in T5. No overlap with discovery.
    - Recommended starting points to lock (adjust to the real usable span): discovery
      ≈ first-usable → 2023-06, final OOS ≈ 2023-07 → last-on-disk. **The floor (T1)
      itself runs on the *full* usable window** — it is pre-committed/single-config so
      it burns no OOS; the split governs only the iteration phase (T2+).
  - **Decision-rule thresholds (make `04` §2 numeric).** Define precisely what
    "roughly tracks or beats Nifty200 Momentum 30 TRI on Calmar after base costs"
    means as a computable predicate (e.g. `calmar_ratio_vs_primary >= X`), and the
    NO-GO trip ("badly underperforms even Nifty 50 TRI") as another (e.g.
    `calmar_ratio_vs_nifty50 < Y`). These feed T1's `evaluate_decision`.
  - **Anti-overfit method.** Choose how T2 will compute the **deflated Sharpe ratio**
    and **PBO** (probability of backtest overfitting) — name the method (e.g. Bailey &
    López de Prado deflated Sharpe; PBO via combinatorially-symmetric cross-validation
    / CSCV) so T2 implements a known recipe, not an ad-hoc one.
  - Throwaway probe code (a one-off `read_prices_adjusted` span check) is allowed; do
    **not** ship a module.
- **Deliverable:** a `## Locked decisions (T0)` section appended to the **top** of
  `04_VALIDATION_FLOOR.md` capturing: usable window, floor→config map (+ any drift
  resolved), the two frozen date ranges, the numeric decision predicates, and the
  chosen deflated-Sharpe/PBO method.
- **Done-criteria:**
  - [x] Real usable backtest window (post-warmup) recorded from on-disk data.
  - [x] Floor config mapped field-by-field; any prose↔default drift surfaced + resolved.
  - [x] `DISCOVERY` and `FINAL_OOS` ranges frozen as explicit values (non-overlapping).
  - [x] Decision-rule GO and NO-GO predicates stated numerically.
  - [x] Deflated-Sharpe + PBO method named with a citation.
- **Session log:**
  - 2026-06-15. Probed `store.read_prices_adjusted()`: 4,008,497 rows, 3,470 ISINs, 2017-01-02 → 2026-06-12, 2,331 trading days. Post-warmup (273 trad. days) first decision date: 2018-02-06. All `MomentumConfig` defaults match `04` §2 floor exactly — zero drift. Frozen: DISCOVERY = (2018-02-06, 2023-06-30), FINAL_OOS = (2023-07-01, 2026-06-12), non-overlapping. GO predicate: `C_strat >= 0.80 × C_primary`. NO-GO predicate: `C_strat < C_nifty50`. Anti-overfit method: Deflated Sharpe (Bailey & LdP 2016) + PBO via CSCV (Bailey & LdP 2014). Full decisions written to `## Locked decisions (T0)` section prepended to `04_VALIDATION_FLOOR.md`.

---

## T1 — THE FLOOR: pre-committed config, 3 cost levels × 3 benchmarks (the gate)

- **Status:** ☑ — **verdict: GO (marginal)** after Phase 4 re-run on rebuilt data (see session log + `04_FLOOR_DIAGNOSIS.md`)
- **Depends on:** T0.
- **Goal:** Run the single `04` §2 floor config, measured honestly, on the full
  usable window; render the `04` §2 report (three cost levels × three benchmarks);
  evaluate the T0 decision predicates and record an explicit **GO / NO-GO verdict**.
  **No tuning, no search** — exactly one config.
- **Do:**
  - Add `floor.py`: build the frozen floor `MomentumConfig` (from T0), run it via the
    existing engine + `_print_three_level_report` machinery. **Swap the synthetic
    regime index for `benchmark.load_price_index` (real Nifty 50 price)** — see the
    load-bearing fact above; without it this is not the spec's floor.
  - Render benchmark-relative metrics vs **all three** TRI series
    (`TRI_MOMENTUM_30`, `TRI_MIDCAP_MOMENTUM_50`, `TRI_NIFTY_50`) at each cost level,
    foregrounding Calmar ratio and max-DD ratio (`03` §4.5 — the pass/fail numbers).
  - Implement `evaluate_decision(...)` applying T0's GO/NO-GO predicates; print the
    verdict prominently and write it to the session log.
  - Reuse `run_real`'s `02 §10` invariant checks (cash conservation, determinism,
    no-lookahead) as a pre-flight so the floor run is trustworthy before judging it.
  - If the primary TRI is a cache miss (no network), fail loud — the floor verdict is
    meaningless without the real benchmark. Do not silently fall back to synthetic.
- **Deliverable:** `floor.py` + a written **Floor Report** (numbers at all three cost
  levels vs all three benchmarks) + the recorded GO/NO-GO verdict, in the session log.
- **Done-criteria:**
  - [x] Exactly one config run; regime fed the **real** price index, not synthetic.
  - [x] Three cost levels × three benchmarks rendered with Calmar + max-DD ratios.
  - [x] `02 §10` invariants pass for the floor run.
  - [x] GO/NO-GO verdict computed by the T0 predicates and stated plainly (Rule 12 —
        no softening a miss into "promising").
- **Session log:**
  - 2026-06-16. Built `floor.py` (single default `MomentumConfig`, window 2018-02-06 →
    2026-06-12). Swapped the synthetic regime index for the **real Nifty 50 price index
    200-DMA** (`benchmark.load_price_index`). Warmed the benchmark cache from network
    (price index + all three TRIs over 2017-01-01 → 2026-06-12); run itself is offline.
    `02 §10` invariants all **PASS** (cash conservation, determinism, no-lookahead @
    cutoff 2024-06-12). Floor report (base cost, full window): CAGR +10.74%, MaxDD 37.99%,
    Calmar 0.28, Sharpe 0.71, ann. turnover **963.6%**, time-in-cash **51.2%**.
    Calmar-ratio matrix (strat/bench):

    | Cost        | Mom30 | Mid50 | Nifty50 |
    |-------------|-------|-------|---------|
    | OPTIMISTIC  | 0.72  | 0.60  | 1.07    |
    | BASE        | 0.63  | 0.53  | 0.94    |
    | PESSIMISTIC | 0.54  | 0.46  | 0.81    |

    **VERDICT: NO-GO.** `C_strat=0.283 < C_nifty50=0.302` at base cost (NO-GO predicate
    trips before the GO test). The floor does not clear even the Nifty 50 TRI on Calmar
    after base costs, and trails the primary Mom30 TRI badly (ratio 0.63). Per the gate:
    **STOP** — diagnosis note written to `04_FLOOR_DIAGNOSIS.md`; T2–T5 NOT started; no
    tuning performed. Note (Rule 12, not softening): the miss is narrow (~6%) and is a
    *return* gap, not a drawdown gap (strat MaxDD 37.99% ≈ Nifty50 38.27%); leads for the
    diagnosis are the 963% turnover and 51% time-in-cash, both pointing at the regime
    overlay whipsawing — but diagnosing ≠ fixing, so no parameter was changed.

  - 2026-06-16 (Phase 4 re-run). §3.3 data bug confirmed and fixed (Spec 05 Phases 1–3):
    ISIN succession bridge in `adjust.py` applied ~62 previously-missed split/bonus events;
    `prices_adjusted` rebuilt (4,008,497 rows, 3,470 ISINs, full 2017-01-02 → 2026-06-12
    range). Floor re-run on rebuilt data — same pre-committed config, no parameter changed.
    All `02 §10` invariants PASS. New floor report (base cost, full window): CAGR +11.75%,
    MaxDD 38.51%, Calmar 0.305, Sharpe 0.76, ann. turnover 972.6%, time-in-cash 46.1%
    (was 51.2% — phantom split-cliff crashes had caused false catastrophic-stop exits).
    Calmar-ratio matrix (strat/bench):

    | Cost        | Mom30 | Mid50 | Nifty50 |
    |-------------|-------|-------|---------|
    | OPTIMISTIC  | 0.77  | 0.65  | 1.14    |
    | BASE        | 0.68  | 0.57  | 1.01    |
    | PESSIMISTIC | 0.59  | 0.50  | 0.88    |

    **REVISED VERDICT: GO (marginal).** `C_strat=0.305 >= C_nifty50=0.302` at base cost
    (clears the NO-GO predicate); `C_strat=0.305 < GO threshold=0.359` (trails primary,
    so marginal). The data fix added +22 bps to C_strat — enough to cross the floor.
    T2 is now authorized. Findings documented in `04_FLOOR_DIAGNOSIS.md` §1/§2/§4 and
    `05_DATA_ADJUSTMENT_REMEDIATION.md` §13.

> ╔══════════════════════════════════════════════════════════════════════════╗
> ║  GATE — read the T1 verdict before opening T2.                           ║
> ║  • NO-GO (underperforms Nifty 50 TRI after base costs): STOP. Open a      ║
> ║    diagnosis note on data/costs/universe. Do not start T2. Do not tune.   ║
> ║  • GO (tracks/beats primary on Calmar after base costs): proceed to T2.   ║
> ╚══════════════════════════════════════════════════════════════════════════╝

---

## T2 — Walk-forward & OOS scaffolding (`validation.py`) + unit tests

- **Status:** ☑ — done 2026-06-16.
- **Depends on:** T1 (GO). ✓ met.
- **Goal:** Build the honest-measurement infrastructure every iteration session needs,
  as pure, unit-tested infra with **no research conclusions** in it.
- **Do:**
  - `validation.py` exposing: the FROZEN `DISCOVERY` / `FINAL_OOS` constants (from T0);
    a **walk-forward window generator** (rolling discovery→OOS folds *within*
    discovery, `04` §5); a **config ledger** that records every config evaluated (so
    the count of trials is known for deflation, `04` §5); and a **deflated Sharpe** +
    **PBO** computation per the T0-chosen method.
  - Unit tests (Rule 9 — encode *why*): walk-forward folds never overlap and never
    touch `FINAL_OOS`; the ledger monotonically counts trials; deflated Sharpe ≤ raw
    Sharpe and decreases as trial count rises; PBO is in [0,1] and rises with
    overfit-prone inputs. Mock any data reads (Rule: no live yfinance/NSE).
  - Do **not** run any sweep here. This task ships machinery, not findings.
- **Deliverable:** `validation.py` + its test module, all green.
- **Done-criteria:**
  - [x] Frozen splits importable as constants; `FINAL_OOS` provably untouched by
        walk-forward folds (test).
  - [x] Config ledger counts trials; used by deflation.
  - [x] Deflated Sharpe + PBO implemented to the named method, with tests on their
        defining properties.
- **Session log:**
  - 2026-06-16. Built `validation.py` (183 lines): FROZEN `DISCOVERY`/`FINAL_OOS`
    constants; `walk_forward_windows` (expanding-IS, 6-month OOS steps, all folds
    within DISCOVERY — 6 folds on default params); `ConfigLedger` (1-indexed monotonic
    trial counter, config + metadata storage); `deflated_sharpe` (Bailey & LdP 2016 —
    DSR = SR − E[max_SR_null(K, T)], non-normality corrected, K=1 returns raw SR);
    `pbo_cscv` (Bailey & LdP 2014 — all C(T, T//2) IS/OOS partitions, omega < 0.5 →
    overfit, PBO = overfit fraction). Unit tests: 33 tests, all green, fully offline.
    Key invariants tested: no fold touches FINAL_OOS; IS always ⊂ DISCOVERY; ledger
    ids monotonic; DSR ≤ raw SR and decreases with K; PBO ∈ [0,1]; consistent IS winner
    → PBO ≈ 0; random noise → PBO ≈ 0.5.

---

## T3 — Controlled-iteration harness (`iterate.py`) + plateau detector + layer 1

- **Status:** ☑ — done 2026-06-16.
- **Depends on:** T2. ✓ met.
- **Goal:** Provide the one-layer-at-a-time, coarse-grid, plateau-based iteration
  machinery (`04` §4), and demonstrate it on the first candidate layer only.
- **Do:**
  - `iterate.py`: run a **coarse** grid over **one** layer while holding all other
    knobs at floor values, **on `DISCOVERY` only**, logging every config to the T2
    ledger. No 1700-combo sweeps (`04` §4 — coarse grids only).
  - **Plateau detector** (the cheapest overfit defense, `04` §4): accept a parameter
    only if a *contiguous neighborhood* performs similarly; reject lone spiky optima.
    This is the core reusable primitive.
  - Run **layer 1 only — regime-overlay calibration** (debounce days, risk-off floor;
    `04` §4 priority 1) as the worked example. Report whether a plateau exists.
  - Layers 2–5 (ranker variant, rebalance cadence, N/M, liquidity floor) are
    **subsequent uses** of this harness, not pre-planned sessions — each is a short
    follow-up run logged to the ledger. Do not build them all now (Rule 2).
- **Deliverable:** `iterate.py` + plateau detector + the layer-1 (regime) result with
  a plateau verdict, in the session log.
- **Done-criteria:**
  - [x] Harness runs a coarse single-layer grid on `DISCOVERY` only; every config hits
        the ledger.
  - [x] Plateau detector implemented + unit-tested (spiky optimum rejected).
  - [x] Layer 1 (regime) run; plateau present/absent stated honestly.
- **Session log:**
  - 2026-06-16. Built `iterate.py` (plateau detector + `run_regime_layer` + `__main__`).
    Unit tests: 25 tests, all green, fully offline. Key invariants: spiky optimum
    rejected; flat plateau accepted; 2-D interior/corner/spike cases; DISCOVERY bounds
    pinned on every engine call; FINAL_OOS never touched; signals precomputed once;
    ledger counts every combo; each combo gets a distinct `RegimeConfig`.

    **Layer 1 run — regime-overlay calibration** on DISCOVERY (2018-02-06 → 2023-06-30)
    at base cost. Grid: `debounce_days` × `risk_off_floor` = 7 × 3 = **21 combos**
    (all logged to ledger, K=21).

    Full Calmar grid (strat Calmar on DISCOVERY):

    | debounce \ risk_off | 0.00  | 0.25  | 0.50  |
    |---------------------|-------|-------|-------|
    | 1                   | 0.246 | **0.265** | 0.261 |
    | 3 (floor default)   | 0.221 | 0.231 | 0.247 |
    | 5                   | 0.024 | 0.063 | 0.128 |
    | 7                   | 0.043 | 0.089 | 0.148 |
    | 10                  | 0.040 | 0.074 | 0.139 |
    | 15                  | 0.021 | 0.061 | 0.126 |
    | 20                  | 0.010 | 0.056 | 0.122 |

    **PLATEAU VERDICT: PLATEAU (04 §4 ACCEPTED).** Winner: `{debounce_days=1,
    risk_off_floor=0.25}` calmar=0.265. All 3 immediate neighbors ≥ 85% × 0.265 =
    0.225: (debounce=3, rof=0.25)=0.231 ✓, (debounce=1, rof=0.0)=0.246 ✓,
    (debounce=1, rof=0.50)=0.261 ✓. Winner vs floor config: +19.8% calmar.

    Structural note (not tuning — observation): debounce ≥ 5 with risk_off=0.0 is a
    "death valley" (calmars 0.010–0.043). The 2020 COVID V-shape recovery devastated
    high-debounce + full-cash configs: go to cash slowly, wait 5–20 consecutive days
    above DMA before returning → miss the entire recovery. debounce=1 is more responsive
    but also more whipsaw-prone; the 25% risk_off floor cushions whipsaws while keeping
    25% of equity deployed in risk-off, catching V-shaped bounces.

    **Accepted candidate:** `RegimeConfig(debounce_days=1, risk_off_floor=0.25)`.
    Proceed to T4 robustness checks with this config + floor MomentumConfig.

---

## T4 — Robustness checks (`robustness.py`) on the chosen candidate

- **Status:** ☑ — done 2026-06-16.
- **Depends on:** T3 (a candidate config exists). ✓ met.
- **Goal:** Subject the chosen candidate to every `04` §6 survival check before it is
  allowed near the final OOS block.
- **Do:** implement and run, on the candidate:
  - **Cost stress** — still beats benchmark Calmar at the **pessimistic** level (§6.1).
  - **Universe perturbation** — drop the top-10 contributing names; does the edge
    persist? Cross-check those names' adjusted data for glitches (§6.2).
  - **Parameter neighborhood** — reuse the T3 plateau check (§6.3).
  - **Subperiod stability** — positive-ish across bull / bear / chop subperiods, not
    one regime carrying everything (the explicit v1 trap — 2021 bull) (§6.4).
  - **Turnover / capacity** — annualized turnover + average participation vs ADV
    within tradeable limits at the intended capital (§6.5).
- **Deliverable:** `robustness.py` + a per-check pass/fail table for the candidate.
- **Done-criteria:**
  - [x] All five §6 checks implemented and run on the candidate.
  - [x] Each reported as explicit pass/fail (Rule 12); a failure blocks T5.
- **Session log:**
  - 2026-06-16. Built `robustness.py` (5 check functions + `main`) and
    `test_s04t4_robustness.py` (36 tests, all green, fully offline).
    Candidate: `RegimeConfig(debounce_days=1, risk_off_floor=0.25)` + floor
    `MomentumConfig` defaults, DISCOVERY window.

  - 2026-06-16 (live run). Ran `venv/bin/python -m app.backtest_v2.robustness`
    on rebuilt prices_adjusted (4,008,497 rows, 3,470 ISINs). Base calmar on
    DISCOVERY = 0.265, sharpe = 0.651, cagr = 10.05%, maxdd = 37.96%,
    turnover = 934%. Total ledger trials K = 12.

    **Per-check results:**

    | Check | Verdict | Key numbers |
    |---|---|---|
    | §6.1 Cost stress (pessimistic) | **FAIL** | calmar_ratio **0.65** < 1.0; C_strat=0.226, C_nifty50=0.346 |
    | §6.2 Universe perturbation (drop top-10 P&L) | **FAIL** | Calmar retention **41%** < 70%; base=0.265 → perturbed=0.108 |
    | §6.3 Parameter neighborhood | **PASS** | Plateau — min neighbor calmar 0.231 ≥ 85% × 0.265 = 0.225 |
    | §6.4 Subperiod stability | **PASS** | 2/3 positive Calmar (⚠ see note below) |
    | §6.5 Turnover / capacity | **PASS** | participation 0.031% << 5% at ₹10L |

    **>>> T4 OVERALL VERDICT: FAIL — T5 is blocked. <<<**

    3/5 checks pass; 2/5 fail. Per spec 04 §6 and the task done-criteria: a
    failure blocks T5. Do not open T5. Do not run the final OOS block. (Rule 12 —
    the FINAL_OOS block must stay pristine for any future attempt.)

    ---

    **Diagnosis of failures (observation only — no parameter was changed):**

    **§6.1 FAIL — cost fragility.** At pessimistic costs, C_strat collapses from
    0.265 to 0.226 while C_nifty50 stays at 0.346. The 10.05% CAGR at base costs
    leaves too little margin; after the pessimistic slippage + brokerage uplift,
    the net edge is gone. The ~934% annualized turnover amplifies cost drag — each
    monthly rebalance runs up a meaningful cost bill, and at pessimistic rates the
    total drag swamps the alpha.

    **§6.2 FAIL — name concentration.** Dropping only 10 names (TANLA, CGPOWER,
    ADANIGREEN, BORORENEW, DEEPAKNTR, BALAMINES, INDIAMART, GREENPANEL, POONAWALLA,
    NAVINFLUOR) out of 3,470 ISINs cuts Calmar from 0.265 to 0.108 — a 59% collapse.
    These are all outsized post-COVID momentum stories (2020–2022). The strategy's
    apparent edge on DISCOVERY is not broad-based momentum but a concentrated bet on
    the top decile of that specific bull cycle. This is structurally similar to v1's
    2021-bull dependency, just at name level rather than period level.

    **§6.4 ⚠ PASS (but a concentration red flag).** The coded criterion (2/3 positive
    Calmar) was met, but the distribution exposes the same single-regime problem the
    spec warns about:

    | Subperiod | CAGR | Calmar |
    |---|---|---|
    | Pre-COVID chop (2018-02-06 → 2020-03-31) | **−18.68%** | **−0.492** |
    | Post-COVID bull (2020-04-01 → 2022-01-31) | **+66.87%** | **+7.678** |
    | Rate-hike correction (2022-02-01 → 2023-06-30) | +4.72% | +0.171 |

    The post-COVID bull (calmar 7.678) is carrying the entire DISCOVERY result. The
    pre-COVID chop (calmar −0.492) is deeply negative. This IS the "one regime
    carrying everything" pattern that §6.4 exists to detect. The count-only criterion
    in `robustness.py` did not catch it because 2/3 periods are nominally positive —
    a known limitation of the coded check (see: §6.4 implementation note in
    `robustness.py`). If the spec's concentration criterion had been hard-coded as a
    FAIL (post-COVID Calmar > 5× mean of other positive periods), §6.4 would have
    failed too.

    **Root cause summary:** The DISCOVERY window is dominated by the 2020–2022
    post-COVID momentum bull. The strategy captures that regime well (debounce=1
    stays nimble on the V-shaped recovery) but performs poorly in the sideways/bear
    preceding it and is fragile to costs. The "edge" at DISCOVERY level is real in
    a bull momentum regime and is illusory otherwise.

    **Next steps (not pre-committed — Arafat to decide):**
    - Option A: Iterate to layer 2 (ranker variant) or layer 3 (rebalance cadence)
      using T3's harness, to see if a different ranker/cadence survives §6.1/§6.2.
    - Option B: Accept this as a research note ("momentum strategy works in post-COVID
      bull; fragile otherwise") and close spec 04 without a validated config.
    - Option C: Revisit the DISCOVERY window definition — the 2018–2020 period is
      structurally dominated by mid/smallcap drawdown (IL&FS crisis), which is a
      genuine market regime but perhaps overly penalizes the strategy pre-COVID.
    - **Do NOT move the FINAL_OOS boundary or tune against T4 results.** (Rule 12)

---

## T5 — Final one-shot OOS gate + Definition of Done (`04` §7)

- **Status:** ⚠ BLOCKED — T4 failed (§6.1 cost stress + §6.2 universe perturbation). FINAL_OOS must not be touched until a candidate clears all five T4 checks. Do not run T5.
- **Depends on:** T4 (all robustness checks pass).
- **Goal:** Run the **single, pre-committed** config on the FROZEN `FINAL_OOS` block
  **exactly once**, and assemble the validated / not-validated verdict per `04` §7.
- **Do:**
  - Run the candidate on `FINAL_OOS` once. **If it fails, it fails — do not iterate
    against it** (`04` §5). Record the trial in the ledger.
  - Assemble the §7 Definition-of-Done checklist: beats Nifty200 Momentum 30 TRI on
    Calmar after **base** costs with **max DD ≤ 70%** of benchmark on discovery; holds
    at **pessimistic** costs and across subperiods; passes the one-shot OOS without
    re-tuning; tradeable on turnover/capacity.
  - Write the honest verdict — "validated strategy" only if every box is checked;
    otherwise "research note," reported without softening (Rule 12).
- **Deliverable:** the final OOS numbers + the completed §7 DoD checklist + the
  one-line verdict, in the session log.
- **Done-criteria:**
  - [ ] `FINAL_OOS` consumed exactly once for the chosen config (ledger shows it).
  - [ ] §7 checklist filled item-by-item.
  - [ ] Verdict stated plainly; a miss is reported as a miss.
- **Session log:**
  - _(fill at end of session)_

---

## Exit criteria for the whole Validation layer (spec 04 complete)

- [x] T0 decisions locked (window, floor→config map, frozen splits, predicates, PBO method).
- [x] T1 floor run honestly; GO/NO-GO verdict recorded → **NO-GO** (original, 2026-06-16)
      → **GO (marginal)** (Phase 4 re-run on rebuilt data, 2026-06-16). §3.3 data bug
      fixed (Spec 05); floor re-run on same pre-committed config confirmed the data fix
      was the legitimate trigger. C_strat 0.305 > C_nifty50 0.302 at base costs.
- [x] **If NO-GO:** diagnosis note written (`04_FLOOR_DIAGNOSIS.md`); spec 04 paused at
      gate; data bug identified (Spec 05) and fixed; floor re-run returned GO (marginal).
      This is resolved — the valid terminal NO-GO state was superseded by the data fix.
- [x] **If GO:** T2 scaffolding green (2026-06-16 — 33 tests, all pass); T3 iteration
      ran one layer at a time on discovery with plateau-based selection (2026-06-16 —
      25 tests green; layer 1 regime grid PLATEAU, winner debounce=1/rof=0.25 calmar=0.265);
      T4 robustness run (2026-06-16): **FAIL on §6.1 and §6.2** (3/5 pass). T5 blocked.
      FINAL_OOS has not been touched. See T4 session log for full diagnosis and next-step options.
- [ ] Final artifact is labeled truthfully: "validated, deployable config" only if §7
      is fully satisfied; otherwise "research note" (Rule 12 — fail loud). No softening.

  **Current state (2026-06-16): research note.** The candidate (layer-1 regime config)
  does not clear T4. It is NOT a validated, deployable strategy. The DISCOVERY result
  (calmar 0.265 at base cost) is a real measurement on real data with the pre-committed
  config, but it is fragile to costs (§6.1) and concentrated in ~10 post-COVID momentum
  names (§6.2). Labeling it anything other than "research note" would violate Rule 12.

> Reminder for every session in this spec: the entire point of v2 was honest
> measurement. The frozen splits, the one-shot OOS, the plateau rule, the trial
> ledger, and the deflated Sharpe all exist to stop us from re-running v1's mistake
> of optimizing a biased harness. Do not move a frozen boundary to make a config pass.
