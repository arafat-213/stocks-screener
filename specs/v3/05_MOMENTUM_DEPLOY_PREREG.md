# v3 / 05 — Momentum Deployment Pre-Registration: turnover-reduction search → one-shot FINAL_OOS

> **Status: LOCKED 2026-06-19 — Arafat approved the grid, levels, and acceptance rule.**
> This re-opens Track-A construction under a **new, narrower objective** (cost survival, not base
> Calmar) — the "future approved change" that `01_TRACK_A_TASKS.md` T7 said FINAL_OOS would only
> open on. **Nothing here has been run.** No config in §4 has been measured. `FINAL_OOS`
> (2023-07-01 → 2026-06-12) remains **pristine and unconsumed**.
>
> **This file is a commitment, not a task list.** It fixes the held-constant construction, the
> coarse turnover grid, the demotion of §6.4, the binding acceptance rule, and the one-shot OOS
> protocol — *before* any number is measured. Moving any stick after seeing a result (a new lever
> level, a loosened threshold, a re-touched OOS) is the v1 sin and is forbidden (`00` §1).

---

## 0. Why this prereg exists (the honest restart)

Track A closed as a research note (`01` T6, 2026-06-17): on its **canonical full DISCOVERY window
(2018-02-06 → 2023-06-30)** the pinned candidate `TRACK_A_BASELINE` **failed 4 of 5 §6 checks** —

| Check | Verdict | Detail (full-window DISCOVERY, base Calmar 0.396 / turnover ~956%) |
|---|---|---|
| §6.1 Cost stress | **FAIL** | calmar_ratio 0.94 < 1.0 — C_strat 0.326 vs C_nifty50 0.346 at pessimistic cost |
| §6.2 Universe perturbation | **FAIL** | retention 32% < 70% — edge in a handful of top names |
| §6.3 Parameter neighborhood | **FAIL** | lone spike — M=50→0.309, smoothing=2→0.276 (both < 85%×0.396) |
| §6.4 Subperiod concentration | **FAIL** | single-regime (post-COVID bull Calmar ≫ 5× others) |
| §6.5 Turnover / capacity | PASS | participation tiny vs ADV |

Two facts reframe the restart:

1. **The strong numbers were window-luck.** On the 2020-start Track-B window the *same* config
   posts Calmar 1.59 / 2.69× benchmark — but only because that window omits the 2018–19 mid-cap /
   NBFC bear it cannot handle. The honest window (2018 start) is Calmar **0.396**. We commit to the
   **honest full window** for all search and selection here.
2. **§6.4 is window-fragile** (TBE3 finding, `04`): the baseline *fails* §6.4 on the 2018 window and
   *passes* it on the 2020 window — the same engine, opposite verdict, on an arbitrary start date.
   A robustness gate that flips on the start date is a noisy proxy. We **demote §6.4 to a reported
   diagnostic** (§2) — an evidence-based decision, not a convenience to rescue a result.

**The disease is turnover.** ~956% annual turnover × realistic cost is what trips §6.1, and a
too-twitchy ranker is also prone to the §6.3 spike. T4 already optimized **base** Calmar and landed
on that spike. **This prereg optimizes a different objective — pessimistic-cost survival on a
plateau — and asks one question:** *is there a lower-turnover momentum config that survives realistic
costs and is robust (not a spike) on the honest window?* If yes, it earns the one-shot OOS. If no,
momentum-only is a research note and `FINAL_OOS` stays pristine.

---

## 1. Scope discipline (inherits `00` §1 — restated)

- ❌ No new factor. The factor set is **frozen** at the Track-A five (§3). This is a *construction*
  search (turnover levers), not a factor search.
- ❌ No fine grid. The grid is the **12 coarse points** in §4 — fully enumerated, decided now. No
  interpolation, no "one more level," no per-lever fishing after seeing Stage 1.
- ❌ No weight tuning. `factor_weights = None` (equal-weight) untouched (`00` §11 item 3).
- ❌ No moved boundary. `validation.DISCOVERY` / `validation.FINAL_OOS` are reused **unchanged**.
- ❌ No FINAL_OOS peek before the single locked candidate is chosen (§8). `walk_forward_windows`
  hard-bounds folds inside DISCOVERY — keep it that way.
- ✅ Every config evaluated is logged to the v2 `ConfigLedger`; K feeds the deflated Sharpe (§7).

---

## 2. The §6.4 demotion (explicit, evidence-based)

