# v3 / 10 — Skew-Aware Re-Validation of S3: dense §6.3 plateau → one-shot FINAL_OOS

> **Status: LOCKED (§12 signed 2026-06-21, Arafat) — R10.1 DONE → §6.3 dense-lattice FAIL → §5 NULL CLOSE
> (U=400 neighbour 83% < 85%; S3 is a +U spike, not a region). `FINAL_OOS` pristine — never consumed.**
> Pre-registration written BEFORE the dense
> §6.3 lattice is measured. Per spec 04 §5 / `00` §1, the design is committed *before* the new
> numbers exist, so no later session moves the measuring stick (the v1 failure mode). The v2
> `FINAL_OOS` block (2023-07-01 → 2026-06-12) has **never been observed** across the entire
> v2→v3 program and is inherited here as a still-unspent one-shot.
>
> **This file is a commitment, not a task list.** It fixes — before any new measurement — the
> single candidate, the one methodological fix being applied, the dense lattice, the binding
> acceptance rule, the honest "conditional" labelling, and the one-shot OOS protocol. Moving any
> stick after a result (a new lever, a loosened threshold, a re-touched OOS, a re-picked operating
> point) is forbidden (`00` §1).

---

## 0. Why this prereg exists (the re-check that earned the OOS)

Five lines of work closed as research notes, all hitting the same verdict: *a diversified momentum
book either fails a robustness gate or merely matches the passive Nifty200 Mom30 index after costs.*
The **skew-aware §6.2 re-check** (2026-06-21, `app/backtest_v2/su_md_skew_recheck.py`, DISCOVERY-only,
`FINAL_OOS` untouched) put the first crack in that verdict:

| Config | base Calmar | vs Mom30 TRI 0.473 | dd_ratio | §6.2 **skew-aware** (200-draw) | §6.2 classic | §6.5 |
|---|---|---|---|---|---|---|
| **S3** (stable U=350 B=1.25) | **0.575** | beats (+0.10) | 0.70 ✅ | median **91%** / p5 **72%** / rot **55** ✅ | 35% ❌ | ✅ |
| MD-M200 (floor, M=200) | 0.550 | beats (+0.08) | 0.80 ✅ | median 96% / p5 83% / rot 55 ✅ | 34% ❌ | ✅ |

Both reproduce their SU2/MD2 anchors byte-for-byte and both **beat the real index on base-cost Calmar
with maxDD ≤ benchmark AND pass the skew-aware §6.2** — the gate `09` §2c adopted (random-subset
retention median ≥ 0.70 + p5 ≥ 0.50 + ≥ 25 rotating per-year top-10 contributors; the median bar is
**not** relaxed vs classic — only the operationalisation). They were eliminated in SU2/MD2 on exactly
two things, **both now identified as measurement defects rather than properties of the strategy:**

1. **§6.2 classic drop-top-10** (35% / 34%) — an ex-post, lookahead-flavoured perturbation that is
   structurally hostile to a positively-skewed momentum strategy (`09` §2c). Dropping the *specific*
   realised winners craters Calmar; dropping a *random* 10 of ~200 held names barely dents it (median
   ~91-96%) with 55 distinct annual contributors rotating ⇒ the edge is **broad**, not a few names.
