# Spec 07 — Merger / Cancellation *Identity* Continuity (open data-layer gap)

> **Status: DRAFT — awaiting owner decision (§5 strategy is NOT locked).** Surfaced
> 2026-06-22 by `06` T06.5's re-warm-start (`specs/v2/06_ISIN_SUCCESSION_CONTINUITY.md` §15).
> This is the **third layer** of the same identity root cause: `05` fixed CA price-adjustment
> across an ISIN change; `06` stitched **face-value successions** (one company, new ISIN) into
> one `instrument_id`; **`07` is the still-open case of a holding whose company TERMINATES —
> merged into a *different* entity, or cancelled — with no face-value successor.** A cold
> session can pick this up from this doc; nothing here depends on un-committed state.
>
> **Relationship to `06` (read first).** `06` deliberately scoped itself to face-value
> re-issues (old + new ISIN are the *same* company, consecutive-day handover, incrementing
> ISIN suffix). Mergers/cancellations are a *different* event: the holder's economic value
> migrates to the **acquirer's** shares (a different instrument, at a swap ratio) or is
> **cancelled** (DVR scrap, insolvency). `06`'s successor map correctly does **not** assert
> these (there is no same-company successor pair), so they fall through as carried-unsellable
> ghosts. `06` is DONE-for-its-scope; `07` is the next layer, not a `06` bug.

---

## 1. The gap in one sentence

When a held company is **merged into another entity** (share-swap, e.g. HDFC→HDFCBANK,
MINDTREE→LTIMINDTREE) or its security is **cancelled** (e.g. TATAMTRDVR DVR scrap, an
insolvency delisting), its ISIN stops trading with **no face-value successor**, so a held
position has no forward price, can never be sold, and is carried as an **MTM-frozen ghost** —
occupying a book slot and freezing dead capital indefinitely.

## 2. How it surfaced (`06` T06.5)

After `06` stitched the 4 face-value successions, the re-warm-started S3 paper book
(inception→2026-06-18, shadow-parity 0.0 bps) still held **3 carried-unsellable ghosts**,
all of this distinct class:

| Symbol | Held (dead) ISIN | Cause | Carried since |
|---|---|---|---|
| HDFC | INE001A01036 | merged into HDFC Bank (share swap, Jul 2023) | 2023-07-13 → edge (722 d) |
| INOXLEISUR | INE312H01016 | merged into PVR → PVR INOX (share swap, 2023) | 2023-02-17 → edge (819 d) |
| TATAMTRDVR | IN9155A01020 | DVR shares cancelled (2024) | 2024-08-30 → edge (445 d) |

They MTM-freeze **~₹315K** (book equity − cash at the edge). Because the live warm-start is
byte-identical to the backtest, the backtest carries them too.

## 3. Blast radius (full universe, 2017→2026, measured 2026-06-22)

Methodology mirrors `06` §3 (`backend/scripts/merger_ghost_blast_radius.py`): per-ISIN
lifetimes from `prices_adjusted`; a **termination** = last trade > 15 calendar days before the
store edge (2026-06-19); **exclude** asserted succession old-legs (`06` handles those) and any
ISIN whose `instrument_id` chain still trades at the edge; **liquid-at-death** = `adv_20` on the
ISIN's last trading day ≥ ₹5cr (the S3 floor; same definition `06` §11 pinned).

| Metric | Count |
|---|---|
| Distinct ISINs | 3,472 |
| Terminated, no face-value successor | 672 |
| **...liquid at death (≥ ₹5cr ADV) → S3-eligible, ghost risk** | **75** |
| ...liquid **and** recent (≥ 2023) | 53 |

Top liquid terminations are exactly the names a momentum book would have held: `HDFC`,
`TATAMTRDVR`, `MINDTREE` (→LTIMINDTREE), `STLTECH`, `RELINFRA`, `JETAIRWAYS`, `IDFC` (→IDFC
First Bank), `UJJIVAN`, `GSKCONS` (→HUL), `BHARATFIN` (→IndusInd), `GRUH` (→Bandhan), `CAIRN`
(→Vedanta), `ABIRLANUVO` (→Grasim), `TATASTLBSL`, `JPASSOCIAT`. These span three sub-types that
need different handling (see §5):

