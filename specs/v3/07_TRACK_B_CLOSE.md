# v3 / 07 — Track B (Value / Quality): Research-Note Close

> **Status: CLOSED as a research note — 2026-06-20 (Arafat).**
> Terminal record for the Track-B (value/quality diversification, H3) line of work pre-registered in
> `03_TRACK_B_PREREG.md`. The full TBE2–TBE7 session logs, per-factor coverage tables, and per-layer
> §6 batteries live in `04_TRACK_B_EXEC_TASKS.md`; this doc is the consolidated verdict and the
> forward decision. **`FINAL_OOS` (2023-07-01 → 2026-06-12) was never consumed — pristine.**

---

## Verdict

Track B asked one question (H3, `03` §2): does adding an **orthogonal** return source — value
(E/P, B/P) and/or quality (ROE, accruals, leverage) — to the Track-A momentum composite repair the
§6.4 subperiod-concentration weakness and clear the `00`/`03` §9 deployment bar on the Track-B
`DISCOVERY` window (2020-01-31 → 2023-06-30)?

**No.** No layer earned a place, the single pre-committed candidate (Track-A baseline) fails the §6
battery, and **H3 is not confirmed — its primary predicate is vacuous on this window.** This is the
**pre-accepted §9 null outcome** (`03` §9/§10), not a softened or abandoned search.

## What was tested (evidence in `04`)

- **TBE2b (data fix, commit `7ffc4e64`):** XBRL `shares_outstanding` tag-mapping bug fixed; panel
  re-ingested (0 → 45,539 non-null). **Unblocked the value block** — E/P 91.7%, B/P 89.8%,
  value_block 92.3% coverage, all momentum-orthogonal (|ρ| < 0.3). Verified TBE4 ran *on* this data
  (fresh DB read at runtime; result moved off the baseline → value factors were non-empty).
- **TBE4 — Layer B1 (Value {E/P, B/P}, commit `66e885d6`): DROPPED.** Calmar 1.591 → 1.216
  (Δ −0.375); §6.4 spread **worsened** +0.71×. Honest-drop rule (`03` §6).
- **TBE5b (data fix, commit `fca89fce`):** leverage rescued via the disclosed `DebtEquityRatio` tag
  (fallback when `total_debt` absent — mathematically equivalent, a sourcing improvement not a
  redefinition). Leverage coverage 21.7% → 54.5%. Accruals **unchanged at 17.2%** — needs CFO +
  total_assets, absent from the results-only DISCOVERY filings.
- **TBE5 — Layer B2 (Quality {ROE, accruals, leverage}, commit `2e8e7db3`): DROPPED.** Calmar
  1.591 → 1.024 (Δ −0.567); max-DD worsened 15.1% → 19.9%. §6.4 spread narrowed (2.07× → 1.22×) but
  the headline Calmar degraded — judged on Calmar per `03` §6. Honest-drop.
- **TBE6 — Layer B3 (block-weight): N/A.** Gate not met — neither B1 nor B2 was accepted, so there
  is nothing to weight (`03` §6 gate). No run, no `FINAL_OOS` touch.
- **TBE7 — candidate §6 battery + deflation/PBO + H3 verdict (commit `673144e9`):** single locked
  candidate = Track-A baseline (B1/B2 dropped, TBE6 N/A). Base run reproduces the TBE3 anchor exactly
  (Calmar **1.591**, Sharpe 1.335 — wiring sane). §6 battery **3/5 PASS** (fails §6.2 retention 33%,
  §6.3 lone-peak). Raw Sharpe 1.335 → **DSR 0.092 at K = 46**. PBO 0.00 (coarse, 2 folds).
- **TBE8 — one-shot `FINAL_OOS`: N/A.** Gate (TBE7 PASS + H3 confirmed) not met. **Not run.**

## Why this is a robust null (not a technicality)

The close rests on **two independent grounds**, either sufficient on its own (`04` TBE7):

1. **H3 not confirmed — vacuous predicate.** The H3 primary predicate (`03` §2) is "§6.4 passes
   *where the Track-A baseline failed*." TBE3's critical finding is that the baseline **already
   passes** §6.4 on this window — so there is no failure to repair, and the predicate cannot be
   satisfied by construction. The supporting-evidence path is empty too: both fundamental layers were
   dropped, so no accepted layer narrows the spread. H3 is dead on this window independent of any
   performance number.
2. **The candidate fails the §6 battery independently.** §6.2 retention 33% (need ≥ 70%) and §6.3
   lone-peak both fail. And the deflation result — **DSR 0.092 at K = 46** — says essentially none of
   the raw edge survives multiple-testing correction. No single rule-relaxation rescues this: the
   failures are on different axes, and *more search strictly lowers DSR* (K rises monotonically).