**§6.4 hardened-concentration is demoted from a hard gate to a reported diagnostic for this prereg.**

- **Justification (binding, on the record):** TBE3 (`04`) showed `passes_concentration_hard` returns
  opposite verdicts for the identical config depending solely on the DISCOVERY start date (FAIL on
  2018 start, PASS on 2020 start). A gate whose verdict is determined by an arbitrary window boundary
  is not cleanly measuring single-regime dependence; it is too noisy to *block* deployment.
- **What we still do:** §6.4's subperiod Calmar profile and spread ratio are **computed and reported**
  for every candidate (Rule 12 — the regime-concentration risk is real and disclosed). It simply does
  **not** gate accept/reject. Arafat has explicitly accepted that some regimes may earn more than
  others, provided the deployment bar (§9) holds.
- **What this is NOT:** this is not a softening of §6.1/§6.2/§6.3/§6.5 — those remain **hard gates**
  (§5). The demotion is surgical to §6.4 and justified by its measured window-fragility, decided
  **before** any config in §4 is run.

---

## 3. Held-constant construction (frozen for the whole search)

Everything except the three §4 turnover levers is pinned to `TRACK_A_BASELINE`:

- `active_factors = ["mom_12_1", "low_vol", "trend_quality", "mom_6_1", "reversal"]` (equal-weight)
- `target_positions N = 20` (locked default; **not** a search lever)
- `use_regime_overlay = True`, `catastrophic_stop_pct = 25.0` (retained as-is)
- `liquidity_floor_cr = 5.0` (decision-date ADV floor)
- **Window:** full `validation.DISCOVERY = (2018-02-06, 2023-06-30)` for all search + selection.
- **Benchmark (deployment bar, §9):** Nifty200 Momentum 30 TRI.
- **Costs:** "base" and "pessimistic" cost models as defined in `robustness.check_cost_stress`
  (§6.1) — reused unchanged. (§6.1's internal cost-stress reference is Nifty50, per `01` T6; the §9
  deployment Calmar comparison is vs Nifty200 Momentum 30 TRI — keep the two benchmarks distinct.)

---

## 4. The search grid (12 coarse points, two-stage)

Three turnover levers (semantics confirmed from `V3Config`):

| Lever | Direction | Levels |
|---|---|---|
| `sell_rank_buffer` M (sell when composite rank > M; N=20) | wider band → hold longer → less churn | **{70, 130, 200}** |
| `rank_smoothing_months` (N-month avg rank) | smoother → fewer whipsaws | **{0, 3}** |
| `rebalance_cadence` | rebalance less often | **{monthly, quarterly}** |

3 × 2 × 2 = **12 configs**, fully enumerated. `semi-annual` cadence is excluded (momentum decays too
fast); N is fixed at 20 (§3). The current baseline (M=70 / smoothing=0 / monthly) is one of the 12
and is the already-known failing anchor (base Calmar 0.396, fails §6.1/§6.2/§6.3).

**Stage 1 (all 12 — cheap screen):** run each on full DISCOVERY at **base + pessimistic** cost.
Record per config: realized turnover, base Calmar, base maxDD, **§6.1 pessimistic-cost Calmar ratio**.
Log all 12 to `ConfigLedger`.

**Stage 2 (only configs clearing §6.1 ≥ 1.0):** run §6.2 universe-perturbation, §6.3 neighborhood,
§6.5 turnover/capacity, and §6.4 **as diagnostic only**. Apply §5.

---

## 5. Pre-committed acceptance rule (binding — decided before any run)

A config becomes the **single locked OOS candidate** iff **all** hold on full DISCOVERY:

1. **§6.1** pessimistic-cost Calmar ratio **≥ 1.0** (survives realistic costs) — the check that killed
   the baseline;
2. **§6.2** top-10-drop retention **≥ 70%** (edge not concentrated in a few names);
3. **§6.3 plateau:** the config **and both lever-neighbors** (±1 grid step on each lever that exists in
   the grid) stay **≥ 85%** of the config's base Calmar — a *region*, not a spike;
4. **deployment bar:** beats **Nifty200 Momentum 30 TRI** on **base-cost** Calmar with **maxDD ≤ 70%**
   of benchmark;
5. **§6.4** reported, **not** gating.

**Tie-break:** if ≥ 2 configs satisfy 1–4 on a plateau, pick the **lowest realized-turnover** one
(lowest cost drag + most tradeable).

