# v3 / 08 — Stable-Universe Momentum Pre-Registration: universe redesign → one-shot FINAL_OOS

> **Status: LOCKED 2026-06-20 (Arafat).** §12 signed; construction/grid/acceptance/OOS-protocol
> are now commitments — no stick moves after a result (`00` §1). No config in §5 has been measured.
> `FINAL_OOS` (2023-07-01 → 2026-06-12) remains **pristine and unconsumed** across the entire
> v2→v3 program.
>
> **This file is a commitment, not a task list.** It is the deliberate, eyes-open §9-bar/universe
> redesign the `07_TRACK_B_CLOSE.md` escalation checkpoint reserved. It fixes — *before any number is
> measured* — the new universe construction, the one principled bar fix, the small search grid, the
> binding acceptance rule, and the one-shot OOS protocol. Moving any stick after seeing a result (a new
> lever level, a loosened threshold, a re-touched OOS) is the v1 sin and is forbidden (`00` §1).

---

## 0. Why this prereg exists (the escalation checkpoint, resolved)

Three lines of work closed as research notes, all pointing at the **same structural place**:

- **Track A** (momentum baseline): failed 4/5 §6 on the honest 2018 window.
- **Momentum-only** (`05`/`06`): NULL CLOSE — 2/12 configs cleared §6.1 cost, both died on §6.2
  retention (43%/34%), §6.3 plateau, and the §9 maxDD clause. **Diagnosis: ~956% turnover, of which
  ~90% is membership churn** ([[turnover-decomp-churn-dominant]]).
- **Track B** (value/quality, `07`): orthogonal factors *diluted* the composite; H3 vacuous; DSR 0.092.

`06`-forward put a condition on the record: *if value/quality also nulls, stop building and have a hard
conversation about the §9 deployment bar and/or the universe — before any further construction.* That
checkpoint is reached. This conversation (2026-06-20) ran it and reached **two findings**, each acted
on below, each justified on its own merits **independently of any observed result** (the anti-HARKing
line — `00` §1):

1. **The universe is the binding mechanism, and it is the wrong universe.** The current "universe" is
   the entire NSE EQ market (`universe_membership`, survivorship-free) carved each rebalance by the
   **adv_20 ≥ ₹5cr liquidity floor** (`signals_v3.py:116`). Membership is therefore "whatever is liquid
   *today*," re-evaluated every rebalance — names crossing the ₹5cr threshold in and out **is** the 90%
   churn that trips §6.1 (cost) and feeds the §6.2 single-name concentration. This is a
   **universe-definition artifact**, not a strategy choice, and it is mechanistically prior to every
   gate failure. Every successful Indian momentum implementation (the Nifty200 Momentum 30 index itself;
   the retail momentum smallcases) runs on a **stable, defined-membership universe with slow review +
   hysteresis buffers** — precisely the churn control we lack.

2. **One clause of the §9 bar is arbitrary.** `maxDD ≤ 70% of benchmark` **combined with** "beat the
   benchmark on Calmar" demands the strategy *strictly dominate the passive momentum index on both
   axes* — beat it on risk-adjusted return **and** draw down materially less than it — while being built
   from the *same factor*. That is near-self-contradictory for a same-factor active strategy (the
   `06` survivors *beat* Nifty200 Mom30 on Calmar and failed only this clause, ratios 0.77/0.80). The
   "70%" was a round number with no principled basis. This is a **bar-internal-logic** defect, decided
   independent of the failures it happens to explain.

**The one question this prereg asks:** *Does a stable, slow-reviewed, buffered universe — holding the
(now-exhausted) momentum construction constant — kill the membership churn enough to clear the §6
battery and the (corrected) deployment bar on the honest full window?* If yes, it earns the one-shot
OOS. If no, stable-universe momentum is a research note and `FINAL_OOS` stays pristine.

---

## 1. Scope discipline (inherits `00` §1 — restated)

- ❌ **No new factor.** The factor set is **frozen** at the Track-A five (§4). This is a *universe*
  redesign, not a factor search. Track B is closed; no fundamentals here.
