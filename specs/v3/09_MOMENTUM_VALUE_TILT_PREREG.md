# v3 / 09 — Momentum × Value-Tilt on a Dense Stable-Universe Grid: retention-first selection → one-shot FINAL_OOS

> **Status: LOCKED (2026-06-20, Arafat — §12 signed; momentum base = 2-factor `[mom_12_1, low_vol]`
> approved as drafted; VT0 authorized).** No further stick moves: moving any stick after seeing a result
> (a new grid level, a loosened threshold, a re-touched OOS) is the v1 sin and is forbidden (`00` §1).
> This file is a **commitment, not a task list** — it fixes the construction, the grid, the binding
> acceptance rule, and the one-shot OOS protocol *before* anything runs.
>
> **It is NOT a continuation of `08`.** `08` (stable-universe momentum-only) closed as a research note.
> This prereg is a *new program* built on three independently-justified design decisions (§2), each
> decided on its own merits and *not* derived from any observed `08`/`06`/`07` number. It carries the one
> validated mechanism from `08` (the stable universe *did* fix §6.2 concentration) and attacks the one
> wall every momentum-only arc died on: **momentum-only ≈ the passive momentum index after honest costs.**

---

## 0. Why this prereg exists (the one wall, stated mechanically)

Across **three independent programs** the same wall appears, and it is **not** the concentration gate:

| Program | The momentum-only candidate | Binding failure (concentration-independent) |
|---|---|---|
| v2 floor (`04`) | simplest momentum portfolio | trails Nifty200 Mom30 on Calmar **0.305 vs 0.448** (ratio 0.68) |
| v3 Track A (`01` T6) | 5-factor composite | §6.1 cost 0.94<1.0 · §6.3 lone peak · §6.4 single-regime |
| v3 stable-universe (`08` SU2) | stable-S2, U=200 | fixed §6.2 (43%→**91%**) but Calmar **0.457 < index 0.473** → "buy the index fund" |

The diagnosis is now firm: **§6.2 (name concentration) is never the sole blocker.** Every momentum-only
config that fails §6.2 *also* fails an orthogonal gate, and the one config that *passed* §6.2 cleanly
(`08` S2, 91%) died on the deployment bar instead. The wall is **single-edge-source**: a momentum
strategy cannot beat the *momentum* index using only momentum. `08` SU2 split the space into two poles
and could not occupy both:

- **broad universe (`08` S3, U=350):** Calmar 0.575 **> index** — but §6.2 35% (concentrated) and a
  §6.3 plateau verdict that rested on a **sparse 2-point lattice** (under-powered);
- **narrow universe (`08` S2, U=200):** §6.2 91% (robust) — but Calmar **< index**.

**The one question this prereg asks:** *Does adding a momentum-orthogonal **value tilt** — on a
properly-dense universe grid, selected by a **retention-first** rule, with a **skew-aware** concentration
test — convert the broad-universe pole from "beats the index but concentrated" into "beats the index AND
robust," on the honest full DISCOVERY window?* If yes → one-shot OOS. If no → momentum×value-tilt is a
research note and `FINAL_OOS` stays pristine. **Even a PASS only proves the strategy beats the cheap
passive momentum index net of honest costs; if it merely *matches* it, the correct answer remains "buy
the index fund" (§10).**

---

## 1. Scope discipline (inherits `00` §1 — restated)

- ✅ **Exactly one new factor source: a value tilt** (E/P, B/P only), justified in §2a. **No** other new
  factor; **no** accruals/leverage (the data is results-only filings — no balance sheet, `07`/TBE2b).
- ❌ **No momentum-knob search.** M, smoothing, cadence, N are exhausted (`05`/`06`). Held constant (§3).
- ❌ **No fine grid.** The grid is the **9 coarse points** in §5 (3 universe × 3 tilt), fully enumerated,
  decided now. Plus the λ=0 controls that reproduce the `08` anchors.
- ❌ **No moved return-split boundary.** `validation.DISCOVERY` / `validation.FINAL_OOS` reused
  **unchanged** (§9). Value scores are point-in-time *inside* those splits.
