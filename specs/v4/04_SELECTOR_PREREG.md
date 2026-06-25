# v4 / 04 — Return-Informed Selector: Pre-Registration

> **Status: V4.4 DONE 2026-06-25 → NULL CLOSE → v4 swing family FULLY CLOSED as a research note.** 0/3
> selectors clear §6.1 (MOM/RS pessimistic ratio 0.39, ADV 0.11; all < 1.0 vs Nifty 50 TRI). The candidate
> **MOM more than doubled base Calmar (0.083 → 0.179)** — the §6 edge-discarding diagnosis was correct, the
> return-informed selector *does* capture per-name edge the liquidity rank threw away (expectancy +0.72% →
> +1.98%, payoff 2.21 → 2.71) — **but it is not enough**: ~800% turnover keeps the costed Calmar far below
> the index bar. **v4-FINAL_OOS NEVER touched (pristine); V4.5/V4.6 N/A; K=6 this run on top of the carried 6.**
> Two pre-authorized forward leads recorded (NOT acted on this run): RS≡MOM confirmed (§3 identity, no new
> info), and the §5 deployment diagnostic read **DEPLOYMENT IS A REAL LEVER** (D_more lifts Calmar 0.179→0.281
> with maxDD ≤ benchmark) — that authorizes a *separate future* deployment-axis prereg with its own K. See §12.
>
> **Status (prior): LOCKED — 2026-06-24 (Arafat). §10 signed (all 7 commitments).** V4.4 execution authorized;
> no stage began before this lock. This prereg is the **separate, pre-authorized** follow-on that `00` §6 + `00` §13 (V4.1) and the
> `03` trade-level forensic licensed: the V4.1 §6 selection-quality diagnostic read **edge-discarding**
> (the top-15-by-`adv_20` liquidity selector throws away edge — random-15 and the uncapped book both beat
> it), and the forensic confirmed the V4.1 edge is **real but thin** with **selection as the single
> highest-leverage lever**. This doc freezes — *before any new return number* — the one structural change
> it authorizes (the **selector**), its small grid, the binding acceptance rule, the K/deflation
> accounting, and the one-shot OOS protocol. It is the v1 anti-HARKing discipline applied a second time.
>
> **Owner:** Arafat. **Created:** 2026-06-24. **Depends on:** `00_SWING_PREREG.md` (LOCKED + Amendment 1),
> `02_SWING_ENGINE.md` (engine built), `03_V41_FORENSIC.md` (the diagnostic that motivates this).
>
> **What this doc is NOT:** not a re-open of the closed V4.1 (the `adv_20` engine stays closed as a
> research note), not an engine spec, not a license to touch any frozen `00` knob other than the selector.

---

## 0. Why this exists (the motivating mechanism — `03`)

The v4 daily-swing family closed NULL at V4.1 (`438d9a1c`): 0/3 exit configs cleared §6.1. The `03`
forensic dissected *why*, and the finding is specific:

- **The edge is real but thin, not broken.** The candidate (T3, ATR-3× trail) has **positive** per-trade
  expectancy (+0.72% net), a trend payoff ratio of **2.21** (avg win +16.6% vs avg loss −7.5%), and a
  34% win rate — the textbook "cut losers, ride winners" signature. It fails the §6.1 Calmar bar because
  the per-trade edge is *small* relative to friction + de-deployment, not because the signal is noise.
- **Selection is the highest-leverage lever.** The edge is per-*name*. The engine currently picks which
  firing names to hold by `adv_20` (liquidity — return-blind), and the V4.1 §6 diagnostic found that
  selector **edge-discarding**: `B_liquid` Calmar 0.083 < 0.85 × `B_random` median 0.138, and below
  `B_all` 0.090. Two independent diagnostics agree we leave edge on the table at selection time.

The pre-authorized response (`00` §6, verbatim): *"authorizes a separate future amendment that introduces
a return-informed selector as a budgeted, §6.3-plateau-tested grid axis carrying its own K."* This is that
amendment, written as its own prereg so the commitment is explicit and signable.