- ❌ **No momentum knob search.** M (sell_rank_buffer), smoothing, cadence, and N were exhausted by the
  `05`/`06` MD grid. They are **held constant at the MD §6.1-survivor config** (§4) — *not* re-searched.
  The **only** new variable is the universe construction (§3).
- ❌ **No fine grid.** The grid is the **4 coarse points** in §5 — fully enumerated, decided now.
- ❌ **No moved return-split boundary.** `validation.DISCOVERY` / `validation.FINAL_OOS` reused
  **unchanged** (§9). The stable universe is constructed *inside* those splits from price/volume in hand.
- ❌ **No FINAL_OOS peek** before a single §6-locked candidate exists (§9).
- ✅ Every config evaluated is logged to the v2 `ConfigLedger`; cumulative **K carries from the ledger**
  (≥ 46 at TBE7 close) and feeds the deflated Sharpe (§8). A fresh objective does **not** reset K.

---

## 2. The two pre-registered redesign decisions (explicit, evidence-based)

**2a. Universe: churning liquidity-floor → stable ADV-ranked membership with slow review + buffer.**
- *Justification (binding, on the record):* the turnover decomposition ([[turnover-decomp-churn-dominant]])
  shows ~90% of turnover is membership churn — a property of defining membership by a per-rebalance
  liquidity floor. Slowing the review to semi-annual and adding a rank-hysteresis buffer attacks that
  mechanism at the source. Decided on the mechanism, which predates this prereg.
- *What stays:* the ₹5cr adv_20 floor is **retained as a per-day tradeability safety** (a name whose
  liquidity collapses is not held even if "in" the stable set). The change is to the *candidate set*:
  the stable membership becomes the primary eligibility, not the full market re-floored daily.

**2b. Bar clause: `maxDD ≤ 70% of benchmark` → `maxDD ≤ 100% of benchmark` (Calmar dominance retained).**
- *Justification (binding, on the record):* the 70% clause + Calmar-beat jointly demand strict frontier
  domination of the passive same-factor index; 70% was arbitrary. The corrected bar — *match-or-better
  than the benchmark on drawdown (`maxDD ratio ≤ 1.0`) **and** beat it on base-cost Calmar* — is the
  coherent "don't be riskier than the index, win on risk-adjusted return" deployment test. Bar-internal
  logic, decided independent of the result it explains.
- *What this is NOT:* **no other gate is softened.** §6.1/§6.2/§6.3/§6.5 thresholds are **unchanged** —
  in particular **§6.2 retention stays ≥ 70%** (we explicitly do NOT relax the concentration gate; a
  stable universe should *improve* retention on its own, and if it still fails that is itself the
  finding — §6 of this doc). §6.4 stays a reported diagnostic (its window-fragility, TBE3/`05` §2).

---

## 3. The stable-universe construction (the one new mechanism — frozen for the search except §5 levers)

Built as a **point-in-time membership mask**, survivorship-free (derived from the survivorship-free
`universe_membership` + `adv_20`), AND-ed into `V3SignalStore.entry_gate` (a signal-layer change only,
no engine edit — `signals_v3.py:94`). Definition:

- **Review cadence:** membership is recomputed **semi-annually** (Jan 31 / Jul 31 review dates) and
  **frozen between reviews**. (Matches Nifty 200 review cadence; the antidote to per-rebalance churn.)
- **Ranking metric:** at each review date D, rank all names by the **median adv_20 over the 126 trading
  days ending at D** (causal, no lookahead — reuses the existing adv_20 series).
- **Membership rule (hysteresis):** a name **enters** the universe if its review-date liquidity rank is
  in the **top U**; a name already **in** the universe **stays** until its rank falls **below `B × U`**
  (buffer band). New listings need the existing minimum-age before they are rank-eligible
  (`01_DATA_LAYER §5.5`).