**Null outcome (a legitimate, pre-accepted close):** if **0** configs satisfy 1–4, momentum-only is
reported as a **research note** — `FINAL_OOS` stays pristine, the OOS run (§8) is **not** performed.
A null result is the honest finding that no lower-turnover momentum config in this universe survives
realistic costs robustly; it is not a prompt to add a lever level or loosen a threshold (`00` §1).

---

## 6. Robustness battery (which checks gate)

Reuse `robustness.py` unchanged. For the Stage-2 survivors:

- **§6.1** `check_cost_stress` — **HARD GATE** (rule 1).
- **§6.2** `check_universe_perturbation` / `passes_top10_retention` — **HARD GATE** (rule 2).
- **§6.3** `check_neighborhood` — **HARD GATE**, applied as the plateau rule (rule 3). Neighbors are
  the adjacent grid points already in §4 (no new configs invented for the neighborhood test).
- **§6.4** `check_subperiod_stability` / `passes_concentration_hard` — **DIAGNOSTIC ONLY** (§2).
- **§6.5** `check_turnover_capacity` — reported; expected PASS (it passed even at 956%).

---

## 7. Deflation & K accounting (honest search cost)

- Every config in §4 (all 12) is logged to the v2 `ConfigLedger`. The cumulative **K** at OOS =
  Track-A trials (T1–T6) **+** TBE3 entries **+** these 12. A fresh objective does **not** reset K —
  the read is taken from the ledger at OOS time, not assumed here.
- At the OOS step (§8), report **raw Sharpe, K, deflated Sharpe** together (`validation.deflated_sharpe`),
  plus **PBO** via `pbo_cscv` on `walk_forward_windows` over DISCOVERY (2–3 expanding folds; **no fold
  reaches FINAL_OOS**).

---

## 8. Splits & the one-shot protocol

- **DISCOVERY** = `validation.DISCOVERY (2018-02-06 → 2023-06-30)` — all of §4/§5/§6/§7 lives here.
- **FINAL_OOS** = `validation.FINAL_OOS (2023-07-01 → 2026-06-12)` — touched **exactly once**, only
  after a single candidate is locked by §5, and **never** if §5 yields the null outcome.
- The OOS run is the **byte-for-byte** locked candidate through `engine.run` on FINAL_OOS — **once, no
  re-tuning**. If it fails the §9 bar, it fails (Rule 12); that is the result, not a prompt to iterate.
  Mark `FINAL_OOS` consumed.

---

## 9. Definition of Done (the deployment bar — your stated criteria)

The candidate is **"validated, deployable"** only if the single locked config:

- Beats **Nifty200 Momentum 30 TRI** on **Calmar** after **base** costs on FINAL_OOS, with
  **max DD ≤ 70%** of benchmark; AND
- Holds §6.1 / §6.2 / §6.3 / §6.5 out-of-sample (the four hard gates do not collapse on OOS); AND
- Is tradeable on realized turnover/capacity; AND
- Raw + deflated Sharpe reported together (§7).

§6.4 is reported OOS as a diagnostic, not a gate (§2). Anything less than the above is a **research
note** (Rule 12) — no softening of the four hard gates to manufacture a pass.

---

## 10. What this prereg does NOT do (guards)

- It does **not** add a factor, tune weights, or change N / regime overlay / liquidity floor (§3).
- It does **not** add a lever level or a finer grid beyond the 12 points in §4.
- It does **not** move `validation.DISCOVERY` / `validation.FINAL_OOS`.
- It does **not** re-open the Track-B §6 **data** gate (closed, PASS) or touch fundamentals — this is
  momentum-only.
- It does **not** soften §6.1/§6.2/§6.3/§6.5; the only demotion is §6.4, justified in §2.
- It does **not** touch `FINAL_OOS` until a single DISCOVERY-locked candidate exists, and not at all on
  the null outcome.

---

## 11. Locked commitments (Arafat, 2026-06-19)

1. Grid = the **12 coarse points** in §4 (M ∈ {70,130,200} × smoothing ∈ {0,3} × cadence ∈
   {monthly,quarterly}); no level added or removed after seeing results.
2. Objective = **§6.1 cost survival on a §6.3 plateau**, not base Calmar.
3. Acceptance rule = §5 items 1–5, with the lowest-turnover tie-break and the pre-accepted null close.
4. **§6.4 demoted to diagnostic** (§2); §6.1/§6.2/§6.3/§6.5 remain hard gates.
5. Held-constant construction = §3; all search on the **full** DISCOVERY window.
6. `FINAL_OOS` spent **exactly once**, only on a §5-locked candidate, under §8/§9; pristine otherwise.

