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

- **Status:** ☐ not started
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
  - [ ] The 5 fundamental factor names validate in `active_factors`; price-factor floor + all locked
        defaults + the equal-weight rule are unchanged (test asserts no locked default moved).
  - [ ] `TRACK_B_DISCOVERY` added; `validation.DISCOVERY`/`FINAL_OOS` untouched (test/diff).
  - [ ] Track-A baseline config recovered from `01`'s ledger (not invented) and recorded here.
- **Session log:** _(empty)_

---

## TBE1 — Fundamental factor library (5 factors) + composite wiring (test-gated)

- **Status:** ☐ not started
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
  - [ ] All 5 factors computed via `read_fundamentals_asof` + raw×raw; TTM + degenerate + financials
        rules match `03` §3/§4 exactly (tests encode each).
  - [ ] Composite blends fundamental ranks under mean-over-active; missing = not counted (test).
  - [ ] No raw-table read, no zero-fill, no market cap other than raw×raw (boundary test).
- **Session log:** _(empty)_

---

## TBE2 — Factor characterization on DISCOVERY (coverage + momentum orthogonality; NO returns)

- **Status:** ☐ not started
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
  - [ ] Per-factor + per-block name coverage reported across DISCOVERY rebalances.
  - [ ] Momentum rank-ρ reported per factor/block vs the |ρ|<0.3 expectation (honest, not a gate).
  - [ ] No backtest return computed; `FINAL_OOS` untouched.
- **Session log:** _(empty)_

---

## TBE3 — Track-A baseline backtest on the Track-B window (the H3 comparison anchor)

- **Status:** ☐ not started
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
  - [ ] Track-A baseline run on `TRACK_B_DISCOVERY` at base cost; logged to `ConfigLedger`.
  - [ ] §6.4 `passes_concentration_hard` evaluated + subperiod spread recorded as the H3 anchor.
  - [ ] `FINAL_OOS` untouched; numbers reported honestly (incl. if the baseline unexpectedly passes
        §6.4 — that would itself be a finding about the window, Rule 12).
- **Session log:** _(empty)_

---

## TBE4 — Layer B1: add the Value block {E/P, B/P} (plateau)

- **Status:** ☐ not started
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
  - [ ] Value block added on the fixed baseline; runs on DISCOVERY; all configs logged.
  - [ ] Accept/drop decided on a plateau + §6.4-not-worse rule (Rule 12 — report a drop honestly).
  - [ ] `FINAL_OOS` untouched.
- **Session log:** _(empty)_

---

## TBE5 — Layer B2: add the Quality block {ROE, accruals, leverage} (plateau)

- **Status:** ☐ not started
- **Depends on:** TBE4.
- **Goal:** Second H3 layer — on top of the B1-accepted config, does quality further narrow the
  §6.4 spread on a plateau?
- **Do:**
  - On the B1-accepted config (or the baseline if B1 was dropped — record which), add the **Quality
    block** (equal-blend of ROE, accruals, leverage, `03` §6 B2). Run on `TRACK_B_DISCOVERY` at base
    cost; log all configs. Accept on a plateau + §6.4-not-worse, else drop.
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
- [ ] TBE3 Track-A baseline on the Track-B window + §6.4 anchor recorded.
- [ ] TBE4–TBE6 value/quality layers added one at a time on a plateau (or dropped honestly), all
      configs logged; no threshold or grid widened.
- [ ] TBE7 single candidate selected; full §6 battery + deflation/PBO + **explicit H3 verdict**;
      go/no-go for the one-shot.
- [ ] TBE8 (only on TBE7 PASS + H3 confirmed) — `FINAL_OOS` spent **exactly once**; §9 DoD verdict.
- [ ] If TBE7 FAILs → Track B closes as a research note; `FINAL_OOS` left pristine (a legitimate,
      pre-accepted outcome — `03` §9/§10; manufacturing a pass by re-tuning is forbidden).

> This file **executes** `03_TRACK_B_PREREG.md`. It defines no new factor, grid, threshold, or
> split. The one-shot `FINAL_OOS` is consumed only at TBE8, only once, only on a locked candidate.