> **Plain-language note (Rule 13):** today the book, when more names qualify than it has slots (15), keeps
> the *most liquid* ones. That's like a recruiter who, facing 46 qualified applicants for 15 jobs, hires
> the 15 with the shortest commute. This prereg tests hiring instead by a **return-informed** rank — the
> 15 with the strongest recent trend — while changing nothing else about the engine.

---

## 1. Scope discipline (the anti-HARKing line — binding)

- ✅ **K CARRIES from the v4 family (currently 6); it does NOT reset.** This is **not** an independent
  family: it is the *same* engine, entry rule (§3.3 of `00`), exit (Type-3 ATR trail), regime score, and
  universe — with **one axis changed** (the selector). The v4 economic prior is unchanged, so the 6 trials
  already spent on this engine carry their full false-discovery weight, and the new selector trials
  accumulate **on top** (§6). *(Confirmed by Arafat 2026-06-24.)*
- ✅ **One-shot OOS inherited, still pristine.** v4-FINAL_OOS was **never** touched (the V4.1 null forbade
  it), so this program inherits the single, unspent v4-FINAL_OOS shot (§7). Spending it is the only path to
  "validated, deployable."
- ❌ **Only the selector changes.** Entry (the 4 conditions), exit (Type-3 ATR 3× — **frozen**, the
  forensic settled the exit/turnover question), the 5-factor regime score, buckets, `target_positions=15`,
  the `stable_universe` U=200, `₹3.5L`, and all indicators stay **byte-frozen at `00`/Amendment-1**. The
  ATR multiple is **frozen at 3.0** (not re-plateaued — it was never the binding constraint).
- ❌ **Selector family is a-priori, not mined.** The selector rankers (§3) are **standard, conventional**
  momentum/relative-strength constructions chosen *because* they are textbook, **not** because they
  backtested well (no backtest has been run). The lookback is frozen at the conventional 126 td (≈6 months)
  with {63, 252} as the §6.3 plateau neighborhood — not tuned.
- ❌ **No grid expansion after results.** The selector set and its plateau neighbors are fully enumerated
  in §3/§4 now. No selector, lookback, or axis is added after seeing a number.
- ❌ **No deployment knob bet on the gate.** The "deploy more capital" idea is registered as a **non-gating
  diagnostic only** (§5) — it adds 0 to K and cannot become a candidate in this run (see §5 rationale).
- ❌ **No FINAL_OOS peek** before a single §6-locked candidate exists; **never** on the null (§7).

---

## 2. The goal (unchanged from `00` §2)

Identical bar to `00` §2 — **no relaxation.** Risk-adjusted outperformance of the cheap passive
alternative, net of realistic costs:
- **Primary bar:** beat **Nifty 50 TRI** on **pessimistic-cost Calmar ratio ≥ 1.0** (§6.1) and on
  **base-cost Calmar with maxDD ≤ 100%** of the benchmark (deployment bar).
- Nifty200 Mom30 TRI reported as a reference only.
- A config that merely *matches* the index is the **"buy the index fund"** research-note close.

**The edge thesis for this program specifically:** the firing set has return *dispersion* — some qualifying
names carry much more of the trend edge than others — and a return-informed rank captures it where the
liquidity rank discards it. If the firing names are roughly interchangeable, the selector cannot help and
this closes NULL (see §8 honest prior — this is the most likely outcome).

---

## 3. The change: the selector axis (frozen on sign)

The **only** new degree of freedom. When more than `target_positions=15` names fire on day `D`, the engine
must choose which 15 to hold. All rankers are **point-in-time** (computed on data through `D` close, used
for the `D+1` open fill — §9 of `00`, no lookahead) and operate on the **already-frozen firing set** (the
4 entry conditions and the `stable_universe`/₹5cr floor are unchanged — the selector only *ranks*, it never
*adds* a name that did not fire).