Both fundamental blocks did exactly the mechanistic thing H3 described (quality narrowed the §6.4
spread) yet **degraded the headline** — bolting equal-weight orthogonal factors onto an already
concentrated momentum composite dilutes it. That is a property of the construction + universe, not a
config artifact.

## Discipline ledger

- **No stick moved.** No factor weight tuned, no threshold loosened, no split re-sliced, no
  sector-neutralization or EBIT/EV smuggled in (`03` §10, §11). Every drop used the pre-committed
  honest-drop rule.
- **`FINAL_OOS` pristine** — touched zero times across TBE2b–TBE7; the null close forbids the OOS run
  (`03` §9). TBE8 explicitly N/A.
- **K accounting:** cumulative **K = 46** at TBE7 (16 Track-A + 4 TBE3 + 4 TBE4 + 4 TBE5, TBE6 N/A,
  + 18 TBE7 ledger entries). A fresh family does **not** reset K — read from the ledger at any future
  OOS (`03` §7).
- **Data fixes were sourcing improvements, not gate changes.** TBE2b/TBE5b fixed XBRL tag mappings;
  they did **not** re-open the §6 data gate, move a threshold, or zero-fill a NULL (`03` §10).

## What the data fixes did and did **not** reach

| Signal | Pre-fix | Post-fix | Tested? |
|---|---|---|---|
| E/P, B/P (value) | 0% (dead) | ~90% (TBE2b) | ✅ TBE4 → dropped |
| ROE | ~90% | ~90% | ✅ TBE5 → block dropped |
| leverage | 21.7% | 54.5% (TBE5b) | ✅ TBE5 → block dropped |
| **accruals** | 17.2% | **17.2% (unreached)** | ⛔ data-blocked — needs a balance sheet |

The only fundamental signal neither fix could reach is **accruals**: it needs CFO + total_assets,
which the results-only Indian XBRL filings in this panel do not carry. That is a *data-availability*
gap, not an untested idea — and it is the lever the next experiment must clear at the source.

## Forward decision (Arafat, 2026-06-20) — escalation checkpoint reached

`06` §forward put a condition on the record: **"if the value/quality path also ends as a research
note, we stop building and have a hard conversation about reconsidering the deployment bar
(§9 maxDD ≤ 70%) and/or the universe — *before* any further construction."** Track B has now ended as
a research note. **That checkpoint is reached.** No new layer, config, or window may be run against
this prereg.

Two things — and only these two — add genuinely *new* information rather than more trials on an
exhausted family. Each requires a **fresh pre-registration with its own pristine OOS**; neither can
retroactively flip this verdict:

1. **A real balance-sheet data source.** Unblocks accruals at full coverage and a cleaner
   leverage/value signal sourced from the balance sheet rather than a results-filing fallback. This
   is the precondition for any honest quality retest.
2. **Value-as-a-tilt construction** (residualized / momentum-orthogonalized overlay or a small tilt),
   committed up front — **not** the equal-weight rank-blend member that demonstrably diluted the
   composite here (`03` §11 currently locks equal-weight; changing it is a new prereg by `03` §10).

**Escalation question for the hard conversation (deliberate, eyes-open — the v1 sin is moving the bar
*during* a search; this is a pre-registered redesign decision at the explicit checkpoint):** is the
`00`/`03` §9 deployment bar (beat Nifty200 Momentum 30 TRI on Calmar **and** max-DD ≤ 70% of
benchmark, **all five** §6 checks) appropriate for this **Indian mid-cap universe**, or is the
universe itself the binding constraint? Both the momentum-only null (`06`: §6.2 thin concentrated
edge) and Track B (orthogonal sources dilute, not repair) point at the same structural place. Resolve
that **before** any further construction.

---

## Status of the v3 arc

- **Track A (momentum baseline):** characterized; baseline unexpectedly passes §6.4 (TBE3) → made the
  H3 predicate vacuous. CLOSED.
- **Momentum-only deployment (`05`/`06`):** NULL CLOSE — no config earns the OOS.
- **Track B (value/quality, `03`/`04`/this doc):** RESEARCH-NOTE CLOSE — H3 not confirmed + §6 fails.
- **`FINAL_OOS`:** **PRISTINE.** Never consumed across the entire v3 arc.

> **Signed:** Arafat — 2026-06-20 (Track B closed as a research note; `FINAL_OOS` pristine;
> escalation checkpoint reached — balance-sheet data source + value-as-tilt + a deployment-bar/universe
> review are each a *new* pre-registration, not a continuation of this one).