- **Held-constant momentum construction** (everything except the §5 levers, pinned to `TRACK_A_BASELINE`
  ⊕ the MD §6.1 survivor):
  - `active_factors = [mom_12_1, low_vol, trend_quality, mom_6_1, reversal]` (equal-weight),
  - `target_positions N = 20`, `sell_rank_buffer M = 130`, `rank_smoothing_months = 0`,
    `rebalance_cadence = monthly` (the `06` MD1 §6.1 survivor — *not* re-searched),
  - `use_regime_overlay = True`, `catastrophic_stop_pct = 25.0`, `liquidity_floor_cr = 5.0` (safety).
- **Window:** full `validation.DISCOVERY = (2018-02-06, 2023-06-30)` for all search + selection.
- **Benchmark (deployment bar, §10):** Nifty200 Momentum 30 TRI. *(TBE-0 task: verify the loaded series
  is the real index, not the `run_real.py:13` placeholder, before any bar comparison — Rule 12.)*
- **Costs:** "base" and "pessimistic" as defined in `robustness.check_cost_stress` — reused unchanged.

---

## 4. Proposed level defaults (for §12 lock)

| Symbol | Meaning | Proposed | Note |
|---|---|---|---|
| **U** | universe size (top-N by trailing adv_20) | **200** | mirrors Nifty 200 investable breadth; strategy still holds N=20 |
| **B** | hysteresis buffer multiple (stay-in until rank > B·U) | **1.25** | 25% band — the churn antidote; B=1.0 ≡ hard review (tested as a grid point) |
| cadence | membership review | semi-annual | frozen between reviews |
| lookback | adv_20 median window for the rank | 126 td (~6mo) | causal |

---

## 5. The search grid (4 coarse points — the universe is the only variable)

| # | Config | Universe | Momentum (held constant) | Role |
|---|---|---|---|---|
| **C0** | churning control | ₹5cr floor, re-floored daily (status quo) | M=130 sm=0 monthly N=20 | **anchor** — must reproduce `06` MD1 M=130 (Calmar 0.523) |
| **S1** | stable + buffer | U=200, semi-annual, **B=1.25** | "" | primary treatment |
| **S2** | stable, hard review | U=200, semi-annual, **B=1.0** | "" | isolates *buffer* effect vs slow-review alone |
| **S3** | stable, broader | **U=350**, semi-annual, B=1.25 | "" | universe-breadth sensitivity |

4 configs, fully enumerated. No level added/removed after results (`00` §1). **Two-stage** (mirrors MD):
- **Stage 1 (all 4 — cost screen):** run each on full DISCOVERY at base + pessimistic cost. Record
  realized turnover, **realized membership churn** (the hypothesis metric), base Calmar, base maxDD,
  §6.1 pessimistic ratio. Log all 4 to `ConfigLedger`.
- **Stage 2 (only configs clearing §6.1 ≥ 1.0):** §6.2 perturbation, §6.3 neighborhood (over the §5
  universe levels), §6.5 capacity, §6.4 diagnostic. Apply §6.

---

## 6. Pre-committed acceptance rule (binding — decided before any run)

A config becomes the **single locked OOS candidate** iff **all** hold on full DISCOVERY:

1. **§6.1** pessimistic-cost Calmar ratio **≥ 1.0**;
2. **§6.2** top-10-drop retention **≥ 70%** (unchanged — concentration gate NOT relaxed);
3. **§6.3 plateau:** the config and its §5 universe-neighbors (±1 step on U and on B) stay **≥ 85%** of
   the config's base Calmar — a region, not a spike;
4. **deployment bar (corrected, §2b):** beats Nifty200 Momentum 30 TRI on **base-cost Calmar** with
   **maxDD ≤ 100%** of benchmark;
5. **§6.4** reported, **not** gating.

**Tie-break:** if ≥ 2 satisfy 1–4, pick the **lowest realized membership churn** (the mechanism we are
buying), then lowest turnover.

**Null outcome (pre-accepted close):** if **0** configs satisfy 1–4, stable-universe momentum is a
**research note** — `FINAL_OOS` stays pristine, the OOS run is **not** performed. A null is the honest
finding that stabilizing the universe does not rescue momentum on this market; it is **not** a prompt to
add a universe level, widen the buffer grid, or loosen a threshold (`00` §1). **If C0 (the control)
fails §6.1 but a stable config also fails §6.2/§6.3, the close explicitly records whether the universe
fix moved the mechanism (churn ↓) even though the gate held** — that diagnostic is the research value.