1. **Share-swap merger** — value migrates to the acquirer at a ratio (HDFC, MINDTREE, IDFC…).
2. **Outright cancellation** — value is scrapped (TATAMTRDVR DVR; some insolvencies).
3. **Voluntary delisting / insolvency suspension** — trading stops, residual/zero value
   (JETAIRWAYS, JPASSOCIAT, RELINFRA).

> **Count caveat (for the cold session to tighten in T07.1).** The 15-day cutoff can also
> catch a name with a trailing *data* gap rather than a true termination — a cluster shares
> `last_date = 2026-05-18` (QPOWER, KRN, INDOTECH, STYLEBAAZA, DEEDEV, IDEAFORGE), which may
> be recent suspensions or data staleness, not delistings. Treat **75 / 53** as a scoping
> estimate; T07.1 must classify each by sub-type (the way `06` T06.1 refined §3's counts).

## 4. Root cause & why `05`/`06` don't cover it

- `05` fixed the **price-adjustment** anchor across a CA on a *still-trading* ISIN.
- `06` stitched **identity** for a face-value re-issue: same company, consecutive-day handover,
  one `instrument_id`. Its three converging signals (consecutive trading-day handover, INE
  issuer-prefix with incrementing suffix, face-value-split CA) are **all absent** for a merger:
  the acquirer is a *different* issuer (different INE prefix), there is no consecutive handover
  (the position should map to the acquirer's *already-trading* ISIN, not a next-day new leg),
  and the CA feed carries **no merger event** (see §5 data constraint). So `06` correctly
  leaves these in `successor_unmatched` / untouched.

## 5. The hard data constraint (why this needs an owner decision, not just code)

**The persisted CA feed has only `type ∈ {split, dividend, bonus}` — there is NO merger,
amalgamation, scheme-of-arrangement, or delisting event in the repo.** So, unlike `06` (which
bootstrapped entirely from data already on disk), a merger **remap onto the acquirer at the
correct swap ratio cannot be derived from existing data.** This is the same shape of blocker as
Track-B's missing balance-sheet data and `08`'s missing index-constituent data: a real defect
that is **data-blocked**, so the fix is a *decision*, not a mechanical task.

### Candidate approaches (TRADE-OFFS — none locked; owner picks in §6)

| Approach | What it does | Pro | Con |
|---|---|---|---|
| **A. Write-off / force-exit at termination** *(recommended starting point)* | On an ISIN's last trade with no successor, **liquidate the held position to cash at the last price** (and bar re-entry). No external data. | Zero new data; removes the ghost + frees the slot + frees capital; honest (you *could* have sold near the end). Cheapest, unblocks the probation. | Slightly optimistic for insolvencies that gapped to ~0 (last price > realisable). Does NOT recover acquirer upside on a merger. |
| **B. Merger-ratio remap onto the acquirer** | Map `old_isin → acquirer_isin × swap_ratio`, migrate the position into the acquirer's (already-trading) instrument. | Economically correct; captures post-merger momentum (HDFCBANK after HDFC). | **Needs an external merger-events + ratio dataset** (not in repo); acquirer may already be held (position-merge logic); larger blast radius. |
| **C. Universe exclusion near termination** | Drop a name from the eligible set N days before its known termination so it is never held into the event. | Simple; no remap. | Needs the termination calendar (partial external data); look-ahead risk; doesn't help a name already held when the event was unforeseeable. |

**Recommendation for the §6 decision:** ship **A (write-off/force-exit)** first — it is
data-free, removes 100% of the ghosts, frees the slot + capital, and unblocks the `11`
probation; record it as a *correctness* fix (not edge-tuning), pre-accepted-null on metrics.
Revisit **B** only if/when a merger-ratio data source is ingested (a separate prereg), the same
way value/quality was deferred pending a balance-sheet re-ingest.

## 6. Decision (NOT locked — owner to sign before any T07.x code)

`06` §9 was an explicit owner decision; `07` needs the same. Open question: **A vs B vs C** (§5),
the treatment of insolvency-vs-merger sub-types (§3), and whether the force-exit price is
last-trade or a haircut. **Do not write T07.x code until this is signed** (mirrors `08`'s
"DRAFTED → §12 lock" discipline).

## 7. Relationship to `06` T06.6 (the re-measure) — **NOT a blocker**

**T06.6 (re-run S3 metrics on the stitched data) is NOT blocked by these merger ghosts** and
can proceed now. Reasoning, recorded so a cold session does not stall:

- T06.6's deliverable is the **succession** re-measure: old (identity-broken) vs new (stitched)
  Calmar/Sharpe/maxDD/retention, pre-accepted-null, **no validated claim** (FINAL_OOS stays
  spent). The backtest **runs** on stitched data today (it did, in T06.5's diagnostic).
- The merger ghosts are present in **both** the old and new runs — they are *not* what `06`
  changed — so the old→new **delta** T06.6 reports still isolates the succession effect.
- The required honesty (Rule 12): T06.6 must **record that the re-measured absolute metrics
  remain merger-contaminated** (3 frozen ghosts still dampen maxDD and occupy slots), so the new
  numbers are *succession-clean, merger-dirty* — a **fully** identity-continuous measurement
  awaits `07`. T06.6 should cite this doc for that caveat.

**Where the merger ghosts ARE a hard blocker: arming the `11` forward probation.** A book that
starts with 3 (universe-wide: up to ~tens of) permanently-frozen dead positions contaminates
forward returns and misstates capital. **`07` (at least approach A) must land before the `11`
probation is armed.** This does not change `06`'s done-criteria (which `06` §15 already amended
to "zero *succession* ghosts").

## 8. Provisional task breakdown (cold-session-ready; refine after §6 is signed)

Designed like `06` §10 — each a self-contained cold session, honoring the project laws
(idempotency, checkpoint/resume, tests mock all feeds, regression-first, surgical changes).

- **T07.1 — Classify the 75 liquid terminations by sub-type.** Read-only audit. Partition the
  §3 set into {share-swap merger, cancellation, delisting/insolvency, false-positive
  data-gap}. Tighten the termination definition (the §3 cutoff caveat). Deliverable: a
  `terminations.parquet` audit (mirroring `successor_unmatched`), with a `subtype` column and
  the false-positive cluster (2026-05-18 batch) resolved. **Gate:** the 3 T06.5 ghosts classify
  as {merger, merger, cancellation}; counts reproduced ± the tightened-definition delta.
- **T07.2 — (if approach A) force-exit-at-termination in the engine.** On an instrument's last
  trade with no `instrument_id` successor and no resume within K days, liquidate to cash at the
  last price; bar re-entry. Surgical, behind a flag (default off → parity-preserving), AND-ed
  into the existing fill model. Regression: the §2 merger ghost reproduced RED (carried), GREEN
  (exited clean); no-termination parity byte-identical. **Gate:** the 3 T06.5 ghosts exit; book
  has 0 carried-unsellable holdings on re-warm-start.
- **T07.3 — (if approach B, data-gated) ingest merger events + acquirer/ratio; remap.** Blocked
  on an external merger-ratio source — a *separate* ingest prereg first. Out of scope until that
  data exists.
- **T07.4 — Extend `validate.py`** with a "no carried-unsellable holding at the store edge"
  check (read-only; fails loud if any liquid terminated leg resolves to a held-but-unpriced
  position). Re-validate.
- **T07.5 — Re-warm-start the `11` book** on the de-ghosted data; re-prove parity ≈ 0.0 and 0
  carried-unsellable holdings (the T06.5 gate, now fully clean). Worker + beat stay STOPPED.
- **T07.6 — Re-measure** (folds into / supersedes `06` T06.6's caveat): record S3 metrics on the
  now fully identity-continuous data; pre-accepted-null; no validated claim; FINAL_OOS untouched.

### Done-criteria for `07`
`07` is complete when: the §6 decision is signed; the chosen approach (A/B/C) is implemented
test-green; `validate.py` enforces no carried-unsellable holding; the `11` book re-warm-starts
with **0** carried-unsellable holdings and parity ≈ 0.0 bps; and the re-measured metrics are
recorded with the identity-continuity caveat. Only then is the `11` probation eligible to start.

---

## 9. Operational state (as of 2026-06-22)

- The `s3_probation` paper book is warm-started to 2026-06-18 on `06`-stitched data and holds
  the 3 merger/cancellation ghosts above (risk-off edge ⇒ mostly cash; see `06` §15).
- **Worker + Celery beat remain STOPPED** — the daily job will not auto-fire.
- Forward probation **NOT eligible** to start until `07` (≥ approach A) lands.
