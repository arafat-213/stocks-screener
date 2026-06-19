# v3 / 06 — Momentum-Only Deployment: Research-Note Close

> **Status: CLOSED as a research note — 2026-06-19 (Arafat).**
> Terminal record for the momentum-only deployment line of work pre-registered in
> `05_MOMENTUM_DEPLOY_PREREG.md`. The full MD1/MD2 session logs and per-config §6 tables
> live in `05` (§ "Execution" + "Research Note"); this doc is the consolidated verdict and
> the forward decision. **`FINAL_OOS` (2023-07-01 → 2026-06-12) was never consumed — pristine.**

---

## Verdict

The §4 grid (12 configs, M × smoothing × cadence) was searched on the **honest full DISCOVERY
window (2018-02-06 → 2023-06-30)** for a lower-turnover momentum config that survives realistic
costs and sits on a robust plateau. **No config earns the one-shot OOS.** Momentum-only
(5-factor, N=20, Track-A construction) is **not robustly deployable** on this universe and window.
This is the **pre-accepted §5 null outcome**, not a softened or abandoned search.

## What was tested (evidence in `05`)

- **MD1 (Stage 1, commit `b8872a3b`):** all 12 configs cost-screened. **2 cleared §6.1** — M=130
  sm=0 monthly (Calmar 0.523, turnover 706%, ratio 1.35) and M=200 sm=0 monthly (Calmar 0.550,
  turnover 617%, ratio 1.45). Smoothing=3 and quarterly cadence failed universally.
- **MD2 (Stage 2, commit `7803c539`):** full §6 battery + the §5 acceptance rule on both
  survivors. **Both eliminated.** MD3 (one-shot OOS) **N/A** — no locked candidate.

## Why this is a robust null (not a technicality)

Both survivors failed on **three independent axes** — relaxing any single rule rescues nothing:

1. **§6.2 retention 43% / 34%** (need ≥70%) — *the structural barrier.* Momentum's edge concentrates
   in ~10 mid-cap winners; drop them and a third-to-half of the P&L leaves. This is a property of
   momentum in the Indian mid-cap universe, not a config artifact.
2. **§5.4 deployment bar — maxDD ratio 0.77 / 0.80** (need ≤0.70 of benchmark). Both *beat* Nifty200
   Momentum 30 TRI on base-cost Calmar (0.523 / 0.550 vs 0.473), so it is a **drawdown** problem, not
   a return problem — and drawdown is your stated minimize-this objective.
3. **§6.3 plateau** — both are isolated lever spikes, not regions (smoothing=3 / quarterly cliff in
   every direction). Predicted from MD1 data; confirmed in MD2.

§6.1 (cost) is *passable* with a wider sell buffer — the T6 cost problem is soluble. §6.4 (diagnostic
only) confirms heavy regime dependence (Post-COVID bull Calmar 5.8–7.0× other subperiods).

## Discipline ledger

- **No stick moved.** No lever level added, no threshold loosened, no window re-sliced (`00` §1, §10).
- **`FINAL_OOS` pristine** — touched zero times across MD1/MD2; the null close forbids the OOS run (§5/§8).
- **K accounting:** MD1 logged K=24, MD2 logged K=10 to `ConfigLedger`; cumulative K is read from the
  ledger at any future OOS, never reset by a fresh objective (`05` §7).

## Forward decision (Arafat, 2026-06-19)

1. **Next = the value/quality re-ingest path, in a separate cold session.** MD2's §6.2 failure *is*
   the diagnosis: a thin, concentrated edge is fixed by adding an **orthogonal** return source
   (value/quality), not by more momentum knob-tuning — which is now exhausted. This **promotes** the
   re-ingest from "~6 months out" to the immediate next step.
   - Concrete blocker (TBE2, `04`): `shares_outstanding` = 0 non-null and `total_debt` = 2.5% non-null
     in the panel → E/P, B/P, leverage are dead; ROE (~90%) already healthy. Root cause = XBRL
     tag-name mismatch. **TBE2b** = fix the tag mappings, re-ingest the panel, verify coverage →
     then TBE4 (value block) becomes runnable.
2. **Escalation condition (on the record):** **if the value/quality path (TBE2b → TBE4 …) also ends as
   a research note, we stop building and have a hard conversation about reconsidering the deployment
   bar (§9 maxDD ≤70%) and/or the universe — *before* any further construction.** Reconsidering the
   bar after a result is the v1 sin and is off-limits *during* a search; it is only legitimate as a
   deliberate, pre-registered redesign decision taken at this explicit checkpoint, eyes open.

> **Signed:** Arafat — 2026-06-19 (momentum-only closed; value/quality re-ingest authorized next).