> **Signed:** Arafat — 2026-06-19 (grid + acceptance rule approved).

---

## Execution (cold-session runnable — DISCOVERY only until a candidate is locked)

> Read this file + the one stage you are doing. Honor the token budget (Rule 6). Update Status,
> fill a Session log, check off Done-criteria. Do not mark Done if anything was skipped (Rule 12).

### MD1 — Stage 1: 12-config cost screen (base + pessimistic) on full DISCOVERY

- **Status:** ✅ DONE 2026-06-19
- **Goal:** measure all 12 §4 configs on `validation.DISCOVERY`; produce the §6.1 cost-survival table.
- **Do:** build each config from `TRACK_A_BASELINE` overriding only (M, smoothing, cadence); run
  `engine.run` at base cost + `robustness.check_cost_stress` (pessimistic). Record turnover, base
  Calmar, base maxDD, §6.1 cost ratio. Log all 12 to `ConfigLedger`. **No FINAL_OOS, no §6.2/3/4.**
- **Deliverable:** a 12-row table (config → turnover, base Calmar, maxDD, §6.1 ratio, pass/fail §6.1)
  in this Session log; the list of configs that cleared §6.1 ≥ 1.0 (the Stage-2 set).
- **Done-criteria:**
  - [x] All 12 configs run on full DISCOVERY; base + pessimistic recorded; all logged to `ConfigLedger`.
  - [x] §6.1-clearing set identified explicitly (may be empty — report honestly, Rule 12).
  - [x] `FINAL_OOS` untouched.
- **Session log (2026-06-19):**

  Script: `backend/app/backtest_v2/md1_cost_screen.py`
  Window: DISCOVERY 2018-02-06 → 2023-06-30 | Held constant: 5-factor set, N=20, regime ON, liq floor 5cr
  C_nifty50 (pessimistic cost, full DISCOVERY) = **0.346** (same for all rows — benchmark is fixed)

  | Config | Base Calmar | MaxDD | Turnover% | C_strat (pess) | C_nifty50 | Ratio | §6.1 |
  |---|---|---|---|---|---|---|---|
  | M=70  sm=0 monthly    | 0.396 | 28.7% |  956 | 0.326 | 0.346 | 0.94 | **FAIL** |
  | M=70  sm=0 quarterly  | 0.147 | 28.3% |  383 | 0.124 | 0.346 | 0.36 | FAIL |
  | M=70  sm=3 monthly    | 0.304 | 29.4% |  680 | 0.262 | 0.346 | 0.76 | FAIL |
  | M=70  sm=3 quarterly  | 0.158 | 25.9% |  335 | 0.138 | 0.346 | 0.40 | FAIL |
  | M=130 sm=0 monthly    | 0.523 | 26.1% |  706 | 0.468 | 0.346 | 1.35 | **PASS** |
  | M=130 sm=0 quarterly  | 0.115 | 28.9% |  331 | 0.096 | 0.346 | 0.28 | FAIL |
  | M=130 sm=3 monthly    | 0.272 | 31.4% |  622 | 0.237 | 0.346 | 0.68 | FAIL |
  | M=130 sm=3 quarterly  | 0.166 | 28.5% |  287 | 0.142 | 0.346 | 0.41 | FAIL |
  | M=200 sm=0 monthly    | 0.550 | 27.2% |  617 | 0.502 | 0.346 | 1.45 | **PASS** |
  | M=200 sm=0 quarterly  | 0.061 | 30.4% |  303 | 0.044 | 0.346 | 0.13 | FAIL |
  | M=200 sm=3 monthly    | 0.187 | 31.4% |  568 | 0.154 | 0.346 | 0.45 | FAIL |
  | M=200 sm=3 quarterly  | 0.086 | 26.9% |  280 | 0.062 | 0.346 | 0.18 | FAIL |

  **ConfigLedger K this run: 24** (2 runs × 12 configs — base + pessimistic each)

  **Structural findings (diagnostic, no stick moved):**
  - Smoothing (sm=3) universally hurt: every smoothed config fails §6.1 regardless of M or cadence.
  - Quarterly cadence universally collapsed Calmar — consistent with the T4 L1 rejection finding.
  - Wider M (hold longer) improved base Calmar and §6.1 survival when combined with monthly cadence.
  - The anchor baseline (M=70 sm=0 monthly) reproduces T6 Calmar 0.396 exactly — no wiring drift.

  **§6.1 survivors → Stage-2 set (MD2): 2 configs**
  1. **M=130, sm=0, monthly** — base Calmar 0.523, 706% turnover, ratio 1.35
  2. **M=200, sm=0, monthly** — base Calmar 0.550, 617% turnover, ratio 1.45

