# v4 / 05 — Turnover-First Trend (exit-width × cadence + §5 deployment): Pre-Registration

> **Status: CLOSED — NULL (2026-06-26). LOCKED 2026-06-25 (§0 explicit deviation; §10 signed) → V4.7 → 1/6
> §6.1 survivor (atr 5.0 / daily, ratio 1.27, the FIRST §6.1 pass in v4) → pre-V4.8 diagnostic (87% of net P&L
> = ATGL) → V4.8 FULL §6 battery → NULL: §6.1 PASS but §6.2 FAIL (random-subset p5 43% < 50% — single-name
> tail) AND §6.3 FAIL (atr4/0.75 neighbor 41% < 85% — lone peak). The v4 family is PERMANENTLY and FINALLY
> closed; v4-FINAL_OOS NEVER touched (V4.9 N/A); K ≈ 13. Keeper finding: the exit mechanism mattered far more
> than the entry mechanism. Any adaptive/gain-scaled exit is a NEW prereg, never a v4 continuation.** No stage
> began, and no engine/selector code was written, before §10 was LOCKED. v4-FINAL_OOS pristine throughout. This prereg attacks the **one constraint V4.4
> isolated as binding — turnover × cost** — with the **one lever class the v4 family has never tested**
> (wider / slower-cadence *time-series-trend* exits, as opposed to the *cross-sectional-momentum* churn levers
> v3 `05` swept). It freezes — *before any new return number* — the small grid, the binding acceptance rule,
> the K/deflation accounting, and the one-shot OOS protocol.
>
> **Owner:** Arafat. **Created:** 2026-06-25. **Depends on:** `00_SWING_PREREG.md` (LOCKED + Amendment 1),
> `02_SWING_ENGINE.md` (engine), `03_V41_FORENSIC.md` (turnover/edge mechanism), `04_SELECTOR_PREREG.md`
> (V4.4 — MOM selector proven, turnover isolated as the killer, §5 deployment proven a real lever).
>
> **What this doc is NOT:** not a re-open of the closed V4.1/V4.4 *configs* (those stay closed as research
> notes), not an entry-signal search, not a selector search (MOM is frozen — see §1), not a license to touch
> any frozen `00`/Amendment-1 knob other than the four named in §3.

---

## 0. The reopen decision — read and rule on this BEFORE §10 (binding)

`04` §8 and `00` §8 closed the v4 family with an explicit bar: *"no further v4 amendments without genuinely
new information (new data, not new knobs)."* **Widening an ATR multiple is, on its face, a knob.** This doc
must clear that bar honestly or not be locked at all. The case for "this is genuinely new information, not a
knob-hunt," stated plainly so you can reject it if you disagree:

1. **V4.4 isolated the binding constraint mechanistically.** The edge is *real and per-name* (MOM: +1.98%
   net expectancy, 2.71 payoff — proven, not assumed); it dies to **friction**, and friction is driven by
   **turnover** (`03` Leak A/B). That is a newly-*established causal fact*, not a guess — before V4.4 we did
   not know the edge was real and the constraint was turnover.
2. **The turnover *mechanism* here was never tested.** v3 `05` swept turnover, but on the **cross-sectional
   momentum** churn levers (`sell_rank_buffer` M, rank-smoothing, rebalance cadence — membership rotation).
   v4 is **time-series trend-following**, whose turnover comes from **hold-length / whipsaw**, a *different*
   mechanism with *different* levers (exit width, decision cadence). v4 itself only ever tested **tighter**
   exits (T1 11d/2660%, T2 28d/1061%) — **never a wider/longer-hold exit.** This lever class is genuinely
   unexplored for the whole program.
3. **It is falsifiable and decisive.** A pass = a genuinely deployable trend book. A null = the strong,
   final finding that the trend edge is *structurally too thin for this cost regime* — which closes v4 for
   good and redirects to a cheaper-cost venue/instrument or a different premise, not to another knob.

**The honest counter (Rule 12):** a skeptic can fairly call this "rationalised knob-hunting" — every dead
strategy has one more lever. The turnover-isolation argument is *valid* but I will not oversell it. **This is
exactly the class of call that `04`/`00` reserved for you.** So:

> **§0 DECISION (Arafat — ruled 2026-06-25):** ☐ reopen-justified  ☑ **explicit-deviation**  ☐ decline.
> Recorded as an **explicit deviation** from the `00` §8 / `04` §8 "no new knobs" close (the `10` §13
> species) — **NOT** claimed as "genuinely new information." The honest label: V4.4's turnover isolation is a
> well-motivated *reason* for one more knob, not new information; this reopen is a **bounded, one-time,
> pre-accepted-null** deviation, and explicitly **not** a precedent that any proven-binding-constraint finding
> reopens a closed family.
>
> **Scope of the deviation (explicit — it authorizes TWO stacked things):** (i) the **turnover lever class**
> (exit width + cadence), genuinely new to the whole program — the §0 case above (points 1–3) justifies *this*;
> and (ii) the **§5 deployment axis** (Neutral-bucket fraction), which is **not** new to this doc — it rides
> the prior **`04` §5 pre-authorization** (deployment as a gated axis with its own K). Both run under the
> single corrected v4 K ledger (§7). The reopen claim is therefore: one genuinely-new lever class + one
> already-authorized axis, not a fresh open-ended search.

---

## 1. Scope discipline (the anti-HARKing line — binding)

- ✅ **K CARRIES from the v4 family (corrected to 4 after V4.4 — see §7.0/§7.1); it does NOT reset.** Same
  engine, entry, regime score, universe, ₹3.5L, `target_positions=15`. New axes (exit width, cadence,
  deployment) accrue on top. *(The prior ledger logged 12 by counting config×cost and counting ADV/RS as
  fresh trials; both are over-charges, corrected under the §7.0 counting standard. Confirm at §10.)*