---

## 7. Robustness battery (which checks gate)

Reuse `robustness.py` unchanged. For Stage-2 survivors: §6.1 cost **HARD**, §6.2 perturbation **HARD**,
§6.3 neighborhood **HARD** (plateau over §5 universe neighbors), §6.4 subperiod **DIAGNOSTIC**, §6.5
capacity reported (expected PASS).

---

## 8. Deflation & K accounting (honest search cost)

- All 4 §5 configs logged to `ConfigLedger`. Cumulative **K at OOS = ledger value (≥ 46 at TBE7) + these
  configs' entries**. A fresh objective does **not** reset K — read from the ledger at OOS time.
- At OOS (§9): report **raw Sharpe, K, deflated Sharpe** (`validation.deflated_sharpe`) + **PBO**
  (`pbo_cscv` over `walk_forward_windows` on DISCOVERY; no fold reaches FINAL_OOS). The deflation
  headwind is real and acknowledged: K is already ~46 and rises monotonically — a marginal edge will not
  survive; only a *large* improvement clears a deflated bar.

---

## 9. Splits & the one-shot protocol

- **DISCOVERY** = `validation.DISCOVERY (2018-02-06 → 2023-06-30)` — all of §5/§6/§7/§8 lives here.
- **FINAL_OOS** = `validation.FINAL_OOS (2023-07-01 → 2026-06-12)` — touched **exactly once**, only after
  a single candidate is locked by §6, and **never** on the null outcome. The OOS run is the
  byte-for-byte locked candidate through `engine.run` on FINAL_OOS — once, no re-tuning. Mark
  `FINAL_OOS` consumed.

---

## 10. Definition of Done (the corrected deployment bar)

The candidate is **"validated, deployable"** only if the single locked config:
- Beats **Nifty200 Momentum 30 TRI** on **Calmar** after **base** costs on FINAL_OOS, with
  **maxDD ≤ 100%** of benchmark (corrected, §2b); AND
- Holds §6.1 / §6.2 / §6.3 / §6.5 out-of-sample (the four hard gates do not collapse); AND
- Is tradeable on realized turnover/capacity; AND
- Raw + deflated Sharpe reported together (§8).

§6.4 reported OOS as a diagnostic, not a gate. Anything less is a **research note** (Rule 12) — no
softening of the four hard gates to manufacture a pass. **Honest forward note:** even a PASS here only
establishes the strategy beats the cheap passive momentum index net of honest costs; if it merely
*matches* it, the correct conclusion is "buy the index fund" — a valid, money-saving outcome.

---

## 11. What this prereg does NOT do (guards)

