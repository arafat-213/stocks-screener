# v5 / 00 — Regime-Throttled Index Overlay: the frozen v4 regime score as a risk-on/off timer on Nifty 50 TRI

> **Status: LOCKED — 2026-06-26 (Arafat signed §11). Execution AUTHORIZED but NOT started — Arafat will run
> RO0 in a separate cold session. No backtest may touch `FINAL_OOS` until a DISCOVERY candidate is locked.**
> This is a **commitment, not a task list**. It fixes — before any new number exists — the
> single candidate, the (already-frozen) signal, the deployment mechanics, the binding bar, the diagnostics,
> the K accounting, and the one-shot OOS protocol. Moving any stick after a result (a new bucket cut, a
> loosened bar, a re-touched OOS, a re-picked instrument) is forbidden (`v3/00` §1).
>
> **Owner:** Arafat. **Created:** 2026-06-26.
> **Rev 1 (2026-06-26, pre-lock discussion):** defensive asset = real-short-rate **liquid fund** (not 0%
> cash) — made fair by the static-matched bar (§3a/§5); binding bar stays **static exposure-matched** (both
> legs now real held assets ⇒ purest "only timing differs"); map fork resolved → **frozen 3-bucket map =
> candidate**, linear ramp = non-gating diagnostic (§5/§6). **LOCKED 2026-06-26 (§11 signed).**
> **Depends on (all COMPLETE, nothing new to build at the data layer):**
> - `v4/01_REGIME_DATA_LAYER.md` — breadth/A-D + India VIX landed, PIT-clean, 5-factor inputs available.
> - `v4/00_SWING_PREREG.md` §4 — the frozen 0–5 regime score *definition* (return-blind, never optimized).
> - Code reuse, verbatim: `app/swing_v4/regime.py` (`RegimeScore.deployable_fraction`),
>   `app/backtest_v2/benchmark.py` (`load_tri`, real Nifty 50 TRI), `costs.py`, `robustness.py`,
>   `validation.py` (`DISCOVERY` / `FINAL_OOS`).
>
> **What this prereg is NOT:** it is not a new factor, a new regime score, a parameter search, or a new data
> layer. It reuses an **already-frozen** signal and asks **one** question (§0).

---

## 0. Why this prereg exists — and the one question it asks

**The whole v2→v4 graveyard shares three walls** (see `MEMORY.md`): (1) **turnover = costs** kills every
single-name momentum book (800–2660%/yr; trails the index even pre-cost); (2) **single-name fragility**
(§6.2 concentration; v4.8's edge was 87% one stock); (3) **deflation** (K≈69–100 ⇒ the one OOS pass we ever
got, S3 `v3/10`, had deflated Sharpe ≤ 0 at every K). The earned conclusion across **three** independent
programs: *a diversified momentum book merely matches the passive index after costs — "buy the index fund."*

**Direction D attacks all three walls at once by changing what we trade.** Instead of *picking stocks*, we
**hold one broad index (Nifty 50 TRI)** and use the **already-frozen v4 regime score** as a **throttle on
how much of our spare capital is deployed** — full in a healthy regime, scaled down into a defensive **liquid
fund** as it deteriorates.

| Wall | How the overlay disarms it |
|---|---|
| **Turnover/costs** | We trade **one instrument**, and **only when the regime bucket changes** — a handful of switches/year, not 800% book churn. |
| **Single-name fragility** | There are **no names**. We hold the index. §6.2 concentration cannot exist by construction. |
| **Deflation (K)** | The signal is **already frozen** (`v4/00` §4, return-blind). We search **nothing**. **K for this family ≈ 1**, not 69. A modest real edge can finally clear a deflated bar. |

**Why this bet is better-founded than anything we have tried.** Single-name momentum has weak external
priors. **Time-series / trend-following regime timing on an index has real, published support**: Faber's
*Quantitative Approach to Tactical Asset Allocation* (the 10-month-SMA timing rule), Antonacci's dual /
absolute momentum, and time-series momentum (Moskowitz–Ooi–Pedersen). The consistent finding across decades
and asset classes: **timing barely raises return but sharply cuts drawdown** vs buy-and-hold. Our regime
score is a *richer* version of Faber's single SMA — it already bakes in the 200-DMA, the 50/200 cross,
breadth, A/D, and VIX. For the first time we are betting **with** a documented anomaly, not against the same
wall.

> **Plain-language note (Rule 13):** a "regime overlay" is a **gas pedal on your index holding**, not a
> stock picker. When the market looks healthy (uptrend + broad participation + calm volatility) the pedal is
> floored (100% in the index ETF). When it deteriorates the pedal eases off (50%, then fully into a liquid
> fund that still earns the short rate). The bet is not "earn more in good times" — it's **"don't sit through
> the 40% crash with your spare money."** The hard part (§5) is proving the *timing* beats just *statically
> holding the same average mix* — otherwise you've paid turnover for de-leveraging you could do for free.