- ✅ **One-shot OOS inherited, still pristine.** v4-FINAL_OOS was **never** touched across V4.1/V4.4, so this
  program inherits the single, unspent v4-FINAL_OOS shot (§7). Spending it is the only path to "validated."
- ✅ **MOM is the FROZEN selector — a recorded decision, not a silent swap.** V4.4 established MOM dominates
  ADV on this engine (base Calmar 0.179 vs 0.083; expectancy +1.98% vs +0.72%) and its trials are **already
  in K**. Carrying MOM forward as the frozen selector is the `04` §3 "exit-choice is a recorded registration
  decision" rule applied explicitly — **the selector axis is NOT re-swept here** (re-floating it would
  re-spend paid trials). ADV at the frozen exit is re-run **once** as the V4.4 anchor (diagnostic, §4).
- ❌ **Only FOUR things change, all named now:** (i) **exit width** (the Type-3 ATR multiple), (ii) **decision
  cadence** (daily → weekly), (iii) **deployment** (the §5-authorized regime Neutral-bucket fraction), and
  (iv) a non-gating **min-hold/cooldown anti-thrash diagnostic** (§5, adds 0 to K). Entry (4 conditions),
  the 5-factor regime *score* (the bucket→fraction *mapping* is the §5 axis, the score is frozen), the
  `stable_universe` U=200, `target_positions=15`, the −25% catastrophic floor, MOM, ₹3.5L, and every
  indicator stay **byte-frozen at `00`/Amendment-1/`04`**.
- ❌ **Lever family is a-priori, not mined.** Wider exits + weekly cadence are **standard, conventional**
  turnover-reduction constructions chosen *because* they are the textbook trend-turnover levers, **not**
  because they backtested well (no backtest has been run). Levels are enumerated in §4 now.
- ❌ **No grid expansion after results.** The §4 grid and its plateau neighbors are fully enumerated. No
  lever, level, or axis is added after a number is seen.
- ❌ **No FINAL_OOS peek** before a single §6-locked candidate exists; **never** on the null (§7).

---

## 2. The goal (unchanged from `00` §2 — no relaxation)

Identical bar to `00` §2 / `04` §2:
- **Primary bar:** beat **Nifty 50 TRI** on **pessimistic-cost Calmar ratio ≥ 1.0** (§6.1) and on **base-cost
  Calmar with maxDD ≤ 100%** of the benchmark (deployment bar).
- Nifty200 Mom30 TRI reported as a reference only.
- A config that merely *matches* the index is the **"buy the index fund"** research-note close.

**The edge thesis for THIS program:** the V4.4 trend book carries a real per-trade edge (+1.98% net) that
friction erases because the book turns over ~800%/yr. If we can **roughly halve turnover** (longer holds /
coarser decisions) **without giving back proportionally more open profit**, the surviving net edge — stacked
on the proven MOM selector and the §5 deployment lift — may clear the costed bar. If wider exits give back as
much as they save (the trail-vs-give-back trade-off is real, not assumed favorable), this closes NULL (§8).

---

## 3. The changes (frozen on sign)

The **only** new degrees of freedom. All operate on the already-frozen entry set + MOM selector; none adds a
name that did not fire, none touches the entry conditions or the regime score.

### 3.1 Exit width — the Type-3 ATR multiple (PRIMARY turnover lever, gated)
The Type-3 close-anchored trail exits when `close < anchor − atr_mult × ATR20`. A **wider** multiple holds
winners longer ⇒ longer holds ⇒ fewer turns ⇒ less cost — but gives back more open profit before exit (the
trade-off the grid measures). `00` froze 3.0 and only-ever-tested **tighter**; this tests **wider**.
- **Grid axis `atr_mult` ∈ {3.0, 4.0, 5.0}** — candidate **4.0**; 3.0 is the old frozen value (the
  low-turnover-floor edge); 5.0 the slow edge. The §6.3 plateau axis.

### 3.2 Decision cadence — daily → weekly (gated)
A daily trend engine re-decides entries/exits every close. Coarsening the **decision clock** to weekly cuts
turnover structurally (fewer, larger decisions) at the cost of delayed exits.
- **`decision_cadence` ∈ {daily, weekly}** — candidate **weekly**. *Definition (faithful + no-lookahead):*
  on a **non-decision day**, `step_day` still (a) applies queued fills, (b) MTMs, (c) ratchets the trail
  anchor, and (d) **checks the −25% catastrophic floor** (risk control is NOT coarsened) — but **skips the
  configured ATR-trail exit check and the entry scan**. The decision day is the **completed week's last
  trading day** (W-FRI as-of, the same completed-week discipline as the weekly-MACD entry input — no
  in-progress week). Binary axis (reported at both levels; a config that clears at one cadence and craters at
  the other is fragile — reported, weighs against locking).

### 3.3 Deployment — the §5-authorized regime Neutral-bucket fraction (gated, IN Stage 1)
`04` §5 ran D_more (Neutral 0.5→0.75) as a non-gating diagnostic and it read **"deployment is a real lever"**
(Calmar 0.179→0.281, maxDD *fell* to 34.0% ≤ benchmark). `04` §5 pre-authorized adding deployment as a gated
axis with its own K. Folded in here **at the candidate level, inside the Stage-1 cost screen**:
- **`neutral_fraction` ∈ {0.5, 0.75}** — Bear stays 0.0, Bull stays 1.0; only the Neutral bucket (score 2–3)
  moves. Candidate **0.75** (the §5 direction). **Stage 1 runs the candidate `neutral_fraction`=0.75**, so the
  §6.1 cost screen gates the *actual deployed candidate* rather than a deployment-stripped book; the **0.5 arm
  is the §6.3 plateau-neighbor** (run in Stage 2).