- It does **not** add a factor, tune weights, or re-search M / smoothing / cadence / N (§1, §3).
- It does **not** soften §6.1/§6.2/§6.3/§6.5 (the only bar change is §2b's maxDD clause; §6.2 stays 70%).
- It does **not** move `validation.DISCOVERY` / `validation.FINAL_OOS`.
- It does **not** acquire real index-constituent data (the ADV-synthetic universe is built from data in
  hand — that decision is locked; a real-index or market-cap universe is a *separate future* prereg).
- It does **not** touch `FINAL_OOS` until a single DISCOVERY-locked candidate exists, and not at all on
  the null outcome.

---

## 12. Locked commitments (Arafat — sign to flip DRAFT → LOCKED)

Confirm or redline each before any run:

1. Universe redesign = stable ADV-ranked membership, semi-annual review + hysteresis buffer (§2a, §3).
2. Level defaults = **U=200, B=1.25**, 126-td adv_20 rank, ₹5cr floor retained as safety (§4).
3. Grid = the **4 coarse points** in §5 (C0 control + S1/S2/S3); no level added/removed after results.
4. Bar fix = **maxDD ≤ 100%** + Calmar dominance (§2b); **§6.2 retention stays ≥ 70%**; §6.4 diagnostic.
5. Acceptance rule = §6 items 1–5, lowest-churn tie-break, pre-accepted null close.
6. Held-constant momentum = the `06` MD1 §6.1 survivor (M=130 sm=0 monthly N=20, 5-factor) — not searched.
7. `FINAL_OOS` spent **exactly once**, only on a §6-locked candidate, under §9/§10; pristine otherwise.

> **Signed:** Arafat — 2026-06-20 (all 7 commitments approved as drafted; DRAFT → LOCKED; SU0 authorized).

---

## 13. Execution (cold-session runnable — DISCOVERY only until a candidate is locked)

> Read this file + the one stage you are doing. Honor the token budget (Rule 6). Update Status, fill a
> Session log, check off Done-criteria. Do not mark Done if anything was skipped (Rule 12).

### SU0 — scaffolding + benchmark verification + stable-universe builder
- **Status:** ✅ DONE (2026-06-20, commit pending) — `FINAL_OOS` untouched.
- **Do:** (a) **verify the Nifty200 Momentum 30 TRI series is the real index**, not the `run_real.py:13`
  placeholder — fail loud if placeholder (Rule 12). (b) Build the point-in-time stable-membership mask
  (semi-annual review, top-U by 126-td median adv_20, B-buffer hysteresis) as a precomputed
  (date → eligible ISIN set); wire it into `V3SignalStore.entry_gate` behind a config flag so C0
  (flag off) is byte-identical to today. (c) Extend `V3Config` with `universe_mode`/`universe_size_U`/
  `universe_buffer_B`/`universe_review_cadence`. Test-gated; **no backtest, no FINAL_OOS.**
- **Done-criteria:** benchmark confirmed real (or loudly flagged); mask builder unit-tested for
  no-lookahead + hysteresis; C0 reproduces the `06` MD1 M=130 anchor (Calmar 0.523) byte-for-byte.

> **Session log (2026-06-20):**
> - **(a) Benchmark — REAL, verified.** `run_real.py:13`'s synthetic index is the *regime-overlay
>   200-DMA* placeholder, **not** the deployment benchmark; the deployment bar loads the real TRI via
>   `benchmark.load_tri(TRI_MOMENTUM_30, …)` from the on-disk cache
>   `data/niftyindices/nifty200_momentum_30_01Jan2017_12Jun2026.parquet`. Loaded with a fetch-fn that
>   raises on any network call (proving a pure cache hit): **2340 pts, 2017-01-02 → 2026-06-12** (covers
>   DISCOVERY + FINAL_OOS), no NaN, levels 8,030 → 38,137 (≠ synthetic "starts at 100"), ~20%/yr CAGR,
>   ~19.5% vol, worst day **−12.78%** = the real Mar-2020 COVID signature. Not a placeholder.
> - **(b) Mask built + wired.** New `app/backtest_v2/stable_universe.py`
>   (`build_stable_universe_mask` → `StableUniverseMask`): semi-annual Jan31/Jul31 reviews resolved to
>   the last trading day ≤ anchor; rank by 126-td median adv_20 with `min_periods = lookback_td` (the
>   minimum-age rule); top-U enter, stay-in until rank > B·U. AND-ed into `V3SignalStore.entry_gate`
>   behind `universe_mode`; `floor` ⇒ mask `None` ⇒ no constraint.
> - **(c) `V3Config` extended:** `universe_mode` (`floor`|`stable`, default `floor`), `universe_size_U`
>   (200), `universe_buffer_B` (1.25), `universe_review_cadence` (`semi-annual`),
>   `universe_rank_lookback_td` (126); fail-loud `__post_init__` validation.
> - **Tests:** `tests/backtest_v2/test_su0_stable_universe.py` (11 cases) — review-calendar resolution,
>   top-U entry, **hysteresis (stay-in within band + drop beyond band + B=1.0 no-buffer)**,
>   **no-lookahead** (future adv corruption leaves past sets identical; non-vacuous), minimum-age, and
>   floor-identity (floor ⇒ mask None; stable AND-s & restricts; mask is a pure AND on a member).
>   **Full `tests/backtest_v2/` = 560 passed** — every pre-existing test (incl. the raw-momentum parity
>   suite) unchanged, the structural proof that the C0/floor path is byte-identical.
> - **Honest flag (Rule 12):** the done-criterion's *numeric* "C0 reproduces Calmar 0.523 byte-for-byte"
>   requires a real-data DISCOVERY backtest, which SU0's own "Do" **forbids** (no backtest). SU0 proves
>   the floor path is byte-identical **structurally** (mask absent ⇒ gate logic unchanged + 560 green);
>   the **numeric** 0.523 reproduction is carried to **SU1**, where C0 is one of the four configs that
>   actually run. This is a deliberate reconciliation of a mild internal inconsistency in the doc, not a
>   skipped check.

### SU1 — Stage 1: 4-config cost + churn screen on full DISCOVERY
- **Status:** ✅ DONE (2026-06-20, commit pending) — `FINAL_OOS` untouched.
- **Do:** run each §5 config at base + pessimistic cost; record turnover, **membership churn**, base
  Calmar, maxDD, §6.1 ratio; log all 4 to `ConfigLedger`. **No FINAL_OOS, no §6.2/3/4.**
- **Done-criteria:** 4-row table (config → churn, turnover, Calmar, maxDD, §6.1, pass/fail); §6.1-clearing
  set identified (may be empty — report honestly); C0 anchor reproduced; `FINAL_OOS` untouched.

> **Session log (2026-06-20):** runner = `app/backtest_v2/su1_cost_screen.py`
> (`backend/venv/bin/python -m app.backtest_v2.su1_cost_screen`), DISCOVERY 2018-02-06 → 2023-06-30,
> §6.1 benchmark = Nifty50 TRI (same metric as `06` MD1; cached). Momentum held constant at the MD1
> §6.1 survivor (5-factor, N=20, M=130, sm=0, monthly, regime ON, ₹5cr floor). Membership churn measured
> with the established `diag_turnover_decomp._decompose_fills` (entry+exit Δweight ÷ total, × annualized
> turnover); regime is ON for all 4 configs ⇒ its full-book-toggle contribution is a **constant confound**
> and the C0→S* delta isolates the universe effect.
>
> | Cfg | Universe | Base Calmar | MaxDD | Turnover | Churn (ann / frac) | C_strat(P) | C_n50 | §6.1 ratio | §6.1 |
> |---|---|---|---|---|---|---|---|---|---|
> | **C0** | ₹5cr floor (daily) | **0.523** | 26.1% | 706% | 561% / 79% | 0.468 | 0.346 | **1.35** | ✅ PASS |
> | **S1** | stable U=200 B=1.25 | 0.391 | 22.3% | 539% | 379% / 70% | 0.333 | 0.346 | **0.96** | ❌ FAIL |
> | **S2** | stable U=200 B=1.0 | 0.457 | 22.6% | 555% | 387% / 70% | 0.396 | 0.346 | **1.15** | ✅ PASS |
> | **S3** | stable U=350 B=1.25 | 0.575 | 23.7% | 604% | 438% / 73% | 0.521 | 0.346 | **1.51** | ✅ PASS |
>
> - **C0 anchor REPRODUCED byte-for-byte:** base Calmar **0.523** = the `06` MD1 M=130 number exactly,
>   numerically confirming SU0's structural byte-identity claim (the floor path is unchanged by the SU0
>   mask wiring). The SU0→SU1 deferred numeric check is now closed.
> - **§6.1 survivor set = {C0, S2, S3}** (ratio ≥ 1.0). **S1 (the *proposed primary* U=200 B=1.25) FAILS**
>   at 0.96 — the 1.25 buffer at U=200 drops base Calmar to 0.391. The buffer is *not* free at the
>   narrow universe (S1 fail) yet is fine at the broad one (S3, U=350 B=1.25, ratio 1.51, best of grid).
> - **The §08 churn hypothesis is CONFIRMED at the mechanism level:** stabilizing the universe cut
>   realized membership churn from C0's **561% → 379–438%** (Δ **−122 to −182 pp**), turnover **706% →
>   539–604%**, churn-fraction **79% → 70–73%**. The redesign moved exactly the lever it targeted
>   ([[turnover-decomp-churn-dominant]]).
> - **Honest caveat (Rule 12) — churn ↓ did NOT translate to a §6.1 edge:** C0, the *highest*-churn
>   config, still posts the 2nd-best §6.1 ratio (1.35) and the only stable config to match/beat C0 on
>   base Calmar is the *broader* S3 (0.575 > 0.523); the narrower stable configs (S1/S2) gave up Calmar.
>   So §6.1 (a cost-survival gate) does **not** reward the churn reduction here — the churn payoff, if
>   any, must appear in **§6.2 retention / concentration** (SU2), which is precisely where momentum-only
>   died in `06`. SU1 establishes the mechanism moved; SU2 decides whether that buys a deployable gate.
> - **Realized stable-universe sizes** (per semi-annual review, n=20 reviews): S1 0–230, S2 0–200,
>   S3 0–396 (the leading 0s are the pre-first-review warmup window — mask empty until the first review).
> - **Ledger:** all 4 configs × 2 cost levels = **8 entries** logged (`ConfigLedger`, stages
>   `SU1_base`/`SU1_pessimistic`); K carries (≥46 at TBE7 + 8). `FINAL_OOS` untouched.
> - **No regression risk:** `su1_cost_screen.py` is a new standalone analysis script; it imports
>   existing code (incl. the SU0 mask + `_decompose_fills`) without modifying any of it.