| Selector | Rank firing candidates by (desc) | Role | Why a-priori |
|---|---|---|---|
| **MOM** (candidate) | trailing **126-td total return** of the adjusted close through `D` | the registered candidate | 6-month momentum is the single most conventional return-informed ranker; chosen for being textbook, not tuned |
| **RS** (comparator) | candidate 126-td return **−** Nifty 50 126-td return (relative strength / excess) | comparator | tests whether *relative* momentum beats *absolute*; standard cross-sectional RS construction |
| **ADV** (baseline) | `adv_20` (the closed V4.1 engine) | baseline / gap | the liquidity selector this program aims to beat — re-run so "return-informed beats liquidity" is measured, not assumed |

- **Oversubscription only.** On a day with ≤15 firing names the selector is inert (it ranks a set that
  fits) — identical book to V4.1 on those days. The selector only bites when the book is oversubscribed
  (the footprint says that is most bull days).
- **Ties / missing lookback:** a name without a full 126-td history (just IPO'd into the universe) sorts
  **last** (never preferentially picked on thin data — a no-lookahead/no-thin-data guard). Exact ties break
  on `adv_20` (the frozen neutral tiebreak), so the selector is fully deterministic.
- **Exit-choice analogue (the no-silent-swap rule):** MOM is the registered candidate. If MOM fails §6 but
  RS (or even ADV) passes, that is a **reported finding, not a silent swap** — promoting a comparator is a
  fresh registration decision, recorded explicitly (mirrors `00` §6).

---

## 4. The search grid (small, fully enumerated — decided now)

Mirrors `00` §5 (two-stage). Everything except the selector axis is frozen.

| Axis | Frozen candidate | Enumerated alternatives (the ONLY ones) | Role |
|---|---|---|---|
| **Selector** | **MOM (126-td)** | RS, ADV (baseline) | the new axis (this prereg) |
| Selector lookback | **126 td** | 63, 252 | §6.3 plateau (confirms the lookback is not a hidden knob) |
| `target_positions` | **15** | {13, 15, 17} | §6.3 plateau (carried from Amendment 1) |
| Exit / ATR mult / regime tier | **Type 3 / 3.0 / 5-factor** | — (FROZEN — not re-opened) | settled by `00` + `03` |

- **Stage 1 — cost screen:** the 3 selectors (MOM, RS, ADV) on full DISCOVERY at **base + pessimistic**
  cost, ₹3.5L whole-share. Record turnover, base/pessimistic Calmar, maxDD, win rate, avg hold, §6.1 ratio,
  **and the `03` per-round-trip + exit-attribution forensic** (so we see *how* a better selector changes the
  trade population, not just the headline). Log each selector × cost level to the v4 ledger (K accrues).
- **Stage 2 — battery (only selectors clearing §6.1):** §6.2 skew-aware / §6.3 plateau (over the selector
  lookback {63,126,252} **and** `target_positions` {13,15,17}) / §6.5 capacity, + §6.4 subperiod diagnostic.
  Apply the §5 acceptance rule.

**K estimate (honest):** Stage 1 = 3 selectors × 2 costs = **+6**; Stage 2 on a single survivor ≈ **+4**
(2 lookback + 2 `target_positions` neighbors, base cost). **Carried 6 + ~10 new ⇒ K ≈ 16+** at OOS. The
skew-aware §6.2 and §6.5 resample one config (no new trials). Deflation headwind is real and acknowledged
(§6, §8).

---

## 5. The deployment question — registered as a NON-GATING diagnostic (adds 0 to K)

Arafat's second forensic takeaway — *the regime overlay holds the book at ~62% mean deployment, suppressing
CAGR* — is **correct on the facts** but is **not** registered as a candidate axis, for a binding structural
reason that this prereg commits to up front:

> **The §6.1 gate is Calmar = CAGR ÷ maxDD — drawdown-normalized.** The overlay suppresses CAGR (numerator)
> but is also what holds maxDD (denominator) at a contained 27–34%. Loosening it lifts numerator *and*
> denominator together, so it is structurally weak at moving a DD-normalized gate, while removing the one
> control protecting the denominator. It is a returns-for-risk trade, not a free Calmar win.

So deployment is run **only as a pre-committed diagnostic**, in the V4.1/`03` style (`B_random`/`B_all` were
non-gating reference books; this is the same species):

- **`D_base`** — the candidate selector at the frozen overlay (`f ∈ {0, 0.5, 1.0}`). Reuses the Stage-1 run.
- **`D_more`** — the candidate selector with a **deploy-more** overlay `f ∈ {0, 0.75, 1.0}` (Neutral bucket
  lifted 0.5 → 0.75; Bear still 0, Bull still 1.0). A single, pre-specified variant — **not** a grid.
- **Reported together:** Calmar, **maxDD**, CAGR for both, at base cost. Capital-blind read is fine
  (`whole_shares` off) since this bounds a structural question, not a deployable book.

*Pre-committed read (decided before any number):*
- **Overlay earns its keep** — `D_more` Calmar ≤ `D_base` Calmar (CAGR rose but maxDD rose at least as fast)
  ⇒ leave the overlay frozen; the de-deployment is doing its risk job. *(The structurally-expected outcome.)*
- **Deployment is a real lever** — `D_more` Calmar materially > `D_base` **and** `D_more` maxDD ≤ 100% of the
  benchmark ⇒ this **authorizes a separate future amendment** that adds a deployment axis with **its own K**
  (identical to the selector-promotion rule). It does **not** change the candidate in this run.

*Guard:* report-only. The locked OOS candidate uses the **frozen** overlay regardless of this diagnostic; it
**adds 0 to K**; a positive read triggers *new* pre-registered work, never a quiet swap.

---

## 6. Pre-committed acceptance rule (binding — identical gates to `00` §6, nothing relaxed)

A selector config becomes the **single locked OOS candidate** iff **all** hold on full DISCOVERY:

1. **§6.1 cost survival:** pessimistic-cost Calmar ratio vs **Nifty 50 TRI ≥ 1.0** (the primary gate;
   high swing turnover means costed Calmar is the killer).
2. **§6.2 concentration — SKEW-AWARE** (the `09`/`10` random-subset gate, exactly as `00` §6.2): median
   Calmar ≥ 0.70 of base **and** p5 ≥ 0.50 of base, **≥ 25 rotating distinct P&L contributors**. Classic
   drop-top-10 reported as a contamination guard, **diagnostic not gating** (a swing book is *meant* to ride
   winners; a pass-skew/fail-classic config is "conditional", never "validated").
3. **§6.3 plateau:** the candidate and its §4 neighbors (±1 step on **selector lookback** {63,126,252}
   **and** on `target_positions` {13,15,17}) stay ≥ **85%** of the candidate's base Calmar — a region, not a
   lone peak.
4. **Deployment bar (= `08` §2b / `00` §6.4):** beats Nifty 50 TRI on **base-cost Calmar** with
   **maxDD ≤ 100%** of the benchmark.
5. **§6.4 subperiod** reported, **not** gating (window-fragility demoted, per the whole v2→v4 arc).

**Null outcome (pre-accepted close):** if **0** selectors satisfy 1–4, the return-informed-selector lever is
a **research note**, the v4 swing family is **fully closed**, and **v4-FINAL_OOS is NOT touched**. A null is
the honest finding that better name-selection does not rescue a thin daily-swing edge past a costed,
deflated bar on this market — **not** a prompt to add a selector, loosen a threshold, or re-touch OOS (§1).

---

## 7. K / deflation, splits, one-shot OOS

- **K** continues from the v4 ledger (6) and accrues each Stage-1/Stage-2 selector × cost level (§4). At OOS
  report **raw Sharpe, K (≈16+), deflated Sharpe** (`validation.deflated_sharpe`) **+ PBO** (`pbo_cscv` over
  DISCOVERY walk-forward windows; no fold reaches FINAL_OOS).
- **DISCOVERY** = `validation.DISCOVERY (2018-02-06 → 2023-06-30)` — all of §3–§6 lives here.
- **v4-FINAL_OOS** = `validation.FINAL_OOS (2023-07-01 → 2026-06-12)`, **pristine** (the V4.1 null never
  spent it) — touched **exactly once**, only after a single §6-locked candidate exists, **never** on the
  null. Byte-for-byte locked candidate through the v4 engine, once, no re-tuning.
- **Contamination caveat (inherited, `00` §8):** the OOS calendar bytes are unspent for the v4 family but
  the researcher's macro-knowledge of 2023–2026 is not pristine ⇒ a FINAL_OOS pass is "in-sample-clean for
  v4, macro-contaminated for the researcher"; the truly clean test remains a **forward paper probation**.

---

## 8. Honest prior — the bar is steep, NULL is the most likely outcome (Rule 12)

This must be read **before** sign-off, not after a result:

- **The V4.1 references already bound the upside.** The §6 diagnostic measured `B_random` median Calmar
  **0.138** and `B_all` (hold every firing name) **0.090** — both *far* below the Nifty 50 TRI bar of
  **0.346**. A return-informed selector picks a *subset*, so it can exceed `B_all` only if edge is dispersed
  across the firing names; but to clear §6.1 it must roughly **2.5×** the random book's Calmar. **The data
  does not promise that.** This is a genuine long shot, not a likely pass.
- **Three prior programs hit the "buy-the-index-fund" wall** (v2 floor, v3 momentum-only, v3 Track-B /
  stable-universe). The base rate for "one more structural lever clears the costed bar" is low.
- **Why run it anyway:** (a) `00` §6 pre-authorized exactly this and it is the *last* clean structural lever
  for v4 before the family is permanently closed; (b) the forensic shows a *real* positive-expectancy edge,
  so the question "is the thin edge concentrated in identifiable names?" is well-posed and falsifiable; (c)
  it is cheap (3 selectors, frozen everything else) and the null is pre-accepted. **If it nulls, v4 closes
  for good** — no further amendments without genuinely new information (new data, not new knobs).

---

## 9. Lookahead guardrail (inherited from `00` §9 + the selector-specific items)

All `00` §9 landmines apply unchanged. Selector-specific:
- **Selector ranks on completed-`D` data, fills `D+1` open.** The 126-td return uses the adjusted close
  through `D` only; the RS benchmark return uses Nifty 50 through `D` only. No in-progress bar.
- **Trailing-window momentum with `min_periods = lookback`;** a name short of full history sorts last (no
  thin-data preference, no forward-fill).
- **Adjusted series only** — a corporate action must not manufacture a momentum rank; `instrument_id`
  identity (`06`/`07`) so a succession does not look like a momentum reset.

---

## 10. Locked commitments (Arafat — sign to flip DRAFT → LOCKED)

Confirm or redline each.

1. **K carries from v4 (≥6), not reset** — same engine/prior, one axis changed; new trials accrue on top;
   one-shot v4-FINAL_OOS inherited pristine (§1, §7). *(Pre-confirmed 2026-06-24.)*
2. **Only the selector changes** — entry, exit (Type-3 ATR **3.0**), regime, `target_positions=15`, stable
   U=200, ₹3.5L, indicators all byte-frozen at `00`/Amendment-1 (§1).
3. **Selector family a-priori** — candidate **MOM (126-td return)**; comparators **RS** (excess vs Nifty 50)
   + **ADV** (closed-engine baseline); lookback frozen 126 with {63,252} as §6.3 plateau (§3, §4).
4. **Grid** — the small enumerated §4 grid (3 selectors × {base,pess}; plateau over lookback{63,126,252} ×
   `target_positions`{13,15,17}); two-stage screen → battery; no level added after results.
5. **Deployment = non-gating diagnostic only** (`D_base` vs `D_more` f∈{0,0.75,1.0}), adds 0 to K, reports
   Calmar+maxDD+CAGR, cannot become a candidate this run; a positive read authorizes a *separate* future
   amendment (§5). **(decision — confirm you accept deployment is NOT a gated axis here.)**
6. **Acceptance rule** — `00` §6 gates verbatim (§6.1 ratio ≥ 1.0; §6.2 skew-aware; §6.3 plateau; deploy bar
   maxDD ≤ 100%; §6.4 diagnostic); exit-choice-is-not-a-silent-swap; pre-accepted null = v4 family fully
   closed, FINAL_OOS untouched (§6).
7. **Honest prior accepted** — the V4.1 references (0.09–0.14) sit far below the 0.346 bar; NULL is the most
   likely outcome; a null permanently closes v4 (§8).

> **Signed:** Arafat — 2026-06-24 (all 7 commitments approved as recorded above; DRAFT → LOCKED; V4.4
> execution below authorized). K carries from the v4 family (≥6, not reset); one-shot v4-FINAL_OOS inherited
> pristine. No selector code was written before this signature.

---

## 11. Execution (cold-session runnable — NOT STARTED until §10 is signed)

> No stage begins before §10 is LOCKED. DISCOVERY only until a candidate is locked; v4-FINAL_OOS spent
> exactly once, only on a §6-locked candidate, never on the null. Honor the token budget (Rule 6); update
> Status + a session log per stage; do not mark Done if anything was skipped (Rule 12).

### V4.4 — Selector implementation + Stage-1 cost screen on DISCOVERY
- **Status:** ✅ DONE 2026-06-25 → **0/3 clear §6.1 → NULL CLOSE** (results in §12).
- **Did:** (a) added `SwingConfig.selector` `"mom"`/`"rs"` + `selector_lookback=126` (additive — V4.0/V4.1
  byte-identical; 44 swing_v4 tests green incl. no-lookahead, thin-data-sorts-last, RS≡MOM identity,
  deterministic, fail-loud-on-missing-`nifty_mom`, and the §5 `neutral_fraction` knob); point-in-time
  momentum precomputed in the signal store; `nifty_mom` plumbed into the engine context for "rs".
  (b) Ran the §4 Stage-1 screen (3 selectors × base+pessimistic) + the §5 deployment diagnostic + the
  `03` per-round-trip forensic on each (`backend/app/swing_v4/v44_selector_screen.py`; raw report
  `backend/reports/v44_selector_screen.txt`, gitignored). Logged 6 trials to the v4 ledger.
- **Done-criteria — all met:** selector deterministic + no-lookahead tested ✅; ADV-baseline parity ✅
  (re-derived 0.083 base / 0.11 pessimistic exactly, |Δ|≤0.004); §6.1 survivors identified ✅ (**zero**);
  no battery/OOS run (correct — the null stops here).

### V4.5 — Stage-2 battery + §6 acceptance (only on §6.1 survivors)
- **Status:** ⬜ N/A — V4.4 yielded **0** §6.1 survivors ⇒ the pre-accepted null (§6) closes the v4 family
  at V4.4. No battery, no plateau, no candidate.

### V4.6 — One-shot v4-FINAL_OOS + §10-of-`00` verdict (only on a locked candidate)
- **Status:** ⬜ N/A — no §6-locked candidate ⇒ **v4-FINAL_OOS NEVER touched; pristine for the v4 family.**

---

## 12. V4.4 results — NULL CLOSE (the findings)

**Run:** `backend/app/swing_v4/v44_selector_screen.py`, DISCOVERY 2018-02-06 → 2023-06-30, base+pessimistic
cost, whole-share ₹3.5L. Raw report `backend/reports/v44_selector_screen.txt` (gitignored).

### 12.1 The §6.1 cost screen — 0/3 survivors

| Selector | base Calmar | maxDD | Sharpe | CAGR | turnover | pess §6.1 ratio | §6.1 |
|---|---:|---:|---:|---:|---:|---:|:--:|
| **MOM** (candidate, 126-td return) | **0.179** | 34.2% | 0.55 | 6.1% | 798% | **0.39** | ❌ FAIL |
| RS (excess vs Nifty 50) | 0.179 | 34.2% | 0.55 | 6.1% | 798% | 0.39 | ❌ FAIL |
| ADV (closed V4.1 baseline) | 0.083 | 34.4% | 0.30 | 2.9% | 828% | 0.11 | ❌ FAIL |

The §6.1 bar is **pessimistic-cost Calmar ratio ≥ 1.0** vs Nifty 50 TRI. Best is MOM at **0.39 — well short**.
**Pre-accepted null (§6): the v4 swing family is fully closed as a research note; v4-FINAL_OOS NOT touched.**

### 12.2 The selector DID capture edge — the §6 diagnosis was right, just not enough (the honest read)

The encouraging negative result: **MOM more than doubled the candidate's base Calmar (0.083 → 0.179, 2.16×)**.
Per-round-trip forensic (the `03` species), MOM vs ADV:

| | win rate | avg win | avg loss | payoff | net expectancy/trip | median hold |
|---|---:|---:|---:|---:|---:|---:|
| **MOM** | 34% | **+21.2%** | −7.8% | **2.71** | **+1.98%** | 43d |
| ADV | 33% | +16.6% | −7.5% | 2.21 | +0.72% | 42d |

Picking the strongest-trend names (not the most liquid) raised average winner size and per-trade expectancy
**~2.7×** — exactly the "edge is per-name and the liquidity rank discards it" mechanism `03` + the V4.1 §6
diagnostic predicted. **The selector is a real, working lever.** It is simply **not large enough** to overcome
~800% turnover at pessimistic cost: even the doubled Calmar (0.179) is 39% of the index's costed Calmar. The
selector attacks the edge (Leak A, `03`); it does nothing for turnover (Leak B), which is set by the frozen
exit and is the binding friction. *No knob inside this prereg can close a ~2.5× costed gap — the wall holds.*

### 12.3 RS ≡ MOM — confirmed empirically (§3 identity)

RS reproduced MOM **byte-for-byte** (base Calmar 0.1795, ratio 0.3948, 755 fills — identical). As §3 reasoned,
the Nifty 50 term is a single per-day constant subtracted from every candidate, so it cannot change the
cross-sectional order. **RS carries no information beyond MOM as a selector.** (Demonstrated, not assumed —
the screen ran the full RS engine and it matched.)

### 12.4 ADV-baseline parity — engine integrity confirmed

The ADV selector (= the closed V4.1 T3 engine) re-derived the V4.1 numbers exactly: base Calmar **0.083**
(V4.1 ~0.083) and pessimistic ratio **0.11** (V4.1 ~0.11), |Δcalmar|=0.000, |Δratio|=0.004 ≤ tol. The selector
refactor changed nothing on the frozen path (also locked by 44 green swing_v4 unit tests).

### 12.5 §5 deployment diagnostic — DEPLOYMENT IS A REAL LEVER (non-gating; a pre-authorized forward lead)

| | Calmar | maxDD | CAGR |
|---|---:|---:|---:|
| `D_base` (Neutral f=0.50, frozen overlay) | 0.179 | 34.2% | 6.15% |
| `D_more` (Neutral f=0.75) | **0.281** | **34.0%** | **9.56%** |
| Nifty 50 TRI maxDD (deploy bar denominator) | — | 38.3% | — |

Lifting the Neutral-bucket deployment from 0.5 → 0.75 raised Calmar **0.179 → 0.281** and CAGR 6.1% → 9.6%
**while maxDD actually fell slightly (34.2% → 34.0%, ≤ the 38.3% benchmark)**. This is the §5 *"deployment is a
real lever"* read: the structural worry (loosening the overlay lifts maxDD as fast as CAGR) did **not**
materialize on this window. **Per §5 this authorizes a SEPARATE future amendment that adds a deployment axis
with its own K — it does NOT change the candidate, add to K, or rescue §6.1 here** (base cost only; pessimistic
cost + the ~800% turnover would still bind). Honest caveat (§8 prior): the base rate is still "buy the index
fund," and this lever, like the selector, leaves turnover untouched.

### 12.6 K / OOS accounting

This run logged **6 trials** (3 selectors × 2 cost levels) to the v4 ledger; carried v4 K (≥6) ⇒ **K ≈ 12**.
The §5 deployment diagnostic added **0** (non-gating). **v4-FINAL_OOS was NOT loaded or touched — pristine for
the entire v4 family.** No selector added after seeing a number, no threshold relaxed, no OOS peek (§1 honored).

> **K-accounting correction (2026-06-25, append-only — original figures above stand as signed):** under the
> counting standard ratified in `05` §7.0, this run's effective independent K is **1**, not 6. Reasons: cost
> levels are an evaluation assumption, not a trial (×1, not ×2); **RS ≡ MOM** (a per-day-constant cannot
> reorder a cross-section, §3) → counts once; the **ADV** arm re-derived the V4.1 cell exactly (parity anchor)
> → adds 0. The only genuinely new return-generating hypothesis here was **MOM**. Corrected carried v4 ledger
> = **4** (V4.1's 3 + this 1); see `05` §7.1. No result or verdict changes — recorded so future preregs do not
> re-inflate K with cost-level and identical-config multipliers.

### 12.7 Forward leads (recorded, NOT acted on — each needs its own signed prereg)

1. **Deployment axis** (§5 positive read) — the one genuinely live, pre-authorized lead. A separate prereg
   could test a deployment-throttle grid carrying its own K. **Prior: NULL is still most likely** (turnover
   unaddressed; "buy the index fund" base rate across 4 prior programs).
2. **Selector + exit/turnover jointly** — the selector helps edge, but turnover (the exit rule) is the binding
   friction and was frozen by `03`. Any future attempt must attack turnover, which is a *different* mechanism
   needing its own pre-registration. **Neither lead reopens this prereg or the closed v4 swing engine.**

---

## Exit criteria
- [x] §10 locked by Arafat (DRAFT → LOCKED) — 2026-06-24.
- [x] V4.4 — selector built (no-lookahead tested, ADV-baseline parity to V4.1 ✅ 0.083/0.11) + Stage-1 cost
      screen on DISCOVERY; **0/3 §6.1 survivors → NULL CLOSE**; §5 deployment diagnostic = "real lever"
      recorded (non-gating); ledger +6 (K≈12). Done 2026-06-25 (§12).
- [x] V4.5 — N/A (0 §6.1 survivors ⇒ §6 battery unreachable; pre-accepted null closes at V4.4).
- [x] V4.6 — N/A (no locked candidate ⇒ v4-FINAL_OOS NEVER touched; pristine for the v4 family).

> **PROGRAM CLOSE — 2026-06-25:** the return-informed selector — the last clean structural lever for v4 —
> **does not rescue the thin daily-swing edge past a costed bar.** It worked as a mechanism (MOM doubled
> Calmar, the §6 edge-discarding diagnosis vindicated) but the ~800% turnover it leaves untouched keeps the
> costed Calmar at 0.39× the index. **The v4 daily-swing family is now permanently closed as a research note.**
> v4-FINAL_OOS is pristine and unspent. Per §8, no further v4 amendments without genuinely new information
> (new data, not new knobs) — with the single pre-authorized exception of a *separate* deployment-axis prereg
> (§12.5/§12.7), which Arafat may or may not open and which carries the same honest "most-likely NULL" prior.