- *Decided at lock (the alternative considered and rejected):* gating §6.1 in front of a proven lever —
  i.e. evaluating Stage 1 at the frozen 0.5 — would kill a turnover-reduced ~0.78-Calmar config **before** it
  ever saw the ~1.5× deployment lift (`04` §5: 0.179→0.281) that might carry it over the 1.0 bar. On the §8
  arithmetic that makes a Stage-1 null near-certain *by construction of the gate*, not by the strategy's
  merit. The "clean turnover-only frontier at 0.5" is **not** worth gating out the best config, so Stage 1
  runs the candidate deployment.

### 3.4 MOM selector — FROZEN (recorded §1 decision, not an axis)
`selector = "mom"`, `selector_lookback = 126` — byte-frozen from V4.4. Not swept.

---

## 4. The search grid (small, fully enumerated — two-stage)

Everything except §3.1–§3.3 is frozen. Mirrors `04` §4 / v3 `05` two-stage shape.

| Axis | Frozen candidate | Enumerated alternatives (the ONLY ones) | Role |
|---|---|---|---|
| `atr_mult` (exit width) | **4.0** | 3.0, 5.0 | gated turnover lever + §6.3 plateau |
| `decision_cadence` | **weekly** | daily | gated turnover lever (binary) |
| `neutral_fraction` (deploy) | **0.75** | 0.5 | gated §5 lever (candidate in Stage 1; 0.5 = §6.3 plateau-neighbor; binary) |
| selector / entry / regime score / U / target_positions / floor | MOM / 4-cond / 5-factor / 200 / 15 / −25% | — (FROZEN) | settled by `00`/`04` |

- **Stage 1 — turnover cost screen at the candidate deployment:** `atr_mult` {3,4,5} × `decision_cadence`
  {daily, weekly} = **6 configs at the candidate `neutral_fraction`=0.75**, MOM, ₹3.5L whole-share, **base +
  pessimistic** cost. Record turnover, base/pessimistic Calmar, maxDD, win rate, avg hold, §6.1 ratio, **and
  the `03` per-round-trip forensic** (so we see *how* each lever reshapes the trade population — does it cut
  cost faster than it gives back edge?). Also re-run **the V4.4 MOM/ATR-3.0/daily/deploy-0.5 anchor and ADV at
  the frozen exit** once as parity/diagnostic (R3 → 0 to K). Log each **config** to the v4 ledger (K accrues
  per §7.0 — cost levels are one trial, not two; anchors add 0). Identify §6.1 survivors.
- **Stage 2 — battery + deployment plateau-neighbor (only on §6.1 survivors):** add the
  `neutral_fraction`=0.5 plateau-neighbor arm; §6.2 skew-aware / §6.3 plateau (over `atr_mult` {3,4,5} **and**
  `neutral_fraction` {0.5,0.75}) / §6.5 capacity, + §6.4 subperiod diagnostic + the §5 min-hold/cooldown
  anti-thrash diagnostic. Apply §6.

**K estimate (honest, under the §7.0 standard):** Stage 1 = 6 configs (`atr_mult`{3,4,5} × cadence{daily,
weekly}) **at the candidate `neutral_fraction`=0.75**, **counted ×1 cost not ×2** — all 6 are new (the
(atr=3.0, daily, deploy=0.5, MOM) V4.4 anchor is **not** among them now that Stage 1 runs at 0.75; it runs
alongside as parity, R3 → 0) ⇒ **+6 new**. Stage 2 on a single survivor ≈ **+3** (the 0.5 deploy
plateau-neighbor arm + its atr neighbors at base cost). **Carried 4 + ≈9 new ⇒ K ≈ 13 at OOS** (vs ≈28 under
the old config×cost convention; **+1 vs the pre-fix-(a) ≈12**, because Stage 1 now runs the candidate
deployment instead of letting the deploy-0.5 anchor absorb a Stage-1 cell). The skew-aware §6.2 and §6.5
resample one config (no new trials). **Deflation headwind is real but ~halved by the corrected count** (§7,
§8) — it does NOT close the ~2.5× §6.1 gap; a marginal raw edge will still not survive deflation, and the
K 12→13 shift is immaterial to that gap.

---

## 5. Min-hold / re-entry-cooldown — registered as a NON-GATING diagnostic (adds 0 to K)

The two *anti-whipsaw* turnover levers are registered **non-gating**, for a binding reason decided up front:
`03` showed the candidate exit **barely whipsaws** (median hold 42d, only 3.9% of trades held ≤10 days), so
min-hold/cooldown have **low expected leverage on this engine** — spending gated grid axes (and K) on them is
not justified. They run as a pre-committed diagnostic (the `04` §5 species):

- **min_hold_td** — block the *configured ATR-trail* exit (NOT the catastrophic floor) for the first **10 td**
  after entry. **cooldown_td** — after a full exit of an `instrument_id`, suppress its re-entry for **10 td**.
- **Run once** on the Stage-1 candidate (base cost): report turnover, median hold, fills, expectancy with vs
  without the anti-thrash bundle.

*Pre-committed read (decided before any number):*
- **Anti-thrash is inert here** (turnover / Calmar essentially unchanged) ⇒ confirms `03` (no whipsaw to
  suppress); leave it off. *(The structurally-expected outcome.)*
- **Anti-thrash materially cuts turnover AND holds/improves Calmar** ⇒ **authorizes a SEPARATE future
  amendment** that adds it as a gated axis with its own K. It does **not** change the candidate this run.

*Guard:* report-only; the locked OOS candidate uses the §4 levers only; **adds 0 to K**; a positive read
triggers *new* pre-registered work, never a quiet swap.

---

## 6. Pre-committed acceptance rule (binding — identical gates to `00` §6 / `04` §6, nothing relaxed)