2. **§6.3 plateau** — for S3, judged on the **sparse 2-point U-lattice** SU2 itself flagged as
   unreliable (`08` §6.3: "(350,1.0) was never enumerated … the S2/S3 neighbourhood evidence must be
   read carefully"). A plateau gate on a 2-point lattice cannot distinguish a spike from a region.

**The one question this prereg asks:** *Does the pre-specified lead candidate **S3** sit on a genuine
§6.3 plateau when its universe lattice is measured **densely** (not the sparse lattice that killed it) —
and if so, does it survive the one-shot `FINAL_OOS` against an **investable, fair-costed** Mom30?* If
yes → a deployable (conditional, see §5/§9) active momentum strategy. If no → "buy the index fund",
now **earned** rather than assumed. `FINAL_OOS` is spent at most once, only on a locked S3.

---

## 1. Scope discipline (inherits `00` §1 — restated)

- ❌ **No new factor.** Frozen at the Track-A five (§3). Track B is closed; no fundamentals, no value tilt.
- ❌ **No momentum-knob search.** M, smoothing, cadence, N are exhausted (MD/SU) and **held constant**
  at the SU2 S3 construction (§3). They are **not** re-searched.
- ❌ **No re-picked operating point.** The locked candidate **is S3 (U=350, B=1.25)**, pre-specified
  now. The §4 lattice is a *plateau check on S3*, **not** a search to select a better U or B (picking
  the best lattice point after seeing the lattice is the v1 sin — `00` §1).
- ❌ **No threshold relaxation.** Skew-aware median stays ≥ 0.70 / p5 ≥ 0.50; §6.3 stays ≥ 0.85;
  maxDD stays ≤ 100% of benchmark. The **only** methodological changes are §2's two fixes, each
  justified independent of the result it explains.
- ❌ **No moved split.** `validation.DISCOVERY` / `validation.FINAL_OOS` reused **unchanged** (§8).
- ❌ **No FINAL_OOS peek** before a single §5-locked candidate exists (§8).
- ✅ Every config evaluated is logged to the v2 `ConfigLedger`; cumulative **K carries from the
  ledger** and feeds the deflated Sharpe (§7). A fresh objective does **not** reset K.
- ➕ **MD-M200 is corroboration only** — it confirms the result is not a stable-universe artefact. It
  is **not** a second OOS candidate (one shot, one config — §8).

---

## 2. The pre-registered methodological fixes (explicit, evidence-based, independent of the result)

**2a. Concentration gate = skew-aware §6.2 (classic drop-top-10 → reported guard).**
- *Justification (binding, on the record, predates this prereg):* `09` §2c established on first
  principles of skewed-strategy statistics that classic drop-top-10 is an ex-post, lookahead-flavoured
  perturbation; `09` replaced it with the skew-aware test **before** this re-check. The median
  threshold (0.70) is **not** relaxed. This is the project's current concentration gate for *all*
  momentum work — applied here for consistency, not invented to pass S3.
- *Honest carry (the §2c "conditional" rule — NOT softened):* S3 **fails** classic drop-top-10 (35%).
  Per `09` §2c, **skew-pass + classic-fail ⇒ "conditional", not "validated".** This label is carried
  all the way into the §9 deploy verdict as a disclosed name-concentration caveat. `10` may not quietly
  upgrade a classic-fail config to "validated".

**2b. §6.3 plateau measured on a DENSE lattice (the sparse-lattice defect, fixed).**
- *Justification (binding, independent):* `08` §6.3 itself flagged the S3 plateau evidence as sparse
  (only S1 present as a neighbour; (350,1.0) never enumerated). A region-vs-spike test is meaningless
  on 2 points. `09` already moved to a dense U-grid {300,350,400} for this reason. §4 extends that to a
  full ±1 lattice around S3 on **both** axes (U and B). Bar-internal measurement fix, decided
  independent of the result.

**2c. Deployment bar = investable (fair-costed) Mom30, reported alongside the zero-cost TRI.**
- *Justification (binding, independent):* the `08`/`09` deploy bar compared a **base-cost strategy**
  against the **zero-cost** Mom30 **TRI** (`03` §2.1/§3) — an uninvestable, frictionless index. The
  economically correct bar is the **investable** fund: TRI minus a passive-replication cost (the index's
  own turnover through the same `costs.py`) minus an ETF expense (~0.30%/yr). This is a bar-internal-logic
  fix like `08` §2b. **Guard against lowering the bar:** S3 already beats the *harder* zero-cost TRI
  (0.575 > 0.473), so the fair-costed bar cannot be accused of being lowered to manufacture a pass — both
  are reported, and the zero-cost TRI cross-check is retained.

---

## 3. The construction (frozen — the only variable is the §4 lattice)

The locked candidate is **S3**, identical to `08` SU2 S3 (byte-for-byte; `su_md_skew_recheck.py`
reproduced Calmar 0.575 exactly):

- `active_factors = [mom_12_1, low_vol, trend_quality, mom_6_1, reversal]` (equal-weight rank-blend),
- `target_positions N = 20`, `sell_rank_buffer M = 130`, `rank_smoothing_months = 0`,
  `rebalance_cadence = monthly`,
- `use_regime_overlay = True`, `catastrophic_stop_pct = 25.0`, `liquidity_floor_cr = 5.0` (safety floor),
- **stable universe:** semi-annual review (Jan31/Jul31), top-U by 126-td median adv_20, B·U hysteresis,
  min-age via `min_periods` (`stable_universe.py`),
- **operating point:** **U = 350, B = 1.25**.
- **Window:** full `validation.DISCOVERY = (2018-02-06, 2023-06-30)` for all §4/§5/§6/§7.
- **Costs:** `base` (primary) and `pessimistic` (stress), `robustness.check_cost_stress` — unchanged.
- **Benchmark:** real Nifty200 Momentum 30 TRI (verified real, `08` SU0) + the §2c fair-costed variant.

---

## 4. The dense §6.3 lattice (fully enumerated now — a plateau check on S3, not a search)

S3 sits at (U=350, B=1.25). The ±1 lattice on both axes — **7 configs, all enumerated, no point added
or removed after results:**

| Axis | Points (B=1.25 unless noted) | Role |
|---|---|---|
| U | **250, 300, 350, 400, 450** | U-plateau around S3 (±1 = U=300 & U=400) |
| B (at U=350) | **1.0, 1.25, 1.5** | B-plateau around S3 (±1 = B=1.0 & B=1.5) |

The center (U=350, B=1.25) is shared ⇒ 5 + 2 = **7 distinct configs**. Each is run once on DISCOVERY at
base cost; record base Calmar, maxDD, turnover, realized membership churn. All 7 logged to `ConfigLedger`.

**§6.3 plateau predicate (NOT relaxed):** S3's four immediate neighbours — U=300, U=400 (B=1.25) and
B=1.0, B=1.5 (U=350) — must **each** stay **≥ 85%** of S3's own base Calmar (0.575 ⇒ threshold 0.489).
A region in **both** axes, not a spike. (Contrast SU2, where only S1 was present and the off-grid
corner was absent.)

---

## 5. Pre-committed acceptance rule (binding — decided before the lattice is run)

S3 becomes the **single locked OOS candidate** iff **all** hold on full DISCOVERY:

1. **§6.1** pessimistic-cost Calmar ratio ≥ 1.0 vs Nifty50 TRI — *carried from SU1 (1.51); re-confirmed.*
2. **§6.2 skew-aware** PASS (median ≥ 0.70 **and** p5 ≥ 0.50 **and** ≥ 25 rotating contributors) —
   *adopt the committed `su_md_skew_recheck` S3 result (91% / 72% / 55), byte-identical config;
   re-run permitted for audit, not required.*
3. **§6.3 dense-lattice plateau** (§4): all four ±1 U/B neighbours ≥ 85% of S3 base Calmar.
4. **deployment bar (§2c):** S3 beats the **fair-costed** Nifty200 Mom30 on **base-cost** Calmar, **and
   stays above it at pessimistic cost**, with **maxDD ≤ 100%** of benchmark. (Zero-cost TRI comparison
   reported as the conservative cross-check.)
5. **§6.5** capacity PASS (avg participation < 5% ADV floor); **§6.4** reported, **not** gating.

**Classic guard (§2c, binding label):** classic drop-top-10 is reported. S3 fails it (35%) ⇒ a lock
under 1–5 is labelled **"conditional"** (skew-pass / classic-fail), **never** "validated". The
"conditional" tag travels into §9.

**Tie-break:** none needed — the candidate is pre-specified S3 (§1). MD-M200 is reported as
corroboration; it is not eligible for the OOS.

**Null outcome (pre-accepted close):** if **§6.3 dense-lattice FAILS** (S3 is a spike, not a region) or
the deploy bar fails at pessimistic cost, S3 is a **research note** — `FINAL_OOS` stays pristine, the
OOS run is **not** performed, and "buy the index fund" stands as the earned conclusion. A null is **not**
a prompt to widen the lattice, relax 0.85, or re-pick U (`00` §1).

---

## 6. Robustness battery (which checks gate)

Reuse `robustness.py` / `skew_robustness.py` unchanged. For S3: §6.1 cost **HARD**, §6.2 skew-aware
**HARD** (primary), §6.3 dense-lattice plateau **HARD**, §6.4 subperiod **DIAGNOSTIC** (the post-COVID
regime concentration both configs carry — reported, the honest forward risk the OOS adjudicates), §6.5
capacity **HARD**. Classic drop-top-10 **REPORTED** (§2c guard, non-gating).

---

## 7. Deflation & K accounting (honest search cost — the headwind is severe)

- The §4 lattice (7 configs) + the carried re-check entries (4) are logged to `ConfigLedger`. Cumulative
  **K at OOS = ledger value** (≥ 69 from `09` + VT entries + 4 re-check + 7 lattice). A fresh objective
  does **not** reset K — read from the ledger at OOS time.
- At OOS (§8): report **raw Sharpe, K, deflated Sharpe** (`validation.deflated_sharpe`) **and PBO**
  (`pbo_cscv` on DISCOVERY walk-forward folds; no fold reaches FINAL_OOS). **The deflation headwind is
  real and explicitly acknowledged: at K ≳ 80 a marginal edge will not clear a deflated bar — only a
  LARGE OOS edge survives.** A deflated-Sharpe miss with a Calmar/maxDD deploy-bar pass is reported
  honestly as "deploy-bar pass, deflation-marginal" — not hidden, not upgraded.

---

## 8. Splits & the one-shot protocol

- **DISCOVERY** = `validation.DISCOVERY (2018-02-06 → 2023-06-30)` — all of §4/§5/§6/§7 lives here.
- **FINAL_OOS** = `validation.FINAL_OOS (2023-07-01 → 2026-06-12)` — touched **exactly once**, only after
  S3 is locked by §5, and **never** on the null. The OOS run is the **byte-for-byte locked S3** through
  `engine.run` on FINAL_OOS — once, no re-tuning. Deploy bar evaluated OOS at base **and** pessimistic
  cost, vs the fair-costed Mom30 (zero-cost TRI reported). Mark `FINAL_OOS` consumed.

---

## 9. Definition of Done (the deploy verdict — with the honest conditional ceiling)

S3 is **"validated-CONDITIONAL, deployable"** only if the locked S3 on FINAL_OOS (one shot):
- Beats the **fair-costed Nifty200 Mom30** on **base-cost Calmar**, **stays above it at pessimistic
  cost**, with **maxDD ≤ 100%** of benchmark; AND
- Holds §6.1 / §6.2-skew / §6.3 / §6.5 out-of-sample (the four hard gates do not collapse); AND
- Is tradeable on realized turnover/capacity; AND
- Raw + deflated Sharpe + PBO reported together (§7).

The **"conditional"** ceiling is binding (§2a/§5): because S3 fails classic drop-top-10, the deploy
verdict is **"validated-conditional"** — deployable **with a disclosed name-concentration caveat**
(the realised edge does lean on its strongest names; mitigate with equal-weight + position caps, the
existing N=20 construction). It is **not** "fully validated". §6.4 (post-COVID regime concentration) is
reported OOS as the standing forward risk. Anything less than the four-gate OOS pass is a **research
note** (Rule 12) — no softening to manufacture a pass; "buy the index fund" is then the earned, honest,
money-saving outcome.

---

## 10. What this prereg does NOT do (guards)

- It does **not** add a factor, tune weights, re-search M/smoothing/cadence/N, or re-pick U/B (§1, §3).
- It does **not** soften §6.1/§6.2-skew/§6.3/§6.5 (the only changes are §2's three independently-justified
  fixes; no threshold moves).
- It does **not** move `validation.DISCOVERY` / `validation.FINAL_OOS`.
- It does **not** treat MD-M200 as an OOS candidate (corroboration only — one shot, one config).
- It does **not** re-open or alter the SU2/MD2 closes — those stand as the record under the gates as-run;
  this is a **new** prereg (`00`/`07`: forward options are each a separate new prereg), not a continuation
  of `08`.
- It does **not** touch `FINAL_OOS` until a single DISCOVERY-locked S3 exists, and not at all on the null.

---

## 11. Locked commitments (Arafat — sign §12 to flip DRAFT → LOCKED)

Confirm or redline each before any run:

1. Candidate = **S3 pre-specified** (U=350, B=1.25, 5-factor, M=130, sm=0, monthly, stable universe);
   the §4 lattice is a plateau check, **not** an operating-point search (§1, §3).
2. Fix 2a = skew-aware §6.2 is the concentration gate (median ≥ 0.70 / p5 ≥ 0.50 / rot ≥ 25, NOT
   relaxed); classic drop-top-10 reported; **classic-fail ⇒ "conditional" label** carried to deploy.
3. Fix 2b = §6.3 plateau on the **dense 7-config U×B lattice** (§4), predicate ≥ 85%, **not** relaxed.
4. Fix 2c = deployment bar vs the **fair-costed (investable) Mom30** at base **and** pessimistic cost,
   maxDD ≤ 100%; zero-cost TRI reported as the conservative cross-check.
5. Acceptance rule = §5 items 1–5 + the binding conditional label; pre-accepted null close on a §6.3
   spike or pessimistic-cost deploy fail.
6. K carries from the ledger; raw + deflated Sharpe + PBO reported at OOS; deflation headwind accepted.
7. `FINAL_OOS` spent **exactly once**, only on a §5-locked S3, under §8/§9; pristine otherwise.

> **Signed:** Arafat — date 2026-06-21  (DRAFT → LOCKED; R10.1 authorized)

---

## 12. Execution (cold-session runnable — DISCOVERY only until S3 is locked)

> Read this file + the one stage you are doing. Honor the token budget (Rule 6). Update Status, fill a
> Session log, check off Done-criteria. Do not mark Done if anything was skipped (Rule 12).

### R10.1 — dense §6.3 lattice on DISCOVERY
- **Status:** ✅ DONE (2026-06-21, `app/backtest_v2/r10_lattice.py`). **§6.3 dense-lattice plateau = FAIL
  → §5 pre-accepted null triggered.**
- **Do:** run the 7 §4 configs (U∈{250,300,350,400,450} at B=1.25; B∈{1.0,1.5} at U=350) on full
  DISCOVERY at base cost; record base Calmar, maxDD, turnover, churn; evaluate S3's four ±1 neighbours
  vs the 0.85 predicate. Log all 7 to `ConfigLedger`. **No FINAL_OOS.**
- **Done-criteria:** 7-row lattice table; S3 plateau PASS/FAIL stated; C0/S3 anchors reproduced; mem-safe
  (the `su_md_skew_recheck` slice+gc pattern — `del` per-run frame, ≤ DISCOVERY-end slice); FINAL_OOS untouched.

**Result (DISCOVERY 2018-02-06 → 2023-06-30, base cost; anchors REPRODUCED byte-exact: C0 0.523, S3 0.575):**

| cfg | universe | base Calmar | maxDD | turnover | churn | univ size | role |
|---|---|---|---|---|---|---|---|
| C0 | ₹5cr floor (daily) | 0.523 *(anchor 0.523 ✅)* | 26.1% | 706% | 561% | — | anchor (MD1 M=130) |
| U250 | stable U=250 B=1.25 | 0.442 | 22.9% | 557% | 400% | 0–283 (n=14) | U-axis −2 |
| **U300** | stable U=300 B=1.25 | **0.506** | 24.5% | 584% | 415% | 0–341 (n=14) | U-axis −1 (neighbour) |
| **S3** | **stable U=350 B=1.25** | **0.575** *(anchor 0.575 ✅)* | 23.7% | 604% | 438% | 0–396 (n=14) | **CENTER** |
| **U400** | stable U=400 B=1.25 | **0.479** | 26.0% | 650% | 485% | 0–456 (n=14) | U-axis +1 (neighbour) |
| U450 | stable U=450 B=1.25 | 0.473 | 25.5% | 661% | 501% | 0–513 (n=14) | U-axis +2 |
| **B100** | stable U=350 B=1.0 | **0.564** | 23.7% | 596% | 425% | 0–350 (n=14) | B-axis −1 (neighbour) |
| **B150** | stable U=350 B=1.5 | **0.559** | 23.7% | 630% | 462% | 0–437 (n=14) | B-axis +1 (neighbour) |

**§6.3 plateau predicate (§4, NOT relaxed):** threshold = 0.85 × 0.575 = **0.489**. The four ±1 neighbours:

| neighbour | base Calmar | % of S3 | vs 0.489 |
|---|---|---|---|
| U300 (U-axis −1) | 0.506 | 88% | ✅ PASS |
| **U400 (U-axis +1)** | **0.479** | **83%** | **❌ FAIL** |
| B100 (B-axis −1) | 0.564 | 98% | ✅ PASS |
| B150 (B-axis +1) | 0.559 | 97% | ✅ PASS |

**Verdict: §6.3 dense-lattice plateau FAIL.** The **B-axis is a clean plateau** (97–98%) and U=300 holds (88%),
but **U=400 drops to 83% (0.479 < 0.489)** — S3 is a **spike on the +U axis, not a region in both axes** as
§4 requires. The miss is marginal (2% under the bar, a 0.010 Calmar gap), but §1/§5 forbid relaxing 0.85,
widening the lattice, or re-picking U on a null. Decay is monotone above the center (U350 0.575 → U400 0.479
→ U450 0.473), confirming a genuine peak rather than lattice noise. C0 and S3 anchors reproduced exactly; 7
configs logged to `ConfigLedger`; FINAL_OOS untouched (never loaded — `prices` sliced ≤ DISCOVERY end).

**⇒ §5 pre-accepted null close is triggered (a §6.3 spike).** S3 is a **research note**; `FINAL_OOS` stays
pristine; the OOS run is **NOT** performed. R10.2/R10.3 are **N/A**. "Buy the index fund" stands as the
**earned** conclusion — the dense lattice that `08` §6.3 flagged as missing now shows S3's index-beating edge
(0.575 > 0.473) does **not** generalise to its immediate +U neighbour. (Awaiting Arafat's sign-off to formally
mark the program closed; the null itself is pre-committed by §5.)

### R10.2 — full battery + §5 acceptance on S3
- **Status:** ⛔ N/A — R10.1 §6.3 dense-lattice FAILED (U=400 neighbour 83% < 85%); §5 null close triggered.
- **Do:** §6.2 skew-aware (adopt committed re-check; re-run optional), §6.3 (from R10.1), §6.5 capacity,
  §6.4 diagnostic, classic guard; build the fair-costed Mom30 (§2c) and evaluate the §5.4 deploy bar at
  base + pessimistic. Apply §5 items 1–5 + the conditional label. **No FINAL_OOS.**
- **Done-criteria:** per-gate table; S3 locked (conditional) OR null close declared (Rule 12 — no silent
  pick); FINAL_OOS untouched.

### R10.3 — one-shot FINAL_OOS + §9 verdict (only on a locked S3)
- **Status:** ⛔ N/A — null close (no §5-locked S3). `FINAL_OOS` NOT consumed — stays pristine.
- **Do:** byte-for-byte locked S3 through `engine.run` on FINAL_OOS — **once**. Deploy bar at base +
  pessimistic vs fair-costed Mom30; raw + deflated Sharpe + PBO; §6.1/§6.2-skew/§6.3/§6.5 OOS hold.
- **Done-criteria:** §9 verdict (validated-conditional / research-note); `FINAL_OOS` marked consumed.

---

## Exit criteria
- [x] §12 locked by Arafat (DRAFT → LOCKED) — 2026-06-21.
- [x] R10.1 — dense §6.3 lattice; S3 plateau verdict **= FAIL** (U=400 neighbour 83% < 85%); FINAL_OOS untouched.
- [x] R10.2 — N/A (null close triggered by R10.1 §6.3 FAIL); FINAL_OOS untouched.
- [x] R10.3 — N/A on the null; `FINAL_OOS` NOT consumed — pristine.