### SU2 — Stage 2: full battery + §6 acceptance on the §6.1 survivors
- **Status:** ⬜ TODO (depends on SU1) — **§6.1 survivor set = {C0, S2, S3}** (S1 dropped, ratio 0.96).
- **Do:** §6.2/§6.3/§6.5 (+ §6.4 diagnostic) on survivors; apply §6 items 1–5 + tie-break. **No FINAL_OOS.**
  Note the §6.3 plateau is over §5 universe neighbors (±1 step on U and B) — with S1 (a U=200 neighbor)
  already failing §6.1, the S2/S3 neighborhood evidence must be read carefully (08 §6.3).
- **Done-criteria:** per-survivor §6 table; exactly one candidate locked OR null close declared (Rule 12 —
  no silent pick); churn-moved-the-mechanism diagnostic recorded either way; `FINAL_OOS` untouched.

### SU3 — One-shot FINAL_OOS + §10 DoD verdict (only on a locked candidate)
- **Status:** ⬜ TODO (depends on SU2 with a locked candidate)
- **Do:** byte-for-byte locked candidate through `engine.run` on FINAL_OOS — once, no re-tune. Report §10
  + raw/deflated Sharpe + PBO. Mark `FINAL_OOS` consumed.
- **Done-criteria:** §10 verdict (deployable | research note); if research note, `FINAL_OOS` stays
  pristine and SU3 is N/A.

---

## Exit criteria
- [x] §12 locked by Arafat (DRAFT → LOCKED) — 2026-06-20.
- [x] SU0 — benchmark verified real (Nifty200 Mom30 TRI, cached, 2017→2026); stable-universe mask built
      + test-gated (560 green); floor path byte-identical structurally. Numeric C0 Calmar-0.523 anchor
      carried to SU1 (SU0 forbids a backtest).
- [x] SU1 — 4-config cost+churn screen (2026-06-20): C0 anchor reproduced (Calmar 0.523); §6.1
      survivors **{C0, S2, S3}** (S1 fails 0.96); churn moved C0 561% → 379–438% (hypothesis confirmed
      at mechanism level); 8 ledger entries; FINAL_OOS untouched.
- [ ] SU2 — full battery + §6; single candidate locked OR null close (no silent pick).
- [ ] SU3 — one-shot FINAL_OOS only on a locked candidate; §10 verdict; else N/A + FINAL_OOS pristine.