A config becomes the **single locked OOS candidate** iff **all** hold on full DISCOVERY:

1. **§6.1 cost survival:** pessimistic-cost Calmar ratio vs **Nifty 50 TRI ≥ 1.0** (the primary gate).
2. **§6.2 concentration — SKEW-AWARE** (the `09`/`10` random-subset gate, exactly as `00`/`04` §6.2): median
   Calmar ≥ 0.70 of base **and** p5 ≥ 0.50 of base, **≥ 25 rotating distinct P&L contributors**. Classic
   drop-top-10 reported as a contamination guard, **diagnostic not gating** (a trend book is *meant* to ride
   winners; pass-skew/fail-classic = "conditional", never "validated").
3. **§6.3 plateau:** the candidate and its §4 neighbors (±1 step on **`atr_mult`** {3,4,5} **and** on
   **`neutral_fraction`** {0.5,0.75}) stay ≥ **85%** of the candidate's base Calmar — a region, not a lone
   peak. Cadence robustness reported (both levels), not a plateau axis (binary).
4. **Deployment bar (= `08` §2b / `00` §6.4):** beats Nifty 50 TRI on **base-cost Calmar** with **maxDD ≤
   100%** of the benchmark.
5. **§6.4 subperiod** reported, **not** gating (window-fragility demoted, per the whole v2→v4 arc).

**Tie-break (if ≥ 2 configs clear 1–4 on a plateau):** pick the **lowest-realized-turnover** one (the program
thesis is turnover; the cheaper-to-run book is the honest pick — mirrors v3 `05` §5).

**Null outcome (pre-accepted close):** if **0** configs satisfy 1–4, the turnover lever does **not** rescue
the thin trend edge; the v4 family is **permanently and finally closed**, and **v4-FINAL_OOS is NOT touched**.
A null is the honest finding that the trend edge is structurally too thin for this cost regime on this market
— **not** a prompt to add a lever, loosen a threshold, or re-touch OOS (§1). Redirect per §8, never re-grid.

---

## 7. K / deflation, splits, one-shot OOS

### 7.0 K-counting standard (pre-committed BEFORE any result — binding)

A **DSR trial** = one distinct **return-generating hypothesis** evaluated on DISCOVERY, counted under these
five rules (chosen now, before a number is seen, so the count is not motivated reasoning):

- **(R1) Cost level is an evaluation assumption, not a trial — ×1, not ×2.** Base and pessimistic cost score
  the *same* strategy under two cost models; no best-of selection happens across them (pessimistic IS the
  gating metric). The prior v4 docs' `× 2 costs` multiplier was an over-charge and is corrected here.
- **(R2) Provably rank-identical configs count once.** E.g. RS ≡ MOM (a per-day-constant cannot reorder a
  cross-section — confirmed in V4.4 §3): one trial, not two.
- **(R3) A re-run of an already-counted config (parity/anchor) counts 0.** E.g. the V4.4 ADV anchor
  re-derived a V4.1 cell exactly.
- **(R4) Non-gating diagnostics count 0** (footprint, §6 selection-quality, §5 deployment-as-diagnostic,
  anti-thrash) — already honored across v4.
- **(R5) Distinct levels on a *gated* axis EACH count — no free reduction.** You genuinely pick best-of over
  them. This is the honesty clamp: do not collapse the 3-point `atr_mult` axis to 1 by argument. To justify a
  count below the rule, compute the **effective number of independent trials empirically** (López de Prado:
  from the cross-correlation of the trial PnL streams) and report deflated Sharpe at *that* N **alongside**
  the config-count N — never instead of it.

### 7.1 Corrected v4 ledger and this program's K

- **Carried v4 K = 4**, not the previously-logged 12. Re-derived under §7.0: V4.1 = **3** (exit-tightness
  T1/T2/T3, ×1 cost); V4.4 = **+1** (MOM only — ADV = anchor → 0 (R3); RS ≡ MOM → 0 (R2); §5 deployment =
  diagnostic → 0 (R4)). The original `00`/`04` ledger counted config×cost (R1 over-charge) and counted ADV/RS
  as fresh trials — both corrected. The original signed numbers stand in `00` §6.4 / `04` §12.6 with an
  append-only K-accounting correction note; this is the figure that carries forward.
- **K** continues from the corrected v4 ledger (**4**) and accrues each *new* Stage-1/Stage-2 **config** (not
  config×cost) under §7.0. At OOS report **raw Sharpe, K (≈13), deflated Sharpe** (`validation.deflated_sharpe`)
  **+ PBO** (`pbo_cscv` over DISCOVERY walk-forward windows; no fold reaches FINAL_OOS), and the empirical
  effective-N (R5) beside it. **The deflation penalty is real but ~halved vs the old config×cost convention —
  fixing the over-charge does NOT close the ~2.5× §6.1 gap; a marginal raw edge still deflates to ≤0.**
- **DISCOVERY** = `validation.DISCOVERY (2018-02-06 → 2023-06-30)` — all of §3–§6 lives here.
- **v4-FINAL_OOS** = `validation.FINAL_OOS (2023-07-01 → 2026-06-12)`, **pristine** (V4.1/V4.4 never spent it)
  — touched **exactly once**, only after a single §6-locked candidate exists, **never** on the null.
  Byte-for-byte locked candidate through the v4 engine, once, no re-tuning.
- **Contamination caveat (inherited, `00` §8):** an OOS pass is "in-sample-clean for v4, macro-contaminated
  for the researcher" ⇒ the truly clean test remains a **forward paper probation** (the `11` species).

---

## 8. Honest prior — the bar is steep, NULL is the most likely outcome (Rule 12)

Read **before** sign-off, not after a result:

- **The §6.1 gap is large and the leaks are partly already spent.** MOM's pessimistic ratio is **0.39**; the
  bar is **1.0** (~2.5× to go). The selector lift (+0.10 Calmar) and the deployment lift (0.179→0.281) are
  *already in* those numbers — they are not fresh headroom. Turnover reduction must do most of the remaining
  work, and **widening the exit trades cost for give-back** (ambiguous net). A ~40% turnover cut roughly
  halves cost (~7%→~3.5% of capital) and could ~double net trading P&L — *if* give-back doesn't eat it. That
  is a genuine maybe, not a likely pass.
- **Four prior programs hit the "buy-the-index-fund" wall** (v2 floor, v3 momentum-only, v3 Track-B, v4
  swing). The base rate for "one more lever clears the costed bar" is low.
- **Deflation at K≈13 (corrected count, §7.0) is still material** (cf. `10`: raw Sharpe positive but
  deflated ≤ 0 ∀K even at the honest lower K — the killer was a thin *raw* edge, not a huge K). Even a
  DISCOVERY pass may deflate away. Halving the K over-charge does not rescue a ~2.5× gross gap.
- **Why run it anyway:** (a) it is the **first and only** attack on the constraint V4.4 *proved* is binding,
  with a lever class the program has **never** tested; (b) the edge is *real* (proven in V4.4), so "can we
  keep more of it past cost?" is well-posed and falsifiable; (c) it is cheap (6 Stage-1 configs, everything
  else frozen) and the null is pre-accepted. **If it nulls, v4 closes permanently** and the honest redirect
  is *not* another knob but a different lever the program cannot supply: a **cheaper execution regime**
  (lower per-trade cost — instrument/venue/lot economics) or a **different premise**. Record that redirect in
  the close; do not re-grid.

---

## 9. Lookahead guardrail (inherited from `00` §9 / `04` §9 + the new-lever items)

All `00` §9 landmines apply unchanged. New-lever-specific:
- **Weekly cadence uses completed weeks only.** Decision day = the completed week's last trading day (W-FRI
  as-of); no in-progress week is ever evaluated (same discipline as the weekly-MACD entry input). The
  catastrophic floor still checks **daily** (a risk control may run more often, never less).
- **Wider ATR trail uses completed-`D` data** (anchor = max close through D; ATR20 through D). No in-progress
  bar, no intraday high.
- **min-hold / cooldown** key off entry/exit **dates already realized** (no forward reference).
- **Adjusted series only**; `instrument_id` identity (`06`/`07`) so a succession is not a fake trend reset
  or a fake cooldown.

---

## 10. Locked commitments (Arafat — sign to flip DRAFT → LOCKED, AFTER the §0 ruling)

Confirm or redline each. **§0 must be ruled first** — if §0 = "decline," do not sign.

1. **§0 reopen ruled = explicit deviation** (NOT "genuinely new information") — recorded against the
   `00` §8 / `04` §8 "no new knobs" close (the `10` §13 species), scoped to the turnover lever class (new)
   **+** the already-`04`-§5-pre-authorized deployment axis (carried). *(Ruled 2026-06-25; see §0.)*
2. **K carries from v4 (corrected to 4 under the §7.0 standard, not 12), not reset**; the §7.0 counting
   standard (cost ×1; identical/anchor/diagnostic configs → 0; gated levels each count) is pre-committed;
   one-shot v4-FINAL_OOS inherited pristine (§1, §7).
3. **Only the §3 four change** — exit width, cadence, deployment (gated); min-hold/cooldown (diagnostic).
   MOM frozen (recorded decision, not re-swept); entry/regime-score/U/target_positions/floor/₹3.5L
   byte-frozen (§1).
4. **Grid** — the §4 grid (`atr_mult`{3,4,5} × cadence{daily,weekly} at the candidate `neutral_fraction`=0.75
   in Stage 1; the 0.5 deploy plateau-neighbor in Stage 2); two-stage screen → battery; lowest-turnover
   tie-break; no level added after results.
5. **Min-hold/cooldown = non-gating diagnostic only** (adds 0 to K; a positive read authorizes a *separate*
   future amendment) (§5).
6. **Acceptance rule** — `00`/`04` §6 gates verbatim (§6.1 ratio ≥ 1.0; §6.2 skew-aware; §6.3 plateau over
   atr_mult+neutral_fraction; deploy bar maxDD ≤ 100%; §6.4 diagnostic); pre-accepted null = v4 family
   permanently closed, FINAL_OOS untouched, redirect-not-regrid (§6, §8).
7. **Honest prior accepted** — §6.1 gap ~2.5× with leaks partly spent; K≈13 deflation (corrected count)
   is still material and does not close that gap; NULL is the most likely outcome; a null permanently
   closes v4 (§8).

> **Signed:** ☑ Arafat — 2026-06-25 (DRAFT → **LOCKED**). No engine/selector code written before this signature.

---

## 11. Execution (cold-session runnable — NOT STARTED until §10 is signed)

> No stage begins before §10 is LOCKED. DISCOVERY only until a candidate is locked; v4-FINAL_OOS spent
> exactly once, only on a §6-locked candidate, never on the null. Honor the token budget (Rule 6); update
> Status + a session log per stage; do not mark Done if anything was skipped (Rule 12).

### V4.7 — Lever implementation + Stage-1 turnover cost screen on DISCOVERY
- **Status:** ✅ **DONE 2026-06-25** → **1/6 §6.1 survivor — V4.8 AUTHORIZED (NOT a null), but the survivor is
  fragility-suspect (see the session log). The FIRST §6.1 pass in the entire v4 family.**