### MD2 — Stage 2: full battery + §5 acceptance on the §6.1 survivors

- **Status:** ✅ DONE 2026-06-19
- **Depends on:** MD1.
- **Goal:** apply §6.2/§6.3/§6.5 (+ §6.4 diagnostic) and the §5 rule to the Stage-1 survivors; lock the
  single candidate or declare the null close.
- **Do:** for each survivor run `check_universe_perturbation`, `check_neighborhood` (plateau via the
  §4 grid neighbors), `check_turnover_capacity`, and `check_subperiod_stability` (report-only). Apply
  §5 items 1–5 + tie-break. **No FINAL_OOS.**
- **Deliverable:** per-survivor §6 table + the §5 verdict — either the single locked candidate config
  (byte-for-byte) **or** "null outcome → research note; FINAL_OOS pristine."
- **Done-criteria:**
  - [x] §6.2/§6.3/§6.5 reported per survivor; §6.4 reported as diagnostic (not gating).
  - [x] §5 applied; exactly one candidate locked OR null close declared (Rule 12 — no silent pick).
  - [x] `FINAL_OOS` untouched.
- **Session log (2026-06-19):**

  Script: `backend/app/backtest_v2/md2_battery.py`
  Window: DISCOVERY 2018-02-06 → 2023-06-30 | §6.4 benchmark: Nifty200 Momentum 30 TRI

  **§6.3 note:** neighborhood plateau reuses MD1 base Calmar table (no re-run; those K entries already
  logged in MD1). §6.4 deployment bar benchmark = Nifty200 Momentum 30 TRI (base cost). Nifty50 TRI
  was the §6.1 benchmark in MD1; the deployment bar is the primary benchmark per §3/§9.

  #### Config: M=130 sm=0 monthly (base Calmar 0.523, turnover 706%)

  | Check | Verdict | Detail |
  |---|---|---|
  | §6.2 Universe perturbation | **FAIL** | perturbed calmar=0.225, retention=43% (threshold ≥70%) |
  | §6.3 Neighborhood plateau | **FAIL** | 3/4 neighbors below 0.4446 (85%×0.523): M=70→0.396, sm=3→0.272, quarterly→0.115 |
  | §6.4 Subperiod (DIAGNOSTIC) | — | Pre-COVID chop −0.140 / Post-COVID bull +5.789 / Rate-hike correction +0.207; concentration_hard=FAIL |
  | §6.5 Turnover/capacity | PASS | participation 0.030% < 5% ADV floor |
  | §5-4 Deployment bar | **FAIL** | C_strat=0.523 > C_bench=0.473 (calmar ok) but maxDD ratio=0.77 > 0.70 |
  | **§5 VERDICT** | **FAIL** | Failed gates: §6.2, §6.3, deployment bar |

  Dropped names (§6.2): CGPOWER, ADANIGREEN, TATAELXSI, PERSISTENT, APOLLOHOSP, KPITTECH, JSWSTEEL, IEX, TIINDIA, DALBHARAT

  #### Config: M=200 sm=0 monthly (base Calmar 0.550, turnover 617%)

  | Check | Verdict | Detail |
  |---|---|---|
  | §6.2 Universe perturbation | **FAIL** | perturbed calmar=0.187, retention=34% (threshold ≥70%) |
  | §6.3 Neighborhood plateau | **FAIL** | 2/3 neighbors below 0.4675 (85%×0.550): sm=3→0.187, quarterly→0.061 |
  | §6.4 Subperiod (DIAGNOSTIC) | — | Pre-COVID chop −0.136 / Post-COVID bull +6.971 / Rate-hike correction +0.159; concentration_hard=FAIL |
  | §6.5 Turnover/capacity | PASS | participation 0.027% < 5% ADV floor |
  | §5-4 Deployment bar | **FAIL** | C_strat=0.550 > C_bench=0.473 (calmar ok) but maxDD ratio=0.80 > 0.70 |
  | **§5 VERDICT** | **FAIL** | Failed gates: §6.2, §6.3, deployment bar |

  Dropped names (§6.2): CGPOWER, ADANIGREEN, TATAELXSI, GREENPANEL, IEX, PERSISTENT, APOLLOHOSP, KPITTECH, JBCHEPHARM, GUJGASLTD

  **ConfigLedger K this run (MD2): 10** (2 base runs + 2 §6.2 perturb runs + 6 §6.4 subperiod runs)

  **Structural findings (diagnostic, no stick moved):**
  - §6.2: Edge is concentrated in a handful of mid-cap momentum winners in both configs. Dropping
    top-10 P&L names cuts Calmar retention to 43% / 34% — the momentum strategy's edge is not
    broadly distributed across the universe.
  - §6.3: Both configs are lever spikes, not plateaus. The M-lever has some regional structure
    (M=130→M=200 is OK), but smoothing=3 and quarterly cadence create hard cliffs in every direction.
    No config in this grid sits on a robust plateau.
  - Deployment bar: Both configs beat Nifty200 Momentum 30 on base-cost Calmar (0.523 and 0.550 vs
    0.473), but neither passes the maxDD ≤70% gate (ratios 0.77 and 0.80). This is a drawdown
    concentration problem, not a return problem.
  - §6.4 (diagnostic): Both fail concentration_hard — Post-COVID bull Calmar (5.789 / 6.971) is
    more than 5× the other positive subperiods. Regime dependence is confirmed.

  **§5 OUTCOME: NULL CLOSE**
  Zero configs satisfy §5 items 1–4 on full DISCOVERY. Per prereg §5, momentum-only closes as
  a **research note**. `FINAL_OOS` remains pristine and untouched. No stick moved, no lever added,
  no threshold loosened. This is a pre-accepted, honest finding per `00` §10.