**The one question:** *Does the frozen v4 regime score, used as a deploy-fraction throttle on Nifty 50 TRI,
beat a **static exposure-matched** index/cash mix on risk-adjusted return (Calmar), net of costs, on
DISCOVERY — and if so, does it hold on the one-shot FINAL_OOS?* If yes → a genuinely deployable, low-turnover,
drawdown-managed spare-capital strategy. If no → **"hold a static index/cash sleeve"** (or just the index),
now **earned** rather than assumed — itself a deployable, money-saving answer.

---

## 1. Scope discipline (inherits `v3/00` §1 — restated for this family)

- ❌ **No new signal.** The regime score is **frozen verbatim** at `v4/00` §4 / `swing_v4/regime.py`
  (5-factor, buckets 0–1→0% / 2–3→50% / 4–5→100%, liquid breadth/A-D, missing-VIX→0). We do **not** tune the
  weights, cuts, DMA windows, factor set, or bucket map. It was designed **return-blind** and never optimized
  on returns ⇒ it contributes **0** to this family's K.
- ❌ **No grid / no lattice.** **One** instrument (Nifty 50 TRI), **one** allocation map, **one** locked
  config (§3). The v3 sin was searching a lattice and then deflating to death. We do not repeat it.
- ❌ **No re-picked operating point.** The candidate is pre-specified **now** (§3). The diagnostics (§6) are
  *reported*, never a menu to select a better config from.
- ❌ **No threshold relaxation.** The binding bar (§5) and the deflation reporting (§7) are fixed here.
- ❌ **No FINAL_OOS peek** before the single locked candidate has been measured on DISCOVERY (§8).
- ✅ **Independent family ⇒ K resets to 0** (as v4 did), but is honestly incremented **within** this family
  for every distinct return-generating config actually run. With the frozen design that is **≈ 1** (§7).
- ➕ **Inherits the spent-OOS reality:** the v2/v3 `FINAL_OOS` is *spent* (`v3/10`). We **inherit the v4 date
  split** (§8) — defensible because the score is return-blind and this strategy has never been fit to returns.

---

## 2. The bet & external priors (why the prior is ~50/50, not ~0)

Unlike the momentum graveyard, trend/regime timing on an index has a real, named edge — but with **honest,
pre-registered caveats** that set the realistic prior:

1. **The edge is drawdown reduction, not return enhancement.** Expect the overlay to *give up* some upside
   for a much shallower maxDD. ⇒ the metric must be risk-adjusted (Calmar = "return per unit of crash"), not
   raw return. *(Rule 13: Calmar ≈ throughput-per-crash.)*
2. **Cash drag in long bull markets.** Our sample (2017–2026 India) is dominated by a **post-COVID bull**.
   An overlay that sits in cash part-time will **lose to buy-and-hold on raw return** here. It must win on
   *Calmar*, and it must beat a *static* mix — see §5.
3. **Whipsaw in choppy/sideways markets.** Each regime flip costs. A flickering bucket can bleed the edge.
   ⇒ flip-count and cost-per-flip are pre-registered diagnostics (§6).
4. **Single-crash dependence (the §6.4 trap, reincarnated).** The entire Calmar edge could be **one avoided
   crash** (the March-2020 COVID dodge). A timer that only ever dodged COVID is not validated by COVID. ⇒ a
   per-drawdown decomposition is pre-registered, and a >90%-single-event edge earns a **"fragile/single-event"
   conditional label** carried to the verdict (§6, §9) — the analog of v4.8's 87%-one-name flag and `v3/10`'s
   conditional label.

**Honest prior:** roughly **50/50** that the overlay clears the §5 binding bar net of costs in this
bull-heavy sample — far better than the momentum graveyard's ~0, but **not** a foregone win.

---

## 3. The construction (frozen — there is no free variable)

- **Deployment vehicle (held):** **Nifty 50 TRI** (`benchmark.load_tri(TRI_NIFTY_50)`) — the literal "spare
  capital sitting in a broad index," cheapest/most-liquid ETF, the v4 primary benchmark. *(Total-return
  index = what you actually earn holding the ETF, dividends reinvested.)*
- **Signal series (for the score):** the **Nifty 50 price index** (close, not TRI) feeds conditions 1–2
  (200-DMA, 50/200 cross), exactly as `regime.py` expects — the 200-DMA is computed on the *price* index per
  standard convention, **never** on the TRI. Conditions 3–5 read `market_internals` (liquid breadth, liquid
  A/D, India VIX), as frozen.