- **Do:** (a) additive `SwingConfig` + engine extensions — `decision_cadence` ("daily"/"weekly", default
  "daily" ⇒ byte-identical), `min_hold_td`/`reentry_cooldown_td` (default 0 ⇒ byte-identical); `atr_mult`
  and `neutral_fraction` already exist. Weekly cadence implemented in `step_day` per §3.2 (skip configured
  exit + entry scan off-decision-days; floor + fills + MTM + anchor still daily); no-lookahead tested
  (future bars / mid-week days leave a decision-day's actions unchanged). (b) Run the §4 Stage-1 screen (6
  configs at the candidate `neutral_fraction`=0.75 × base+pess) + the §5 anti-thrash diagnostic + the `03`
  forensic + the V4.4 deploy-0.5 anchor + the ADV anchor (parity, R3 → 0 to K). Log to the v4 ledger.
- **Done-criteria:** new levers deterministic + no-lookahead tested; the V4.4 MOM/ATR-3.0/daily/deploy-0.5
  anchor cell — run alongside Stage 1 as parity (R3 → 0 to K) — reproduces the V4.4 number (base Calmar
  ~0.179), while Stage-1 proper runs the 6 cells at the candidate `neutral_fraction`=0.75; §6.1 survivors
  identified; no battery/OOS in this stage.

#### V4.7 session log (2026-06-25)
**Engine (additive, default byte-identical):** `SwingConfig` gained `decision_cadence` ("daily" default),
`min_hold_td`/`reentry_cooldown_td` (0 default). `engine.py`: weekly cadence in `step_day` (off-decision days
skip the configured exit + entry scan; fills/MTM/anchor/−25% floor stay daily), decision days = last trading
day of each ISO week computed over the FULL calendar (no-lookahead, §9); `_past_min_hold`/`_in_reentry_cooldown`
gated behind their config flags; `last_exit` recorded on full-exit. `_exit_reason` took an
`allow_configured_exit` flag (floor always runs). **44 prior swing_v4 tests still green (additive proof); +7
new `test_v47_levers.py` (decision-day map, daily-byte-identical, weekly defers configured exit / floor still
daily, weekly no-lookahead, min-hold blocks configured-not-floor, cooldown suppress-then-allow).** Screen =
`app/swing_v4/v47_turnover_screen.py`; report `backend/reports/v47_turnover_screen.txt` (gitignored).

**Parity (R3 → 0 to K):** MOM-0.5 anchor base Calmar **0.179** (V4.4 exact, |Δ|=0.000); ADV anchor base **0.083**
/ pess ratio **0.11** (V4.1 exact). Engine integrity confirmed — the new levers are byte-identical on the
frozen path.

**Stage-1 §6.1 grid (neutral_fraction=0.75, pessimistic-cost Calmar ratio vs Nifty 50 TRI; ≥1.0 clears):**

| atr | cadence | base Calmar | maxDD | turn% | medHold | expectancy | payoff | §6.1 ratio | |
|---|---|---|---|---|---|---|---|---|---|
| 3.0 | daily | 0.281 | 34.0% | 829 | 46d | +2.18% | 2.54 | 0.68 | FAIL |
| 3.0 | weekly | 0.271 | 21.9% | 511 | 56d | +1.94% | 2.39 | 0.66 | FAIL |
| 4.0 | daily | 0.194 | 26.2% | 544 | 70d | +2.20% | 1.99 | 0.45 | FAIL |
| **4.0** | **weekly** | 0.130 | 31.1% | 387 | 80d | +2.32% | 2.55 | 0.36 | FAIL ← §4 candidate |
| **5.0** | **daily** | **0.474** | 28.0% | 403 | 92d | +9.34% | 3.96 | **1.27** | **PASS** |
| 5.0 | weekly | 0.408 | 34.5% | 277 | 119d | +11.58% | 4.33 | 0.42 | FAIL |

**Result: 1/6 clears §6.1 → atr 5.0 / daily (ratio 1.27).** The §2 thesis WORKED at the widest exit: the 5×
trail cut turnover (829%→403% daily) **and** lifted expectancy (+2.18%→+9.34%, payoff 2.54→3.96, avgWin
+20.5%→+48.8% — it rides winners), so the trail-vs-give-back trade came out *favorable* at 5×. **This is the
first §6.1 pass in the whole v4 family.**

**⚠ Three loud fragility flags carried to V4.8 (Rule 12 — do NOT over-read the 1.27):**
1. **The pre-registered §4 candidate (atr 4.0 / weekly) FAILED (0.36).** The survivor is a *different* cell.
   Legitimate under §4 ("identify §6.1 survivors" — any clearer carries), but it is not the a-priori favorite.
2. **Lone peak on the `atr` axis** — base Calmar 0.281 → 0.194 (trough) → **0.474**: non-monotonic and jagged.
   The §6.3 plateau (candidate ±1 step ≥ 85% of base) will almost certainly FAIL — the atr-4.0/daily neighbor
   (0.194) is 41% of 0.474. This is the `10` §6.3 lone-peak species, *predicted* before V4.8 runs it.
3. **Cadence crater** — atr 5.0/daily ratio **1.27** vs atr 5.0/weekly **0.42**: a clean pass flips to a deep
   fail on the binary cadence axis. Per §6.3 a config that clears one cadence and craters the other is fragile
   — weighs against locking. Combined with (2), the survivor sits at the **grid boundary** (atr=5.0), itself a
   tell that the response is not a plateau.

**§5 anti-thrash diagnostic (NON-GATING, 0 to K):** candidate atr4/weekly ± (min_hold=10, cooldown=10):
turnover 387%→382%, Calmar 0.130→0.147 (<10% turnover cut) ⇒ **INERT** — confirms `03` (median hold ~80d here,
no whipsaw to suppress). Pre-committed read: leave it off; no separate amendment authorized.