### MD3 — One-shot FINAL_OOS + §9 DoD verdict (only on a locked candidate)

- **Status:** **N/A** — MD2 null close. No locked candidate. `FINAL_OOS` pristine.
- **Depends on:** MD2 with a locked candidate — MD2 produced the null outcome; MD3 is not performed.
- **Session log:** _(not run — null outcome per prereg §5)_

---

## Exit criteria

- [x] MD1 — 12-config cost screen run on full DISCOVERY; §6.1 survivor set identified (2 configs); all logged.
- [x] MD2 — full battery + §5 on survivors; **NULL CLOSE** declared (no config satisfies §5 items 1–4).
- [x] MD3 — **N/A** (null outcome; FINAL_OOS untouched; no second OOS run).
- [x] MD2 null → momentum-only closes as a research note; no stick moved, no second OOS run.
      A pre-accepted, honest outcome (`00` §10). **FINAL_OOS remains pristine.**

---

## Research Note (final close, 2026-06-19)

**Momentum-only (5-factor, N=20, Track-A construction) closes as a research note.**

The full §4 grid (12 configs across M×smoothing×cadence) was searched for a lower-turnover config
that survives realistic costs and sits on a robust plateau. The honest finding is:

1. **The §6.1 cost bar is passable** — M=130 and M=200 at monthly cadence both survive pessimistic
   costs (ratios 1.35 and 1.45). The cost problem from T6 is soluble with a wider sell buffer.
2. **§6.2 is the structural barrier** — momentum edge is concentrated in a small set of top names
   (~10 stocks drive the bulk of P&L). Dropping them cuts Calmar retention to 34–43%. This is not
   a config problem; it is a structural property of momentum in the Indian mid-cap universe.
3. **§6.3 fails because the lever space has no plateau** — smoothing=3 and quarterly cadence both
   destroy Calmar in every direction (0.06–0.27 vs 0.52–0.55 base). The two survivors are isolated
   spikes, not robust regions.
4. **The deployment bar fails on drawdown** — both configs beat Nifty200 Momentum 30 on Calmar but
   carry maxDD ratios of 0.77–0.80 (threshold ≤ 0.70). The strategy's drawdown is too close to the
   benchmark's to clear the bar.
5. **§6.4 (diagnostic) confirms regime concentration** — Post-COVID bull Calmar (5.8–7.0) is >> 5×
   other subperiods. The momentum edge is real but heavily regime-dependent.

**No config in this grid earns the one-shot OOS. `FINAL_OOS` is pristine.**
Value+momentum revisit (Track-B) is deferred to ~6 months out pending a fundamental factor re-ingest
(per TBE2 data-gap finding and `04` close).