- ❌ **No FINAL_OOS peek** before a single §6-locked candidate exists (§9), and **never** on the null.
- ✅ Every config logged to `ConfigLedger`; cumulative **K carries** (≥ 46 at TBE7 + `08`'s 23 ≈ **69+**)
  and feeds the deflated Sharpe (§8). A fresh objective does **not** reset K. **The deflation headwind is
  severe and acknowledged up front: only a *large* improvement clears a deflated bar (§8, §10).**

---

## 2. The three pre-registered design decisions (each justified independently of any result)

**2a. Add a momentum-orthogonal VALUE TILT — not the Track-B co-equal composite that diluted.**
- *Why this is new info, not re-opening a closed track:* Track B (`07`) closed because value, blended as a
  *co-equal composite factor* (equal-weight with momentum), **diluted** the momentum signal (H3 vacuous,
  DSR 0.092). A **tilt** is a different mechanism: momentum stays the **primary** ranker; value is a
  **secondary, low-weight re-rank** (λ≪1, §3) that breaks momentum ties toward cheap names *without*
  displacing the momentum ordering. The thing that makes a tilt potentially *additive* rather than
  dilutive is **orthogonality** — TBE2b measured the value block as momentum-orthogonal (|ρ| < 0.3; E/P
  91.7% / B/P 89.8% coverage). A small orthogonal overlay is the textbook way to add return *without*
  adding momentum's own concentration. Decided on the mechanism (orthogonality + tilt-not-blend), which
  predates and is independent of any `08` number.
- *What this attacks:* the single-edge-source wall (§0) — the **only** lever that can lift a robust base
  over the *momentum* index, since by construction it adds a *non-momentum* return stream.

**2b. Retention-FIRST selection rule — pre-committed (replaces Track A's greedy-Calmar rule).**
- *Why:* Track A's T5 selected the 5-factor by a **greedy-Calmar** rule and got an **overfit** candidate
  (lone peak, single regime). The T5 log explicitly flagged that *"adopting a retention-aware gate is a
  NEW pre-registration decision for Arafat"* and that the best-retention already-run momentum base was
  the 2-factor `[mom_12_1, low_vol]` (57% retention, lowest turnover). This prereg **cashes that flagged
  option**: selection is **retention-first** (robustness is the objective, Calmar is the floor), decided
  on the objective's internal logic, not on any candidate's score.
- *Consequence — the momentum base (§12 redline):* retention-first applied to the factor layer selects
  the **2-factor `[mom_12_1, low_vol]`** base (the best-retention already-run momentum config) over the
  overfit 5-factor. **This re-opens the Track-A factor choice — the one genuinely new factor-layer
  decision here — and is the key §12 redline.** (Alternative: keep `08`'s frozen 5-factor base; noted in
  §12.) The momentum *knobs* (M/sm/cadence/N) remain frozen either way.

**2c. DENSE universe grid + SKEW-AWARE §6.2 — both test-power fixes, decided on the tests' own logic.**
- *Dense grid:* `08` SU2's §6.3 plateau verdict on S3 (U=350) rested on a **2-point lattice** (only S1
  present as a neighbor; the U=350,B=1.0 corner was never enumerated) — **under-powered**. The §5 grid
  centers the broad-universe region (U ∈ {300, 350, 400}) so the interesting cell (U=350) is **interior
  with neighbors on both axes** — the §6.3 plateau test is now properly powered exactly where SU2 was
  blind. Decided on test power, not on S3's result.
- *Skew-aware §6.2:* the classic §6.2 "drop the top-10 **realized** P&L names" is an *ex-post,
  look-ahead-flavored* perturbation that is structurally hostile to a positively-skewed strategy (you
  only know those were winners because you saw the whole sample). A **distribution-aware** test —
  *random-subset* drops + *contributor-identity rotation* (§6) — asks the right question ("is the edge
  broad-based and does it rotate its winners?") on first principles of skewed-strategy statistics.
  **The threshold is NOT relaxed** (median retention bar stays ≥ 70%); only the *operationalization* is
  upgraded, and the classic drop-top-10 is **still reported alongside** for whole-program comparability.

> **Honest contamination flag (Rule 12, binding mitigation).** We *already know* momentum fails the
> classic drop-top-10 §6.2. Designing a gentler §6.2 with that knowledge is knowledge-contaminated. The
> pre-committed mitigation: (i) the skew-aware thresholds are **locked now** (§6), before any run; (ii)
> the classic drop-top-10 retention is **reported next to** the skew-aware result every time; (iii) a
> config that **passes skew-aware but fails classic** is labeled a **WEAKER** result in §10 and does
> **not** earn the "validated, deployable" label on its own — only "research-note, conditional." This
> keeps the upgrade honest rather than a back-door relaxation.

---

## 3. The construction (frozen for the search except the §5 grid levers)

Built as a signal-layer change only — no engine edit. Reuses: the `08` stable-universe mask
(`stable_universe.py`, validated in SU0–SU2), the existing momentum `composite_rank` (`factors.py`), and
the **TBE2b-unblocked value block** (reuse the Track-B value-block construction; do **not** rebuild).

- **Universe (carried from `08`, validated mechanism):** stable ADV-ranked membership — semi-annual
  review (Jan 31 / Jul 31), top-U by 126-td median adv_20, hysteresis buffer **B = 1.25** (the `08`
  churn antidote), ₹5cr adv_20 floor retained as per-day tradeability safety. **U is a §5 grid lever.**
- **Momentum base (primary ranker, §2b — held constant across the grid):**
  `active_factors = [mom_12_1, low_vol]` (equal-weight composite percentile), `N = 20`, `M = 130`,
  `smoothing = 0`, `cadence = monthly`, regime overlay ON, cat-stop 25%. *(§12 redline: 5-factor alt.)*
- **Value tilt (the one new source, §2a):** `value_rank` = equal-weight cross-sectional percentile of
  **E/P** and **B/P** (point-in-time, lagged per the Track-B value data layer; no lookahead). Combined as
  a **weighted rank-sum**: `final_rank = momentum_rank + λ · value_rank`, λ ∈ §5. **λ = 0 reproduces the
  pure-momentum base exactly (the anchor/control).** λ is kept small (≤ 0.6) so momentum stays primary —
  this is a *tilt*, not the Track-B co-equal blend (which was effectively λ = 1).
- **Window:** full `validation.DISCOVERY (2018-02-06 → 2023-06-30)` for all search + selection.
- **Benchmark (deployment bar, §10):** **real** Nifty200 Momentum 30 TRI (the cached series SU0 verified
  real, worst-day −12.78% COVID signature — *not* the `run_real.py` placeholder).
- **Costs:** "base" and "pessimistic" per `robustness.check_cost_stress`, reused unchanged.

---

## 4. Proposed level defaults (for §12 lock)

| Symbol | Meaning | Proposed | Note |
|---|---|---|---|
| momentum base | primary ranker | `[mom_12_1, low_vol]` | retention-first (§2b); 5-factor = §12 redline |
| **U** | universe size (top-N by 126-td adv_20) | grid {300, **350**, 400} | centers the broad-universe pole; 350 interior |
| **B** | hysteresis buffer | 1.25 (fixed) | the `08` churn antidote; not re-searched |
| **λ** | value-tilt strength | grid {0, **0.3**, 0.6} | 0 = pure-momentum anchor; 0.3 interior |
| value factors | the tilt | E/P, B/P (equal-weight) | TBE2b-unblocked, momentum-orthogonal |

---

## 5. The search grid (9 coarse points — two new variables: U and λ)

3 universe × 3 tilt, fully enumerated. The **interior cell (U=350, λ=0.3)** has neighbors on both axes →
the §6.3 plateau test is fully powered there (the SU2 fix). The **λ=0 column** is the pure-momentum
control (reproduces the `08` broad-universe anchors); the **U=350, λ=0 cell must reproduce `08` S3's base
Calmar 0.575 byte-for-byte** (anchor check).

| | λ=0 (control) | λ=0.3 | λ=0.6 |
|---|---|---|---|
| **U=300** | C-300 | T-300-lo | T-300-hi |
| **U=350** | C-350 (≡ `08` S3 anchor) | **T-350-mid (interior)** | T-350-hi |
| **U=400** | C-400 | T-400-lo | T-400-hi |

**Two-stage (mirrors `08`):**
- **Stage 1 (all 9 — cost screen):** run each on full DISCOVERY at base + pessimistic cost. Record base
  Calmar, maxDD, §6.1 pessimistic ratio, realized turnover, **realized value-tilt activity** (how often
  the tilt changes the held set vs λ=0). Log all 9 to `ConfigLedger`. Reconfirm the value block is
  momentum-orthogonal on this window (|ρ| < 0.3) — fail loud if it drifted (Rule 12).
- **Stage 2 (only configs clearing §6.1 ≥ 1.0):** skew-aware §6.2 (+ classic, reported), §6.3 plateau
  (over the §5 U×λ neighbors), §6.5 capacity, §6.4 diagnostic, deployment bar.

---

## 6. Pre-committed acceptance rule (binding — decided before any run)

A config becomes the **single locked OOS candidate** iff **all** hold on full DISCOVERY:

1. **§6.1** pessimistic-cost Calmar ratio **≥ 1.0** (vs Nifty50 TRI, the program's §6.1 benchmark).
2. **§6.2 skew-aware (PRIMARY gate, threshold NOT relaxed):**
   - **(a) random-subset retention:** over **200** draws each dropping a **random 10** of the held names,
     the **median** retention (perturbed Calmar / base Calmar) **≥ 0.70** AND the **5th-percentile**
     retention **≥ 0.50** (the edge is broad-based in distribution, not just on average);
   - **(b) contributor rotation:** the union of the per-calendar-year top-10 P&L contributors spans
     **≥ 25 distinct names** across DISCOVERY (winners *rotate* — a process, not a story).
   - **classic drop-top-10 retention is computed and reported** but is **not** the gate (§2c flag).
3. **§6.3 plateau:** the config and its §5 U×λ neighbors (±1 step on U and on λ) stay **≥ 85%** of the
   config's base Calmar — a region, not a spike. (Best-powered at the interior cell.)
4. **deployment bar (`08` §2b, carried):** beats **real Nifty200 Mom30 TRI** on **base-cost Calmar** with
   **maxDD ≤ 100%** of benchmark.
5. **§6.4** subperiod — reported, **not** gating (window-fragility, TBE3/`05` §2).

**Tie-break (if ≥ 2 satisfy 1–4):** highest **skew-aware median retention** (the robustness we are
buying), then highest base Calmar margin over the index.

**Null outcome (pre-accepted close):** if **0** configs satisfy 1–4, momentum×value-tilt is a **research
note** — `FINAL_OOS` stays pristine, the OOS run is **not** performed. A null is the honest finding that
an orthogonal value overlay does not lift a robust momentum base over the passive momentum index on this
market; it is **not** a prompt to add a grid level, raise λ, widen U, or loosen a threshold (`00` §1).
**The close must record the diagnostic either way:** did the tilt (i) lift Calmar over the index at any
robust cell, and (ii) move skew-aware retention vs the λ=0 control? That trade-off curve is the research
value — it tells us whether the orthogonal edge is real-but-insufficient or simply absent.

---

## 7. Robustness battery (which checks gate)

Reuse `robustness.py` for the classic checks; add the skew-aware §6.2 as a new pre-committed routine
(unit-tested for no-lookahead and determinism before any DISCOVERY run). For Stage-2 survivors:
§6.1 cost **HARD**, §6.2 skew-aware **HARD** (classic reported), §6.3 neighborhood **HARD** (plateau over
§5 U×λ neighbors), §6.4 subperiod **DIAGNOSTIC**, §6.5 capacity reported (expected PASS).

---

## 8. Deflation & K accounting (honest search cost)

- All 9 §5 configs × 2 cost levels logged to `ConfigLedger`. Cumulative **K at OOS = ledger value
  (≥ 46 at TBE7 + 23 from `08`) + these entries** — read from the ledger at OOS time. A fresh objective
  does **not** reset K. **K is ~69+ and rising; a marginal edge will not survive a deflated bar.**
- At OOS (§9): report **raw Sharpe, K, deflated Sharpe** (`validation.deflated_sharpe`) + **PBO**
  (`pbo_cscv` over `walk_forward_windows` on DISCOVERY; no fold reaches FINAL_OOS).

---

## 9. Splits & the one-shot protocol

- **DISCOVERY** = `validation.DISCOVERY (2018-02-06 → 2023-06-30)` — all of §5/§6/§7/§8 lives here.
- **FINAL_OOS** = `validation.FINAL_OOS (2023-07-01 → 2026-06-12)` — touched **exactly once**, only after
  a single candidate is locked by §6, **never** on the null. The OOS run is the byte-for-byte locked
  candidate through `engine.run` on FINAL_OOS — once, no re-tuning. Mark `FINAL_OOS` consumed.

---

## 10. Definition of Done (the deployment bar)

The candidate is **"validated, deployable"** only if the single locked config, on FINAL_OOS:
- Beats **real Nifty200 Mom30 TRI** on **Calmar** after **base** costs, with **maxDD ≤ 100%** of
  benchmark; AND
- Holds §6.1 / §6.2-skew-aware / §6.3 / §6.5 out-of-sample (the four hard gates do not collapse); AND
- **Also passes the classic drop-top-10 §6.2 ≥ 70%** (else it is labeled **"research-note, conditional"**,
  not "validated" — the §2c contamination guard); AND
- Is tradeable on realized turnover/capacity; AND
- Raw + deflated Sharpe reported together (§8) — **a deflated edge ≤ 0 is a research note regardless of
  raw outperformance.**

§6.4 reported OOS as a diagnostic, not a gate. Anything less is a **research note** (Rule 12) — no
softening of the four hard gates to manufacture a pass. **Honest forward note:** if the strategy merely
*matches* the passive momentum index, the correct conclusion is "buy the index fund" — a valid,
money-saving outcome, and the most likely one given the three-program prior (§0).

---

## 11. What this prereg does NOT do (guards)

- It does **not** re-search momentum knobs (M / smoothing / cadence / N), tune value weights beyond the
  3-point λ grid, or add any factor beyond the E/P+B/P value tilt (§1, §3).
- It does **not** acquire real balance-sheet data (accruals/leverage stay out — `07`); the value tilt is
  E/P+B/P only, from data in hand.
- It does **not** soften the §6.1 / §6.2 (median-retention ≥ 70%) / §6.3 / §6.5 thresholds; §2c upgrades
  the §6.2 *operationalization* only, with the classic test reported alongside as a guard.
- It does **not** move `validation.DISCOVERY` / `validation.FINAL_OOS`.
- It does **not** touch `FINAL_OOS` until a single DISCOVERY-locked candidate exists, and not at all on
  the null outcome.

---

## 12. Locked commitments (Arafat — sign to flip DRAFT → LOCKED)

Confirm or redline each before any run:

1. **New source = value TILT** (E/P + B/P, weighted rank-sum λ-overlay, momentum primary) — *not* the
   Track-B co-equal blend (§2a).
2. **Momentum base — KEY REDLINE:** retention-first ⇒ **`[mom_12_1, low_vol]`** (re-opens the Track-A
   factor choice, §2b). ☑ **approve 2-factor**  /  ☐ redline to `08`'s frozen 5-factor.
3. **Grid = the 9 coarse points** in §5 (U ∈ {300,350,400} × λ ∈ {0,0.3,0.6}); no level added/removed
   after results; U=350,λ=0 must reproduce `08` S3 (Calmar 0.575).
4. **Selection = retention-first** (§2b), §6 items 1–5, skew-aware-median-retention tie-break,
   pre-accepted null close (§6).
5. **§6.2 = skew-aware PRIMARY** (random-subset median ≥ 0.70 + p5 ≥ 0.50 + ≥ 25 rotating contributors),
   threshold NOT relaxed, classic drop-top-10 reported alongside; **pass-skew-fail-classic = "conditional"
   not "validated"** (§2c, §10).
6. **Bar = maxDD ≤ 100% + Calmar dominance** vs real Nifty200 Mom30 TRI (carried from `08` §2b).
7. **`FINAL_OOS` spent exactly once**, only on a §6-locked candidate, under §9/§10; pristine otherwise.
   **K carries (~69+); deflated edge ≤ 0 ⇒ research note regardless of raw outperformance.**

> **Signed:** Arafat — 2026-06-20 (all 7 commitments approved as drafted, incl. §12.2 = 2-factor base;
> DRAFT → LOCKED; VT0 authorized).

---

## 13. Execution (cold-session runnable — DISCOVERY only until a candidate is locked)

> Read this file + the one stage you are doing. Honor the token budget (Rule 6). Update Status, fill a
> Session log, check off Done-criteria. Do not mark Done if anything was skipped (Rule 12).

### VT0 — scaffolding: value-tilt wiring + skew-aware §6.2 + orthogonality reconfirm (no backtest)
- **Status:** ✅ DONE (2026-06-20). No backtest run; FINAL_OOS untouched.
- **Do:** (a) load the TBE2b value block (E/P, B/P), point-in-time, into a `value_rank` percentile;
  reconfirm |ρ| < 0.3 vs the momentum composite on DISCOVERY (fail loud if drifted). (b) Wire
  `final_rank = momentum_rank + λ·value_rank` into `V3SignalStore` behind a `value_tilt_lambda` config
  flag (λ=0 ⇒ byte-identical to the pure-momentum base). (c) Implement the skew-aware §6.2 routine
  (random-subset retention + contributor rotation), unit-tested for **no-lookahead + determinism**.
- **Done-criteria:** orthogonality reconfirmed (or loudly flagged); λ=0 reproduces the pure-momentum base
  byte-for-byte; skew-aware §6.2 unit-tested; **no backtest, no FINAL_OOS.**

**Session log (2026-06-20):**
- **(a) Orthogonality RECONFIRMED — PASS.** `vt0_scaffold.py` on full DISCOVERY (2018-02-06 →
  2023-06-30): momentum composite (2-factor `[mom_12_1, low_vol]`) vs value_rank (E/P+B/P equal-weight
  percentile) over **62,184** overlapping (date×name) cells → **Pearson ρ = −0.1063, |ρ| = 0.106 < 0.30**.
  The TBE2b orthogonality holds; the tilt's additive rationale (§2a) stands. *(Coverage note, honest:
  E/P 29.2% / B/P 27.9% of cells are non-null **over the full 3,470-ISIN universe** incl. illiquid
  micro-caps with no filings — not contradicting TBE2b's 91.7%/89.8%, which was measured over the
  tradeable in-universe names; the tilt only ever sees gate-eligible names.)*
- **(b) Value tilt WIRED, λ=0 byte-identical — VERIFIED.** `V3Config.value_tilt_lambda` (default 0.0,
  guarded: non-negative; λ>0 forbids fundamental factors in `active_factors` so value cannot route
  through the closed Track-B co-equal blend). `signals_v3.build_value_rank` + `_apply_value_tilt` layer
  `final_rank = momentum + λ·value_rank` on top of the price-only composite; `precompute_v3_signals`
  gained an optional `value_frames` arg. λ=0 short-circuits to the momentum frame **unchanged** —
  test `test_lambda0_byte_identical_even_with_value_frames` asserts byte-for-byte equality even when
  value frames are supplied. **560 → 580 backtest_v2 tests green (parity suite unchanged).**
- **(c) Skew-aware §6.2 IMPLEMENTED + unit-tested.** New `skew_robustness.py`: `random_subset_retention`
  (seeded RNG, 200×drop-10, median≥0.70 ∧ p5≥0.50; `run_perturbed` injected as a seam → engine-free)
  + `contributor_rotation` (per-year top-10 union ≥25). Tests prove **determinism** (same seed ⇒
  identical drop sequence + retentions), **no-lookahead** (200 random draws cover all 40 held names ⇒
  drops are RNG-driven, not P&L-driven), threshold logic, and fail-loud on non-positive base Calmar.
- **⚠ Construction decision flagged (Rule 12) — missing-value handling in the tilt:** a held name with
  **no** E/P/B/P data is **neutral-filled to median rank 0.5** in `_apply_value_tilt`, so the tilt only
  *re-orders* momentum-eligible names and never *drops* one for lacking fundamentals (NaN-propagation
  would shrink the momentum universe — wrong for a tilt). This was **not** explicitly pre-registered;
  it is the principled default for an overlay and is documented in code. Sparse value frames are
  forward-filled across the daily grid until the next review. **No threshold or grid moved.**

### VT1 — Stage 1: 9-config cost screen on full DISCOVERY
- **Status:** ✅ DONE (2026-06-20, `vt1_cost_screen.py`). DISCOVERY only; FINAL_OOS untouched.
- **Do:** run each §5 config at base + pessimistic cost; record base Calmar, maxDD, §6.1 ratio, turnover,
  value-tilt activity; log all 9 to `ConfigLedger`. **No FINAL_OOS, no §6.2/3/4.**
- **Done-criteria:** 9-row table; §6.1-clearing set identified (may be empty — report honestly); the
  U=350,λ=0 anchor reproduces `08` S3 (0.575); `FINAL_OOS` untouched.

**Session log (2026-06-20):**

| Cfg | U / λ | base Calmar | MaxDD | Turn% | Tilt% | C_strat(P) | C_n50 | Ratio | §6.1 |
|---|---|---|---|---|---|---|---|---|---|
| C-300 | U=300 λ=0 | 0.205 | 26.5% | 510 | 0.0 | 0.169 | 0.346 | 0.49 | FAIL |
| T-300-lo | U=300 λ=0.3 | 0.315 | 27.8% | 514 | 32.0 | 0.277 | 0.346 | 0.80 | FAIL |
| T-300-hi | U=300 λ=0.6 | 0.295 | 26.7% | 531 | 39.9 | 0.255 | 0.346 | 0.74 | FAIL |
| C-350 | U=350 λ=0 | 0.295 | 27.4% | 506 | 0.0 | 0.257 | 0.346 | 0.74 | FAIL |
| T-350-mid | U=350 λ=0.3 | 0.318 | 27.7% | 515 | 33.1 | 0.279 | 0.346 | 0.81 | FAIL |
| T-350-hi | U=350 λ=0.6 | 0.265 | 27.7% | 545 | 39.7 | 0.227 | 0.346 | 0.66 | FAIL |
| C-400 | U=400 λ=0 | 0.289 | 28.0% | 528 | 0.0 | 0.252 | 0.346 | 0.73 | FAIL |
| **T-400-lo** | **U=400 λ=0.3** | **0.392** | 28.2% | 534 | 31.3 | **0.349** | 0.346 | **1.01** | **PASS** |
| T-400-hi | U=400 λ=0.6 | 0.326 | 28.9% | 558 | 38.5 | 0.286 | 0.346 | 0.83 | FAIL |

- **§6.1 survivor set = {T-400-lo}** — exactly **1/9** clears the pessimistic-cost Calmar ratio ≥ 1.0
  (ratio **1.01 — marginal**, base Calmar 0.392). This is the only config carried to VT2. Honest: it
  clears by a hair; a 1.01 ratio is fragile and the deflation headwind (§8, K≫69) is unforgiving.
- **Plumbing anchor REPRODUCED — PASS.** The separate 5-factor U=350 λ=0 base run returned Calmar
  **0.575**, byte-reproducing `08` S3 → the stable-universe mask + engine plumbing is unchanged from `08`.
  ⚠ **Spec-conflict resolved + flagged (Rule 7/12):** §5/§12.3 say *"U=350,λ=0 must reproduce `08` S3's
  0.575"*, but §12.2 (signed) sets the grid base to the **2-factor** `[mom_12_1, low_vol]`, which **cannot**
  reproduce a **5-factor** number. The grid's `C-350` (2-factor, λ=0) is **0.295**, not 0.575. Reconciled
  by treating the anchor as a **plumbing-regression check** run on `08`'s exact 5-factor config *separately*
  from the grid — both reported. The done-criterion is met under that reading; **no stick moved** (grid base
  stays the signed 2-factor). The 5-factor "0.575" anchor literal in §5/§12.3 is a drafting artifact, not a
  grid cell — Arafat to note for any future erratum.
- **Orthogonality RECONFIRMED — OK.** ρ = −0.1063 (|ρ| 0.106 < 0.30) over 62,184 cells — unchanged from
  VT0; the tilt's additive rationale (§2a) still holds on this window.
- **Tilt diagnostic (the §6/§200 trade-off curve, recorded now):** the value tilt is **additive at λ=0.3
  at every universe** — it lifts base Calmar over the same-U λ=0 control (C-300 0.205→0.315, C-350
  0.295→0.318, C-400 0.289→0.392) while changing 31–33% of the held set. **λ=0.6 overshoots** (lower than
  λ=0.3 at all three U) → the tilt is real but small; past a point it displaces too much momentum. The edge
  is **real-but-thin**, not absent: only the broadest universe (U=400) + the interior tilt (λ=0.3) crosses
  §6.1, and only marginally.
- **Honest read on the retention-first base (§2b/§12.2):** the 2-factor base is **materially weaker on
  Calmar** than `08`'s 5-factor S3 (C-350 0.295 vs S3 0.575). Retention-first traded raw Calmar for
  robustness up front; the value tilt recovers only part of that gap. VT2 will tell whether the survivor's
  thinner Calmar still carries §6.2/§6.3 robustness.
- **K accounting:** 18 ledger entries this run (9 configs × 2 cost levels); the plumbing anchor is **not**
  logged as a trial (it is a regression check, not a search point). Cumulative K at VT3 ≥ 69 + 18.
- **FINAL_OOS untouched.** VT2 next: full §6 battery on the lone survivor **T-400-lo**.

### VT2 — Stage 2: full battery + §6 acceptance on the §6.1 survivors
- **Status:** ⬜ not started.
- **Do:** skew-aware §6.2 (+ classic, reported), §6.3 plateau (over §5 U×λ neighbors), §6.5, §6.4
  diagnostic, deployment bar; apply §6 items 1–5 + tie-break. **No FINAL_OOS.**
- **Done-criteria:** per-survivor §6 table; exactly one candidate locked OR null close declared (Rule 12);
  the tilt trade-off diagnostic (Calmar-vs-index × retention-vs-control) recorded; `FINAL_OOS` untouched.

### VT3 — One-shot FINAL_OOS + §10 DoD verdict (only on a locked candidate)
- **Status:** ⬜ not started — runs **only** if VT2 locks a candidate; **N/A on the null**.
- **Do:** byte-for-byte locked candidate through `engine.run` on FINAL_OOS — once, no re-tuning; fill the
  §10 DoD item-by-item; report raw + deflated Sharpe + PBO.
- **Done-criteria:** `FINAL_OOS` consumed exactly once (ledger shows it); verdict "validated" /
  "conditional" / "research note" stated plainly (Rule 12).

---

## Exit criteria
- [x] §12 locked by Arafat (DRAFT → LOCKED) 2026-06-20; §12.2 momentum-base = 2-factor `[mom_12_1, low_vol]`.
- [x] VT0 — value tilt wired (λ=0 byte-identical), orthogonality reconfirmed (ρ=−0.106), skew-aware §6.2 test-gated (2026-06-20).
- [x] VT1 — 9-config cost screen (2026-06-20); §6.1 survivor = **{T-400-lo}** (1/9, ratio 1.01 marginal); 5-factor plumbing anchor reproduces `08` S3 (0.575); orthogonality OK (ρ=−0.106); FINAL_OOS untouched.
- [ ] VT2 — full battery + §6; one candidate locked OR pre-accepted null close; tilt trade-off recorded.
- [ ] VT3 — one-shot FINAL_OOS (only on a locked candidate); §10 verdict labeled truthfully. — or **N/A** (null).