**K:** +6 new Stage-1 configs (cost ×1, R1; anchors + anti-thrash = 0). Carried v4 K = 4 ⇒ **K so far ≈ 10**
(Stage 2 adds the 0.5 deploy plateau-neighbor → ≈13 at OOS, per §7.1). **v4-FINAL_OOS untouched (pristine).**

**Verdict: V4.7 DONE — 1/6 §6.1 survivor (atr 5.0 / daily) → V4.8 battery authorized, NOT the pre-accepted
null.** But V4.8 enters with the §6.3 plateau failure essentially pre-diagnosed (flag 2) and a cadence-crater
fragility (flag 3); the honest expectation is that the survivor does not survive the full §6 battery. No grid
level added, no threshold loosened, no OOS peek.

#### Pre-V4.8 mechanism diagnostic (2026-06-25) — "edge vs lottery" on the atr-5.0/daily survivor

**Non-gating, 0 to K, base cost, FINAL_OOS untouched** (`v47_concentration_diagnostic.py`; Arafat-requested
before authorizing the V4.8 battery — `00` §6 / `05` §5 diagnostic species). Question: is the pess-ratio 1.27
a broad trend edge, or a handful of lottery-ticket compounders the wide 5× trail happened to not cut off?

**Verdict: it is a real trend edge whose entire payoff is one multi-year compounder.** Decisive across every cut:
- **Single-name dependence:** the biggest winner (Adani Total Gas, entry 2020-10-26, **+1161% over 826 calendar
  days**) is **₹229,647 of ₹265,012 total net P&L = 86.7% of everything the survivor made** over 5.4 years.
- **Concentration:** top 5 trades = **141%** of net P&L, top 10 = 174%, top 20 = 205% (>100% ⇒ the other ~170
  trades net negative; a few names carry the book). Winners-only Gini 0.76. Median trade **−6.3%**, mean
  **+9.3%** (the 15-pt mean≫median gap = one giant right tail). Win rate 35%.
- **vs atr 3.0 (matched (iid,entry_date), 141 common entries):** going 3×→5× made **70% of trades *worse***
  (wide stop gives back open profit), only **4%** became big winners (Δ≥30pts). Median Δret **−4.25%**; the
  mean is positive *only* because of ATGL's +762-pt swing. **Top 5 improvements = 166% of all added edge**
  (ATGL, SRF, DIVISLAB, ADANIPORTS, NATIONALUM — three were *losses* at 3× that 5× held into a recovery).
- **Mechanism of the §6.3 lone peak (flag 2), now explained:** atr=5.0 is the *only* cell wide enough to not
  trail ATGL out (3× clipped it at 165 d / +400%). The lone peak and the single-name dependence are the **same
  fact**; the 826-day hold means the wide trail converted the strategy into buy-and-hold-the-one-rocket (also
  why turnover fell 829%→403%).

**Consequence for V4.8 (per Arafat 2026-06-25):** the mechanism is *coherent* (trend-following's job is to let
exceptional businesses compound), so this is **less** "suspicious random parameter" than first feared — but it
makes **§6.2 concentration co-equal with §6.3** as the make-or-break gate, and a strategy that is 87% one name
is a near-certain §6.2 FAIL by construction. **Decision: run V4.8 as the FULL §6 battery exactly as specified**
(not a §6.2-only shortcut), accept the verdict including complete rejection. **Add a post-V4.8 leave-top-k-out
fragility test** (remove top 1/2/5/10/20 trades → recompute CAGR — a fragility *demonstration*, non-gating, 0
to K, NOT a deployment rule). **Preserved finding if v4 closes:** *the exit mechanism mattered far more than
the entry mechanism.* **Future (NEW prereg, NOT a v4 extension):** adaptive / gain-scaled exits (a trail that
widens as unrealized gain grows) — its own pre-registration if ever pursued, never folded into v4.

### V4.8 — Stage-2 battery + deployment plateau-neighbor + §6 acceptance (only on §6.1 survivors)
- **Status:** ✅ **DONE 2026-06-26** (`v48_battery.py`, full §6 battery on atr5/daily/0.75) → **NULL CLOSE —
  failed §6.2 AND §6.3 → the v4 family is PERMANENTLY and FINALLY closed; v4-FINAL_OOS NEVER touched.**

**Gate-by-gate (base Calmar 0.474 | Sharpe 0.79 | maxDD 28.0% | CAGR 13.29% | turnover 403%):**
- **§6.1 cost survival — PASS** (re-confirmed): C_strat 0.438 / C_nifty50 0.346 = **ratio 1.27** ≥ 1.0.
- **§6.2 skew-aware concentration — FAIL** (the binding kill, exactly as the pre-V4.8 diagnostic predicted):
  - (a) random-subset retention **FAIL** — median **105%** (≥70% bar) BUT p5 **43%** < 50% bar. The median says
    dropping 10 *random* names usually doesn't hurt (you often shed losers); the **p5 tail guard** says that in
    the worst 5% of draws — the ones that remove ATGL/the few compounders — Calmar collapses to 43% of base.
    The skew-aware tail bar caught the single-name fragility the median is designed to tolerate. **This is the
    test working as designed**, not a threshold technicality.
  - (b) contributor rotation **PASS** — 58 distinct top-10/yr (≥25). Winners rotate year-to-year, but rotation
    does NOT rescue the tail-fragility (a different gate).
  - classic drop-top-10 realized P&L (DIAGNOSTIC, non-gating): retention **−16%** — removing the top 10 names
    by realized P&L drives Calmar *negative*. Pass-skew is moot here (random-subset already failed); reported.