- **Signal → deploy fraction (frozen 3-bucket map):** `f = RegimeScore(...).deployable_fraction(D) ∈ {0.0,
  0.5, 1.0}`, **5-factor, `neutral_fraction = 0.5` (frozen default)** — the verbatim v4 bucket map (0–1→0% /
  2–3→50% / 4–5→100%). No code change to `regime.py`. *(The linear ramp `f = score/5` is a §6 diagnostic only,
  built on the same `RegimeScore.score(D)` integer — never the candidate.)*
- **Allocation:** gross index exposure on day `D+1` = `f(D)` of current NAV; the remaining `1 − f` sits in
  the **defensive asset** (a liquid / overnight fund earning the short rate — see §3a).
- **Rebalance trigger (the turnover killer):** act **only when the bucket changes** (i.e. `f` changes).
  Score on completed day `D` → trade at **`D+1` open** (causal, `v4/00` §9 discipline). No daily churn; no
  forced intra-bucket rebalancing.
- **No forced liquidation semantics needed** (we hold one instrument): a downgrade simply sells down to the
  new `f`; an upgrade buys up. (Contrast v4's per-name "throttle only blocks new deployment" — N/A here.)
- **Starting capital:** **₹3.5L** (Arafat's real spare capital). One ETF ⇒ whole-unit granularity is a
  non-issue (no fractional-share drag like v4) — a **deployability plus**.
- **Window:** full `validation.DISCOVERY (2018-02-06 → 2023-06-30)` for §6/§7; `FINAL_OOS` per §8.

### 3a. Costs & the defensive asset (fixed here — fair, not lenient)

- **Switch cost:** on each bucket change, apply the project cost model (`costs.py`) to the **traded notional**
  `|Δexposure| × NAV`, at **base** (primary) and **pessimistic** (stress) — house convention.
- **Holding cost:** a Nifty 50 **ETF expense ratio (~0.05%/yr)** accrues on the *held* equity portion and a
  **liquid-fund expense (~0.20%/yr)** on the *defensive* portion (the fair-cost honesty of `v3/10` §2c — we
  cost our own vehicles, not just the benchmark's).
- **Defensive-asset return — LOCKED realistic (Rev 1):** the un-deployed `(1 − f)` earns a **real short-rate
  series** (91-day T-bill or a liquid-fund index, sourced in RO0; **not** a flat constant — rates swung from
  ~3.35% in COVID to ~6.5% later). *Rationale (the Rev-1 insight):* the hypothesis is **preserve capital
  during bad regimes**, not "sit in zero-return cash." Modeling 0% would *understate* the strategy. **This is
  safe — not a thumb on the scale — precisely because the binding bar is the static-matched mix (§5):** the
  defensive yield enters **both** the overlay and the comparator (each holds the same average `(1 − w*)` in it),
  so `edge = overlay − static = (f_t − w*)·(r_etf − r_liq)` — the yield *level* cancels from the binding
  comparison and only ever helps the overlay against the *reported* buy-and-hold. A **0%-cash floor** is kept
  as a **reported conservative diagnostic** (§6), non-gating.

---

## 4. The signal — reused verbatim, nothing to define here

The 0–5 score, its five conditions, the frozen buckets, the liquid breadth/A-D choice, the missing-VIX→0
rule, and the causality discipline are **all defined and signed in `v4/00` §4** and **implemented in
`swing_v4/regime.py`** (verified 2026-06-26: `RegimeScore.deployable_fraction` returns {0.0, 0.5, 1.0};
`n_factors=5` frozen; `n_factors=3` is the reported ablation only). **This prereg adds nothing to the signal
and is forbidden from touching it.** That is the entire reason K stays ≈ 1.

---

## 5. Benchmarks & the binding deploy bar (the sharp, honest test)

A regime overlay **trivially** cuts maxDD by being de-risked on average — so beating buy-and-hold proves
nothing. The real question is whether the **timing** adds value over just **statically holding the same
average mix**.

**5a. The static exposure-matched mix (the BINDING comparator — the purest "only timing differs").**
- Define `w*` = the overlay's **realized average daily deployed fraction** over the *same window*. `w*` is an
  **output**, not a tuned knob ⇒ it adds **0** to K.
- **Static mix** = constant weight `w*` in the **same Nifty 50 TRI** + `(1 − w*)` in the **same liquid fund**,
  **rebalanced monthly** through the same `costs.py` (base + pessimistic) and the same §3a expenses.
- This holds the **identical two assets at the identical average weight** as the overlay — **same asset, same
  fees, same average exposure; the *only* difference is *when* you are in each.** That is exactly the "isolate
  timing" experiment. If the overlay cannot beat it, the "edge" is just de-leveraging you could do statically
  for free — the Direction-D analog of "buy the index fund," and the honest answer becomes **"hold a static
  index/liquid-fund sleeve."**

**5b. Reported context comparators (non-gating).**
- **Buy-and-hold full Nifty 50 TRI** (w=1.0), base + pessimistic — the upside the overlay sacrifices. *(Note:
  B&H differs from the overlay in **both** average exposure and timing, and enjoys a structural tax-deferral
  edge the overlay does not, so it is context — not the binding bar.)*
- **Faber single-200-DMA timer** (textbook rule: 100% in the ETF when price > 200-DMA, else the liquid fund)
  — attribution: *is our richer 5-factor score worth it vs the naive single-SMA rule?* Reported, never a
  candidate.

**5c. The binding bar (DISCOVERY, §6 acceptance):** the overlay's **Calmar > the static exposure-matched
mix's Calmar at BOTH base and pessimistic cost**, with overlay **maxDD ≤ buy-and-hold maxDD** (sanity: the
overlay must actually de-risk). The buy-and-hold and Faber comparators are reported alongside.

---

## 6. Diagnostics & which checks gate (DISCOVERY)

| Check | Role | Gate? |
|---|---|---|
| **Deploy bar §5c** — Calmar vs static-matched, base **and** pessimistic; maxDD ≤ B&H | **HARD (binding)** | ✅ |
| Per-drawdown decomposition — share of the Calmar edge attributable to each de-risking episode | **DIAGNOSTIC** + **conditional label** if >90% from one event | ⚠️ label |
| Whipsaw — flip count/yr, cost-per-flip, total drag from switching | DIAGNOSTIC | — |
| **Linear exposure ramp** (`f = score/5`, on the same frozen score) | DIAGNOSTIC (does finer gradation help? if materially better → a **separate future prereg**, never a retro-candidate) | — |
| Realized-gain frequency / turnover (CGT-drag visibility) | DIAGNOSTIC (so the tax asymmetry vs B&H is visible, not hidden) | — |
| 3-factor ablation (`n_factors=3`) | DIAGNOSTIC (robustness of the signal tier) | — |
| 0%-cash floor (vs the real short-rate defensive asset) | DIAGNOSTIC (conservative sensitivity; neutral to the binding bar) | — |
| Faber single-200-DMA timer | DIAGNOSTIC (attribution: richer score vs naive rule) | — |
| Buy-and-hold full index | DIAGNOSTIC (context: sacrificed upside) | — |

**Conditional-label guard (binding):** if the per-drawdown decomposition shows **>90%** of the DISCOVERY
Calmar improvement comes from a **single** de-risking episode (almost certainly the COVID-2020 dodge), the
candidate carries a **"fragile / single-event" conditional label** all the way into the §9 verdict — it may
clear the bar but is **never** labeled cleanly "validated"; the OOS (a different regime) is then the real
adjudicator. *(Precedent: v4.8 87%-one-name flag; `v3/10` conditional label.)*

---

## 7. Deflation & K accounting (the headwind is finally surmountable — but honesty first)

- **K for this family ≈ 1.** Per the K-counting standard (`MEMORY.md` → distinct return-generating
  hypotheses, not metric evals): the locked overlay is the **one** return-generating config. `w*`, the
  static mix, buy-and-hold, the Faber reference, the 3-factor ablation, the **linear-ramp** and the
  **0%-cash-floor** sensitivities are **diagnostics / anchors / deterministic transforms → each adds 0**.
  K = **1** (or at most 2 if a second config is ever run, which §1 forbids). *(Critical: the linear ramp is a
  diagnostic, not a second arm — running it does not make this K=2, but **promoting** it to candidate after
  seeing its result would. That promotion is forbidden here; it can only seed a separate future prereg.)*
- At OOS (§8): report **raw Sharpe, K, deflated Sharpe** (`validation.deflated_sharpe`) and Calmar/maxDD at
  both cost levels. **PBO** is **N/A / not meaningful** for a single non-searched config (there is no search
  set to be overfit to) — stated, not hidden.
- **Honest caveat (binding, from `MEMORY.md`):** *fixing K never rescues a thin raw edge* — `v3/10` had K
  pushed as low as 69 and still deflated ≤ 0 because the **raw** edge was marginal. **Low K is necessary, not
  sufficient.** The overlay must show a **genuine raw Calmar edge over the static mix**, not just a low K. A
  deflated-Sharpe miss alongside a clean Calmar-deploy pass is reported as **"deploy-bar pass,
  deflation-marginal"** (the `v3/10` honesty), never upgraded.

---

## 8. Splits & the one-shot protocol (inherit the v4 dates)

- **DISCOVERY** = `validation.DISCOVERY (2018-02-06 → 2023-06-30)` — all of §5/§6/§7 lives here. This window
  **contains the COVID crash**, so the overlay's core value prop is testable in-sample; it is also where the
  single-event risk (§6) is most visible.
- **FINAL_OOS** = `validation.FINAL_OOS (2023-07-01 → 2026-06-12)` — touched **exactly once**, only after the
  locked overlay clears §5/§6 on DISCOVERY, and **never** on the null. The OOS run is the **byte-for-byte
  locked config** through the §12 simulator on FINAL_OOS — once, no re-tuning. Deploy bar evaluated OOS at
  base **and** pessimistic vs the OOS-window static-matched mix (each window matches its own `w*`).
- **Justification for inheriting the v4 split despite the v2/v3 OOS being spent:** the regime score was frozen
  **return-blind**, and this strategy (an index overlay) has **never been fit to returns** on any window. No
  parameter here has "seen" the FINAL_OOS. The split is reused unchanged (no moved stick, `v3/00` §1).

---

## 9. Definition of Done (the deploy verdict)

The overlay is **"validated, deployable (pending forward probation)"** only if the single locked config, on
the one-shot FINAL_OOS:
- **Beats the static exposure-matched mix on Calmar at base AND pessimistic cost**, with maxDD ≤ buy-and-hold;
  AND
- The DISCOVERY result was not a fluke (the OOS Calmar edge over the static mix does not collapse); AND
- **Raw + deflated Sharpe reported together** (§7), with a genuine raw edge (low K is not a free pass).

**Conditional ceiling (binding, §6):** if the edge is >90% single-event on DISCOVERY, the best attainable
verdict is **"validated-conditional (single-event / fragile)"** — deployable only with that disclosed caveat,
not cleanly validated.

**Pre-accepted null (the honest, money-saving close):** if the overlay **fails to beat the static-matched mix
at pessimistic cost** on DISCOVERY, it is a **research note** — `FINAL_OOS` stays **pristine**, the OOS run is
**not** performed, and the earned conclusion is **"hold a static index/cash sleeve (or just the full index)"**
— itself a clean, deployable answer for ₹3.5L of spare capital. A null is **not** a prompt to add a knob,
relax the bar, change the instrument, or re-pick the idle sleeve (`v3/00` §1, Rule 12).

---

## 10. What this prereg does NOT do (guards)

- It does **not** define, tune, or touch the regime score (§1, §4) — verbatim reuse of `swing_v4/regime.py`.
- It does **not** search a grid, an instrument, a bucket cut, or an operating point (§1, §3).
- It does **not** soften the §5 binding bar, the §6 conditional-label guard, or the §7 deflation reporting.
- It does **not** move `validation.DISCOVERY` / `validation.FINAL_OOS` (§8).
- It does **not** touch `FINAL_OOS` until a single DISCOVERY-cleared config exists, and **not at all** on the
  null (§8, §9).
- It does **not** re-open v2/v3/v4 — those stand closed; this is a **new family** (`v3/00`/`v2/07`: each
  forward option is a separate new prereg).

---

## 11. Locked commitments (Arafat — sign to flip DRAFT → LOCKED)

Confirm or redline each before any code/run:

1. **Candidate = pre-specified frozen overlay** (§3): Nifty 50 TRI held vs a liquid-fund defensive asset;
   `f` from the verbatim 5-factor `RegimeScore` (`neutral_fraction=0.5`, **frozen 3-bucket map**); trade only
   on bucket change, score(D)→trade(D+1 open); ₹3.5L. **Linear ramp = §6 diagnostic, never the candidate.**
2. **Signal frozen verbatim** (§4) — no touch to weights/cuts/factors/buckets; contributes 0 to K.
3. **Costs & defensive asset** (§3a): `costs.py` base+pessimistic on switch notional; ~0.05%/yr ETF + ~0.20%/yr
   liquid-fund expense; **defensive asset = a real short-rate liquid fund (primary)**, 0%-cash a reported floor.
4. **Binding bar = beat the static exposure-matched mix** (§5; same ETF + same liquid fund, constant `w*`) on
   Calmar at base **and** pessimistic, maxDD ≤ buy-and-hold; buy-and-hold + Faber-200DMA reported as context.
5. **Diagnostics & conditional label** (§6): per-drawdown, whipsaw, linear-ramp, realized-gain frequency,
   3-factor, 0%-cash floor, Faber — all reported, non-gating; **>90% single-event ⇒ "fragile" conditional
   label** carried to verdict.
6. **K ≈ 1; deflation reported honestly** (§7) — low K is necessary, not sufficient; PBO N/A for a single
   config; a genuine raw Calmar edge over the static mix is required.
7. **Inherit `validation.DISCOVERY` / `FINAL_OOS`** (§8); `FINAL_OOS` spent **exactly once**, only on a
   DISCOVERY-cleared locked config, under §8/§9; pristine on the null.

> **Signed:** Arafat — 2026-06-26  (DRAFT → LOCKED; RO0 authorized — execution deferred to a cold session)

---

## 12. Execution (cold-session runnable — DISCOVERY only until the candidate is cleared)

> Read this file + the one stage you are doing. Honor the token budget (Rule 6). Update Status, fill a
> Session log, check off Done-criteria. Do not mark Done if anything was skipped (Rule 12). Reuse existing
> code (`regime.py`, `benchmark.py`, `costs.py`, `robustness.py`, `validation.py`); the new module is small
> and self-contained — **not** the `backtest_v2`/`swing_v4` engines (this is a one-instrument simulator).

### RO0 — dependency verify + build the overlay simulator (no returns yet)
- **Status:** ✅ DONE — 2026-06-26. Simulator + comparators + defensive loader built and
  tested (13 green); all three real series verified + aligned; **no DISCOVERY/OOS return
  measured**; `FINAL_OOS` untouched.
- **Do:** (a) verify `benchmark.load_tri(TRI_NIFTY_50)` returns a real, gap-checked Nifty 50 **TRI** over
  2018–2026 AND a Nifty 50 **price** series for the regime DMAs (fail loud on miss); (a′) source + gap-check a
  **real short-rate series** for the defensive asset (91-day T-bill or a liquid-fund index; one-off cache-miss
  fetch allowed, **no live API in `pytest`** — CLAUDE.md §5); (b) build `app/regime_overlay/overlay.py` — a
  pure simulator: inputs = TRI series, defensive short-rate series, `RegimeScore`, cost model, expenses; for
  each day apply `f(D)` to `D+1`, switch on bucket change, accrue switch costs / ETF + liquid-fund expense /
  defensive return, emit a daily NAV; (c) build the **static exposure-matched mix**, **buy-and-hold**, and the
  **Faber-200DMA** + **linear-ramp** diagnostic comparators in the same module; (d) unit tests (synthetic, no
  live API): a known score path → exact switch dates, exact cost on a known `Δexposure`, `w*` computed
  correctly, defensive-leg accrual correct, causality (no `D` value used before `D+1`).
- **Done-criteria:** module + tests green; **no DISCOVERY/OOS return measured**; Nifty 50 TRI + price + the
  short-rate series all confirmed real and aligned to the trading calendar; `FINAL_OOS` untouched.

#### RO0 — Session log (2026-06-26)
**Built** (`backend/app/regime_overlay/`, additive — touches no existing module):
- `overlay.py` — the pure close-to-close one-instrument simulator. `simulate(fraction, tri,
  defensive, cost_cfg, overlay_cfg, rebalance)`: equity (TRI) calendar authoritative; defensive
  overnight leg as-of **ffilled** onto it; causal **1-day signal lag** (score on close `D` trades at
  `D+1` open — day 0 sits in cash, no look-ahead); switch cost = `costs.fill_cost` (statutory) **+
  `base_slippage_pct` on the traded ETF notional `|Δequity|`**, defensive leg STT-free; cost reduces
  NAV then splits to target (no phantom negative-cash at a 100% deploy); daily ETF (0.05%/yr) + liquid
  (0.20%/yr) holding-cost accrual. Emits NAV, applied-fraction path, **`w*`** (mean applied fraction —
  an output), flip count, total switch ₹. Fraction-path builders: `overlay_fraction` (frozen 3-bucket
  candidate), `static_fraction` (constant `w*`, `rebalance="monthly"` = the §5a binding comparator),
  `faber_fraction` (200-DMA timer), `linear_ramp_fraction` (`score/5` diagnostic). `metrics_from_nav`
  reuses `metrics._cagr_from_equity` + `_compute_max_drawdown` → Calmar/maxDD/CAGR/Sharpe.
- `short_rate.py` — `load_defensive_index(...)`, mirroring `benchmark.load_price_index` (injectable
  `_fetch_fn`, atomic parquet cache, fail-loud-on-empty).
- `tests/regime_overlay/test_ro0_overlay.py` — 13 synthetic tests (no live API): causality lag, exact
  switch cost on a known Δ, `w*`, defensive accrual, defensive ffill onto a sparser calendar, monthly
  static rebalance count, Faber DMA cross, metrics drawdown, fail-loud on a TRI gap, loader parse/cache/
  empty-raise. **13 passed**; reused `benchmark`/`regime` suites still green (53 combined, additive-only).

**Defensive asset — sourced + LOCKED (within the §3a pre-authorized "91-day T-bill *or* a liquid-fund
index" choice; not a stick-move):** the **Nifty 1D Rate Index** (NSE's overnight-rate index, the
canonical liquid/overnight-fund proxy), pulled from the niftyindices *price* endpoint (cumulative CLOSE
level; `pct_change` = realised daily overnight return). Fetched + cached real over 2017-01-02 → 2026-06-12.

**Dependency verification (all real, gap-checked, aligned — RO0 a/a′):**
| Series | rows | span | overlay-window exact-date hits | post-ffill holes |
|---|---|---|---|---|
| Nifty 50 **TRI** | 2340 | 2017-01-02 → 2026-06-12 | — (authoritative cal) | 0 |
| Nifty 50 **price** | 2340 | 2017-01-02 → 2026-06-12 | 2067/2067 | 0 |
| **Nifty 1D Rate Index** | 2184 | 2017-01-02 → 2026-06-12 | 1917/2067 (sparser publish cal) | **0** (ffilled) |

The rate index: daily return min **+0.0062%** / max +1.86% / **0 negative days** / **~5.72%/yr** mean —
a clean accruing overnight series. Price shares the TRI calendar exactly; the rate index publishes on a
slightly sparser calendar but covers every trading day after as-of ffill (the simulator's alignment).
**No returns measured; all data sliced ≤ 2026-06-12; `FINAL_OOS` (2023-07-01 → 2026-06-12) untouched.**

**Process note (not a stick-move):** an early-session claim that "network is fully blocked" was **wrong** —
the default tool sandbox blocks network on tool calls; the one-off real fetch (§12 RO0 a′: "one-off
cache-miss fetch allowed, no live API in pytest") runs fine with the sandbox disabled, and **no live
network touches `pytest`** (tests inject stub fetches). Cache parquet lives under the gitignored
`backend/data/niftyindices/` (consistent with the existing TRI/price caches) — not committed.

### RO1 — DISCOVERY headline + full diagnostics + §5 acceptance
- **Status:** ✅ DONE — 2026-06-26. **§5c BINDING BAR FAILED — hard, at both cost levels →
  §9 PRE-ACCEPTED NULL → RESEARCH-NOTE CLOSE. RO2 N/A. `FINAL_OOS` PRISTINE (never loaded into
  any window — all four series sliced ≤ DISCOVERY end before simulation).** The frozen overlay
  whipsaws to death: **598 bucket flips over 1333 DISCOVERY days (~113/yr, mean dwell 2.2 days),
  ₹229k switch cost on a ₹350k book** — **wall #1 (turnover) was NOT disarmed.** The prereg's core
  premise (§0: "trade only on bucket change ⇒ a handful of switches/year") is **empirically false**:
  the score's three *daily* internals (breadth / A-D / VIX) flicker across the 1↔2 and 3↔4 bucket
  boundaries constantly (score itself changes 818/1333 days).
- **Do:** run the locked overlay on `DISCOVERY` at base + pessimistic; compute `w*`, the static-matched mix,
  buy-and-hold, Faber-200DMA; report the §6 table (Calmar/maxDD/turnover/flip-count for each); run the
  per-drawdown decomposition + the 3-factor/liquid-fund sensitivities; apply the §5c binding bar; assign the
  §6 conditional label if >90% single-event. Log the one config to a family `ConfigLedger` (K=1). **No
  FINAL_OOS.**
- **Done-criteria:** per-comparator metrics table; binding-bar PASS/FAIL stated at both cost levels;
  per-drawdown attribution + single-event verdict; honest "clears bar / fails / deflation-marginal" call;
  `FINAL_OOS` untouched (TRI sliced ≤ DISCOVERY end). **If FAIL at pessimistic ⇒ §9 null close; RO2 N/A.**

#### RO1 — Session log (2026-06-26)
**Ran** (`backend/app/regime_overlay/ro1_discovery.py`, additive; report → `backend/reports/ro1_discovery.txt`):
wired the **real cached** series (Nifty 50 TRI / Nifty 50 price / Nifty 1D Rate Index / `market_internals`
regime), all sliced **≤ 2023-06-30** before any sim, into the RO0 `overlay.simulate`. **1333 DISCOVERY
trading days**; frozen 5-factor `RegimeScore` (`neutral_fraction=0.5`); `w* = 0.6193`. **K=1** (one config
in the family `ConfigLedger`).

**Headline table (base | pessimistic), DISCOVERY:**
| Series | Calmar | maxDD | CAGR | Sharpe | flips | switch ₹ |
|---|---|---|---|---|---|---|
| **Overlay (CANDIDATE) base** | **−0.155** | 37.6% | −5.82% | −0.527 | 599 | 228,963 |
| **Overlay (CANDIDATE) pess** | **−0.237** | 57.5% | −13.64% | −1.356 | 599 | 290,101 |
| Static w*-mix (**BINDING**) base | **0.419** | 24.4% | 10.23% | 0.926 | 65 | 1,752 |
| Static w*-mix (**BINDING**) pess | **0.418** | 24.4% | 10.20% | 0.923 | 65 | 2,450 |
| Buy&Hold TRI (ctx) base | 0.343 | 38.3% | 13.14% | 0.762 | — | — |
| Faber-200DMA (ctx) base | 0.241 | 22.1% | 5.32% | 0.496 | 55 | — |

**§5c binding bar — FAIL (not marginal):** overlay Calmar **−0.155 ≤ static 0.419** (base) AND
**−0.237 ≤ 0.418** (pess) → both legs FAIL; the maxDD-≤-B&H sanity leg passes (37.6% ≤ 38.3%) but the
binding Calmar test is failed at *both* cost levels. The overlay even **loses to plain buy-and-hold**
(0.343). **The static w*-mix (0.419) — same two assets, same average exposure, only timing removed —
beats B&H on Calmar with far lower maxDD (24.4% vs 38.3%): the §5 thesis confirmed empirically —
"the de-risking is valuable, but only done *statically*; the *timing* destroys it."**

**Per-drawdown decomposition (overlay edge over static, base):** the overlay **loses in EVERY B&H crash
window** — 2018 −14.0%, 2019 −11.4%, **COVID-2020 −16.0%**, 2022 −18.5%, 2023 −6.9% edge. Σ positive
episode edges = **0** ⇒ single-event share N/A ⇒ **NOT single-event-fragile** — it is *uniformly*
cost-dominated, a stronger negative than fragility (it never even dodged COVID net of its own whipsaw).

**Diagnostics (non-gating, each 0 to K):** linear ramp (`score/5`) base Calmar **−0.116**; 3-factor
ablation **−0.041**; 0%-cash floor **−0.189** (vs −0.155 real-rate). **Nothing rescues it** — and §1
forbids re-picking regardless.

**Whipsaw is the killer (the headline finding):** **598 bucket flips / ~113 per year / mean dwell 2.2
days**; switch cost **₹228,963 on a ₹350k book (65% of capital bled to costs)**. Verified this is an
**intrinsic property of the frozen score, not a sim artifact** (raw fraction-change count = 598
independent of the simulator; score changes 818/1333 days). The 3 *daily* internals (liq-breadth,
liq-A/D, VIX) flicker across the 1↔2 and 3↔4 bucket boundaries continuously ⇒ **wall #1 (turnover)
re-materialized**, contradicting the §0 premise. No hysteresis / debounce exists in the frozen map, and
adding one is a *new signal* (§1/§4 forbidden) ⇒ the candidate-as-frozen is decisively null.

**§9 VERDICT:** **RESEARCH-NOTE NULL** — fails the §5c binding bar at pessimistic (and base). `FINAL_OOS`
**stays pristine**, the OOS run is **not** performed (RO2 N/A), and the earned conclusion is
**"hold a static index/liquid-fund sleeve"** — concretely the static `w*≈0.62` mix (Calmar 0.419, maxDD
24.4%), a clean deployable answer for ₹3.5L. A null is **not** a prompt to add hysteresis, relax the bar,
or re-pick the map (§1, Rule 12) — any debounced/EMA-smoothed regime timer is a **separate future prereg**
with its own K, not a continuation of this one.

### RO2 — one-shot FINAL_OOS + §9 verdict (only if RO1 clears the bar)
- **Status:** ⛔ N/A — RO1 failed the §5c binding bar (pre-accepted null, §9). `FINAL_OOS` stays
  **PRISTINE** for this family; the one-shot OOS run is **not** performed.
- **Do:** byte-for-byte locked overlay through the RO0 simulator on `FINAL_OOS` — **once**. Deploy bar at
  base + pessimistic vs the OOS-window static-matched mix; raw + deflated Sharpe (K=1); per-drawdown on the
  OOS window. Mark `FINAL_OOS` consumed for this family.
- **Done-criteria:** §9 verdict (validated / validated-conditional / research-note); `FINAL_OOS` marked
  consumed; deflation reported honestly (Rule 12 — no softening to manufacture a pass).

---

## Exit criteria
- [x] §11 signed by Arafat (DRAFT → LOCKED) — 2026-06-26.
- [x] RO0 — simulator + comparators built, deps verified, tested; no returns measured; FINAL_OOS untouched. — 2026-06-26.
- [x] RO1 — DISCOVERY headline + diagnostics + §5 binding-bar verdict; FINAL_OOS untouched. **NULL: overlay
      Calmar −0.155/−0.237 ≤ static 0.419/0.418 at base/pess (598 flips/yr-equiv ~113, ₹229k switch cost) ⇒
      §9 RESEARCH-NOTE CLOSE; family closes. — 2026-06-26.**
- [ ] RO2 — N/A (RO1 did not clear the bar); `FINAL_OOS` PRISTINE, one-shot OOS not performed.

---

## 13. Deviations (reserved)
*(Empty at lock. Any post-result stick-move is recorded here openly, `v3/10` §13 style — never as a quiet
threshold edit — so the record cannot later be read as a clean validation.)*