- **§6.3 plateau — FAIL** (lone peak on the `atr` axis confirmed, as flag 2 pre-diagnosed):
  - grid base Calmar — atr3 {0.50→0.179, 0.75→0.281}; atr4 {0.50→**0.029**, 0.75→0.194}; atr5 {0.50→**0.518**,
    0.75→**0.474**=candidate}.
  - ±1-step neighbors of the candidate: **atr 4.0/0.75 = 0.194 = 41% of base → FAIL**; atr 5.0/0.50 = 0.518 =
    109% → PASS. The **deployment axis is robust (0.5 arm even beats the candidate)**, but the **exit-width axis
    is a lone spike** (atr4 craters) — one failed neighbor ⇒ §6.3 FAIL.
- **deploy bar — PASS**: strat 0.474 vs Nifty50 TRI 0.346, maxDD ratio **0.73** ≤ 1.0. (Beats the index on the
  bull window — but that is not enough when §6.2/§6.3 fail.)
- **§6.4 subperiod (DIAGNOSTIC, non-gating) — 1/3 positive**: Pre-COVID chop **−0.480**, Post-COVID bull
  **+5.767**, Rate-hike correction **−0.222**. *All* the edge is the one post-COVID bull window (where ATGL
  ran); the other two regimes are net-negative — independent corroboration of the single-window/single-name story.

**§7 deflation context (reported, not a gate):** raw Sharpe 0.786 → **DSR K13 = +0.025** (barely positive —
deflation-marginal even before the §6 fails); PBO (CSCV 6×8) **0.47** (≈ coin-flip overfitting). K added this
run = **+3 under §7.0** (the deploy-0.5 plateau arm: atr{3,4,5}/0.50; the 0.75 cells + candidate are V4.7
re-runs → R3 = 0; §6.4 subperiods diagnostic → R4 = 0; §6.2 perturbations / PBO reruns resample one config → 0).
The naive ConfigLedger logged 9 entries, but the §7.0-correct new-trial count is **+3 ⇒ carried 10 ⇒ K ≈ 13 at
OOS** (matches §7.1's estimate; cf [[k-counting-standard-no-overcharge]]).

**§5 anti-thrash on the survivor (NON-GATING, 0 to K) — INERT again:** turn 403%→403%, medHold 92d→92d,
Calmar 0.474→0.483 (<10% turnover cut) ⇒ confirms `03`; no separate amendment authorized.

**Leave-top-k-out fragility DEMONSTRATION (the Arafat-requested test — NON-GATING, 0 to K, P&L attribution not
a re-simulation):** the edge vanishes at **k=2**.

| remove top-k trades | remaining net P&L | attribution CAGR |
|---|---|---|
| 0 (full book) | ₹265,012 | **+11.02%** |
| 1 (just ATGL) | ₹35,365 | +1.80% |
| 2 | −₹9,274 | **−0.50%** (net-losing) |
| 5 | −₹108,944 | −6.68% |
| 10 | −₹194,853 | −14.00% |
| 20 | −₹276,873 | −25.20% |

Removing the **single** best trade (ATGL) collapses CAGR 11.0%→1.8%; removing the top **2** turns the book
net-losing. This is the quantified answer to "how fast does the edge disappear?": **immediately.**

**VERDICT — NULL (failed §6.2 + §6.3, two independent grounds).** The turnover/wide-exit lever produced a
genuine trend edge, but one whose entire payoff is a single multi-year compounder (ATGL) — too concentrated to
clear the skew-aware tail guard (§6.2 p5) and sitting on a lone `atr` spike (§6.3). Per `05` §6 pre-accepted
null: **the v4 family is PERMANENTLY and FINALLY closed; v4-FINAL_OOS is NOT touched (V4.9 N/A); no lever added,
no threshold loosened, no OOS peek.** Keeper finding: *the exit mechanism mattered far more than the entry
mechanism.* Any adaptive/gain-scaled-exit idea is a NEW pre-registration, never a v4 continuation (§11 pre-V4.8 note).

### V4.9 — One-shot v4-FINAL_OOS + §10-of-`00` verdict (only on a locked candidate)
- **Status:** ⬛ **N/A — NOT RUN (correctly).** V4.8 produced no §6-passing candidate (NULL), so v4-FINAL_OOS
  is **NEVER touched** and stays pristine across the entire v4 family. There is nothing to lock; there is no OOS.

---

## Exit criteria
- [x] §0 reopen ruled by Arafat — **explicit-deviation** (2026-06-25).
- [x] §10 locked by Arafat (DRAFT → LOCKED, 2026-06-25).
- [x] V4.7 — levers built (no-lookahead tested, V4.4-cell parity) + Stage-1 turnover screen on DISCOVERY
      (2026-06-25); **1/6 §6.1 survivor = atr 5.0 / daily (ratio 1.27)**, fragility-flagged; anti-thrash
      diagnostic (INERT) + MOM/ADV anchors (exact parity) recorded; ledger +6 (K so far ≈ 10).
- [x] Pre-V4.8 mechanism diagnostic (2026-06-25, 0 to K) — "edge vs lottery": **real trend edge, but 87% of
      net P&L is one name (ATGL +1161%)**; §6.2 now co-equal with §6.3 as the gate. Decision: run V4.8 FULL
      battery + a post-battery leave-top-k-out fragility test (non-gating).
- [x] V4.8 — Stage-2 FULL §6 battery + deployment plateau-neighbor + leave-top-k-out on the atr-5.0/daily
      survivor (2026-06-26) → **NULL: §6.1 PASS (1.27) but §6.2 FAIL (random-subset p5 43%<50% — single-name
      tail) AND §6.3 FAIL (atr4/0.75 neighbor 41%<85% — lone peak); deploy PASS; §6.4 1/3+; DSR K13 +0.025;
      leave-top-k edge gone at k=2.** v4 family PERMANENTLY closed; ledger +3 under §7.0 ⇒ K ≈ 13.
- [x] V4.9 — **N/A (correctly not run):** no §6-passing candidate ⇒ v4-FINAL_OOS NEVER touched, stays pristine.
