# Spec 07 — Merger / Cancellation *Identity* Continuity (open data-layer gap)

> **Status: §6 LOCKED 2026-06-22 — Approach A (write-off / force-exit at termination)
> signed by owner (Arafat). T07.1 + T07.2 DONE 2026-06-22 (engine force-exit landed,
> test-green; see §10 + §11). T07.4 DONE 2026-06-23 (validate.py Check 9 enforces "no
> carried-unsellable holding at the store edge"; see §12). Next = T07.5 (re-warm-start
> the `11` book on de-ghosted data); T07.3 (merger-ratio remap) stays
> data-gated / out-of-scope.** Surfaced
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

## 6. Decision — **LOCKED 2026-06-22 (Approach A), signed by owner (Arafat)**

`06` §9 was an explicit owner decision; `07` got the same. After reviewing the A/B/C trade-offs
(§5) against the T07.1 audit (§10), the owner **locks Approach A — write-off / force-exit at
termination.** The three sub-questions of §5 are resolved as follows:

1. **Strategy = A (write-off / force-exit).** On an instrument's last trade with no
   `instrument_id` successor and no resume within K days, liquidate the held position to cash at
   the **last price** and bar re-entry. **Rationale:** A is the only approach that is *not*
   data-blocked — B (merger-ratio remap) needs an external swap-ratio dataset that demonstrably
   does not exist in the repo (§5, confirmed by T07.1: even the free-text "Scheme of Arrangement"
   rows don't cover the actual names), and C (universe exclusion) *also* needs a termination
   calendar **and** introduces look-ahead bias — unacceptable for a forward paper-trade. A removes
   100% of the ghosts, frees the slot + capital, and is the only thing that unblocks the `11`
   probation. This is a **correctness** fix, pre-accepted-null on metrics.

2. **Exit price = flat last-traded price for ALL sub-types in v1 (no haircut).** Although §10's
   audit shows insolvencies (e.g. JETAIRWAYS, JPASSOCIAT) gapped toward zero — so last-price is
   *optimistic* for that sub-type — the sub-type label is `heuristic` for most names and known to
   misclassify (VIJAYABANK→insolvency, ETF units→merger). Building a per-sub-type haircut on top of
   a label we don't fully trust would add more error than it removes. **Decision: flat last-price
   for v1; record the insolvency-optimism as a known, pre-accepted bias in the T07.6 re-measure
   (Rule 12).** A haircut is revisited only if/when a §5-B ground-truth merger/insolvency dataset
   is ingested (separate prereg).

3. **Re-entry bar is scoped to the terminated ISIN only, NOT the broader `instrument_id` chain.**
   The dead ISIN stops trading so its bar is trivially true; a *different* still-trading
   instrument (e.g. a merger acquirer) remains independently eligible on its own momentum. The bar
   does not propagate up the identity chain.

**B is deferred** to a future merger-ratio ingest prereg (the way value/quality was deferred
pending a balance-sheet re-ingest). **C is rejected** (data-blocked *and* look-ahead-dirty).

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

- **T07.1 — Classify the 75 liquid terminations by sub-type.** ✅ **DONE 2026-06-22** (see §10).
  Read-only audit. Partition the §3 set into {share-swap merger, cancellation,
  delisting/insolvency, false-positive data-gap}. Tighten the termination definition (the §3
  cutoff caveat). Deliverable: a `terminations.parquet` audit (mirroring `successor_unmatched`),
  with a `subtype` column and the false-positive cluster (2026-05-18 batch) resolved. **Gate:**
  the 3 T06.5 ghosts classify as {merger, merger, cancellation}; counts reproduced ± the
  tightened-definition delta. **Gate PASSED.**
- **T07.2 — force-exit-at-termination in the engine.** ✅ **DONE 2026-06-22** (see §11). On an
  instrument's last trade with no `instrument_id` successor and no resume within K trading days,
  liquidate to cash at the last price; re-entry is barred structurally. Behind a flag
  (`terminate_after_silent_days`, default 0 → OFF → `engine.run` byte-for-byte unchanged).
  Regression: the §1 ghost reproduced RED (carried) + GREEN (exited clean), boundary-at-K,
  succession-immune, no-termination parity byte-identical. **Gate:** the engine-level RED/GREEN
  passes; the full re-warm-start (book has 0 carried-unsellable holdings) is verified in T07.5.
  **Gate PASSED at the engine level.**
- **T07.3 — (if approach B, data-gated) ingest merger events + acquirer/ratio; remap.** Blocked
  on an external merger-ratio source — a *separate* ingest prereg first. Out of scope until that
  data exists.
- **T07.4 — Extend `validate.py`** with a "no carried-unsellable holding at the store edge"
  check. ✅ **DONE 2026-06-23** (see §12). Read-only Check 9: re-derives the liquid
  terminated-no-successor set and asserts every genuine termination is price-silent ≥ K
  trading days at the store edge (so the §6/§11 engine force-exit has fired by the edge);
  fails loud on any leg still carried-unsellable. Skips `data_gap_suspect`. **Gate:** RED
  (a terminated leg silent < K fails) + GREEN (≥ K passes) + the 3 T06.5 ghosts
  force-exit-safe; full data-layer suite green (208). **Gate PASSED.**
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

## 9. Operational state (as of 2026-06-23)

- The `s3_probation` paper book is warm-started to 2026-06-18 on `06`-stitched data and holds
  the 3 merger/cancellation ghosts above (risk-off edge ⇒ mostly cash; see `06` §15).
- **Worker + Celery beat remain STOPPED** — the daily job will not auto-fire.
- Forward probation **NOT eligible** to start until `07` (≥ approach A) lands.
- T07.1 audit landed (read-only): `terminations.parquet` written; the 3 ghosts classified
  {merger, merger, cancellation}. No engine/book state changed.
- **§6 decision LOCKED 2026-06-22 (Approach A, flat last-price, ISIN-scoped re-entry bar).**
- **T07.2 force-exit landed 2026-06-22 (engine code + tests; see §11).** The capability is ON
  for the live S3 book (`build_live_context`, K=15 trading days) and OFF by default everywhere
  else (parity-preserving). **No book state re-warm-started yet** — that is T07.5.
- **T07.4 validator landed 2026-06-23 (validate.py Check 9 + tests; see §12).** Read-only;
  no engine/book state changed. T07.5's re-warm-start is now UNBLOCKED. Worker + beat remain
  STOPPED.

---

## 10. T07.1 — classification audit (DONE 2026-06-22)

**Artifacts.** `backend/app/data/bhavcopy/terminations.py` (pure classifier
`classify_terminations`), `backend/scripts/t07_1_classify_terminations.py` (runner →
writes `terminations.parquet`), `store.TERMINATIONS_SCHEMA` + `write/read_terminations`,
`tests/data/test_bhavcopy_terminations.py` (6 tests green; full data-layer suite 74 green).

**§3 counts reproduced exactly** (store edge 2026-06-19, 15-day cutoff): 3,472 distinct ISINs →
672 terminated-no-successor → **75 liquid-at-death** (≥₹5cr ADV) → 53 also recent (≥2023).

### Sub-type breakdown of the 75 (the deliverable)

| subtype | curated | heuristic | total |
|---|---:|---:|---:|
| **merger** (share-swap / acquisition) | 11 | 34 | **45** |
| **data_gap_suspect** (false-positive) | 0 | 17 | **17** |
| **delisting_insolvency** | 2 | 10 | **12** |
| **cancellation** (DVR scrap) | 1 | 0 | **1** |

**Gate PASS** — the 3 T06.5 ghosts classify as expected: HDFC → merger, INOXLEISUR → merger,
TATAMTRDVR → cancellation.

### Tightened-definition delta (the §3 cutoff caveat, resolved)

The 15-day cutoff caught **17 false-positives** — names whose last trade sits near the edge yet
the market kept trading daily afterward. These are an **ingest-gap signature**, not real
delistings: 12 of them share the single date **2026-05-18** (the exact §3 cluster — IDEAFORGE,
QPOWER, KRN, INDOTECH, STYLEBAAZA, DEEDEV…), and the rest cluster on 2026-05-11/12/13/14. Real
delistings do not co-occur on one calendar day for dozens of liquid names. **Tightened true count:
75 → 58** genuine liquid terminations (45 merger + 12 insolvency + 1 cancellation). The 17
`data_gap_suspect` rows are retained in the parquet (flagged, not dropped) so T07.4's validator
and any re-ingest can re-confirm them rather than silently trust the cutoff.

### How classification works (and its honest limits — Rule 12)

§5's data constraint proved **stronger** than drafted: not only is there no structured merger
event, the free-text `ca_unmatched` "Scheme of Arrangement" rows do **not** cover the actual
merged names (HDFC/INOXLEISUR/TATAMTRDVR have *no* merger CA text). So sub-type is **not**
authoritatively derivable from on-disk data. Every row therefore carries a `confidence` flag:

- **`curated`** — a 14-name seed of fates already documented in §3 (in-repo knowledge / public
  record), carrying the acquirer where known (HDFC→HDFCBANK, IDFC→IDFCFIRSTB, CAIRN→VEDL…).
  Authoritative.
- **`heuristic`** — data-derived inference from the two clean axes the data *does* give:
  (1) **`last_peak_ratio`** = last close ÷ all-time-peak close — value **destroyed** (<0.5) ⇒
  delisting/insolvency (JETAIRWAYS 0.08, GENSOL 0.10, DHANI 0.10); value **preserved** ⇒
  merger/acquisition; (2) a **shared near-edge `last_date` cluster** ⇒ data-gap; (3) a **`DVR`**
  symbol suffix ⇒ cancellation. Inferred, not confirmed.

**Known heuristic imperfections** (acceptable for an audit; all `confidence=heuristic` and the
`last_peak_ratio`/`evidence` columns let a consumer judge): a handful of ETF unit migrations
(GROWWSLVR/SILVER1/GROWWGOLD) land in `merger` by value-preservation; VIJAYABANK (a real merger
into Bank of Baroda) trips the <0.5 insolvency ratio; a few `data_gap_suspect` names with low
ratios (IBULLSLTD 0.04) may be genuine collapses coinciding with the gap date. None affect the
gate or the 3 ghosts; a §5-B merger-ratio ingest (separate prereg) would replace the heuristic
tier with ground truth.

**Scope honoured:** read-only — no engine state, prices, or holdings mutated; FINAL_OOS
untouched. This audit only *labels* the population; the force-exit fix is T07.2 (gated on the §6
owner decision, still unsigned).

---

## 11. T07.2 — force-exit at termination (DONE 2026-06-22)

**Artifacts.**
- `backend/app/backtest_v2/engine.py` — the flag `EngineContext.terminate_after_silent_days`
  (plumbed through `build_context`/`run`, **default 0 = OFF**), the precomputed lookups
  (`cal_ord`, `inst_trade_ords`, built only when the flag > 0), the pure helper
  `_silent_trading_days`, and the `step_day` step **5.ii-b** (`_force_exit_terminated`).
- `backend/app/paper_v2/s3_config.py` — `S3_TERMINATE_AFTER_SILENT_DAYS = 15`.
- `backend/app/paper_v2/live_engine.py` — `build_live_context` turns the feature ON for the
  live S3 book (the value is now a parameter, default = the S3 constant, so a caller can
  isolate a different layer with `0`).
- `backend/tests/backtest_v2/test_v3t07_2_force_exit.py` — 6 new tests (all green).
- `backend/tests/paper_v2/test_v3t06_5_warmstart_succession.py` — the `06` RED test now passes
  `terminate_after_silent_days=0` to isolate the `06` ghost (see "Interaction with `06`").

**How termination is detected (live-safe, stateless).** After `collapse_to_instrument_id`
(`06` T06.3) a *real* succession keeps printing under the same `instrument_id`, so a held
instrument with **no successor** is exactly one that goes **price-silent**. So §6 point 1's
two conditions ("no `instrument_id` successor" **and** "no resume within K days") collapse to a
single observable: **K trading days of silence.** `_silent_trading_days` computes
`day_ord − ordinal(most-recent print ≤ day)` from the full-calendar ordinals precomputed in
`build_context`. It only ever reads the *absence* of prints up to `day` — no future knowledge —
so the backtest and the live shell (both stepping the **same** `ctx`) declare termination on the
identical day. This is why no per-position counter or new persisted state was needed (the live
`LoopState` / `paper_v2` schema are untouched — no migration).

**The exit (Approach A, §6.2/§6.3).** In `step_day`, right after MTM (so `last_price` is the
carried last-traded close_tr) and **before** the stop/rebalance steps (so no doomed sell is
queued for the dead name), every held position silent ≥ K is liquidated via the normal
`apply_fills` path: a `sell` Fill at the **flat last price** (no haircut). Reusing `apply_fills`
means the exit is recorded in `fills_log`, removes the position, and pays the standard statutory
cost (zero ADV ⇒ base-slippage floor only, no divide-by-zero). **Re-entry needs no explicit
bar:** a dead ISIN never prints again, so it can never re-enter `universe_today` — §6.3's
"trivially true" bar is enforced structurally by the data.

**Parity (the flag is genuinely off by default).** `engine.run`'s new parameter defaults to 0,
the lookups are skipped, and `step_day`'s 5.ii-b is guarded — so every pre-`07` backtest path is
byte-for-byte unchanged. Proven by `test_no_termination_parity_off_vs_on` (a continuous panel
runs identically at K=0 vs K=15) and by the unchanged full suite (**backtest_v2 + paper_v2 all
green**; the only break — the `06` RED test — was the expected interaction below, now resolved).

**Tests (Rule 9 — they encode WHY).** RED: a terminated holding stays held forever with the
feature OFF (the §1 ghost). GREEN: with K=15 it is sold once, at its flat last price, freeing the
slot + capital. Boundary: the exit fires on the **K-th** silent day, not the (K−1)-th. Helper:
`_silent_trading_days` counts true trading-day silence (0 while trading, None when unknown). And
the succession-immunity test: a stitched chain (`instrument_id` keeps printing) has silence 0 and
is **never** force-exited — proving the "no successor" gate is what separates a termination from a
`06` re-issue.

**Interaction with `06` (surfaced + resolved).** Turning the feature ON in `build_live_context`
made the `06` T06.5 **RED** test fail: that test deliberately replays the *raw-isin* (pre-`06`)
store where the old leg goes silent at the split — which `07` now (correctly) force-exits, masking
the `06` ghost the test isolates. `07`'s net catching the same leg is **correct production
behaviour** (it is a separate identity layer), so the fix is not to weaken `07` but to run that
one `06` regression with `terminate_after_silent_days=0`. In production both layers are on: `06`
stitches real successions (never silent → never force-exited) and `07` catches true terminations.

**Honest notes (Rule 12).**
- **K = 15 trading days is a chosen default, not pinned in §6.** ≈3 weeks tolerates a transient
  data/holiday gap while clearing a true termination well before it freezes capital. The
  `data_gap_suspect` cluster (§10) is the population this K is meant to *not* prematurely exit;
  a genuine >15-day data gap that later resumes would be force-exited (and, being silent, also
  invisible to re-entry until it prints again) — an accepted edge of the silence rule.
- **The exit pays standard statutory cost** (consistent with every other sell); §6.2's "no
  haircut" governs the *price* (flat last-traded), not the fee. The insolvency-optimism bias
  (last price > realisable for names that gapped toward zero) is carried per §6.2 and will be
  re-stated in the T07.6 re-measure.
- **No book/metrics state changed by T07.2** — it is engine capability + tests only. The
  re-warm-start that proves "0 carried-unsellable holdings on the live book" is **T07.5**
  (blocked on T07.4's validator). FINAL_OOS untouched.

---

## 12. T07.4 — validator: no carried-unsellable holding at the store edge (DONE 2026-06-23)

**Artifacts.**
- `backend/app/data/bhavcopy/validate.py` — `_check_9_termination_force_exit`, wired into
  `run_validation` after Check 8 (new keyword `terminate_after_silent_days`, default 15 via the
  module constant `_FORCE_EXIT_SILENT_DAYS`); four new `ValidationReport` fields
  (`terminations_liquid`, `terminations_force_exit_safe`, `terminations_data_gap_suspect`,
  `terminations_carried_at_edge`) + a coverage-report line; module docstring Check 9 entry.
- `backend/app/data/bhavcopy/terminations.py` — one-line **latent-bug fix**:
  `classify_terminations` crashed (`ValueError: Columns must be same length as key`) when the
  liquid set is empty — `apply(result_type="expand")` on an empty frame yields no columns. Check 9
  is the first caller to feed it a *clean* store (zero liquid terminations is the common case), so
  the empty path is now handled explicitly. No behaviour change for the non-empty path.
- `backend/tests/data/test_bhavcopy_validate.py` — `TestCheck9TerminationForceExit` (6 unit tests)
  + `TestRunValidationCheck9Integration` (2 end-to-end). Full data-layer suite **208 green**.

**What Check 9 enforces (and why this is the right data-layer invariant — Rule 13).** A held
position becomes a frozen ghost (§1) exactly when its instrument terminates and the engine never
force-exits it. The engine's Approach-A fix (`engine._force_exit_terminated`, §11) liquidates any
holding **price-silent ≥ K trading days**. So the *data-layer* guarantee that "the warm-start (T07.5)
will inherit zero ghosts" is: **every genuine liquid terminated-no-successor leg is silent ≥ K trading
days at the store edge** — i.e. the silence force-exit has already fired by the edge. Check 9
re-derives that population (via `terminations.classify_terminations`, so it self-validates against a
stale store rather than trusting `terminations.parquet`) and fails loud on any leg silent < K.

**Silence is counted exactly as the engine counts it** (`engine._silent_trading_days`):
`edge_ord − (last-print ordinal of the leg's instrument_id)` over the *full* price calendar. The
validator and the engine therefore declare the identical silence on the identical day — the check
is a faithful data-layer mirror of the runtime force-exit, not an independent re-implementation.

**`data_gap_suspect` is excluded from the assertion** (§10): a shared near-edge `last_date` is an
ingest-gap fingerprint, not a real delisting, so those names are expected to resume printing and a
forced exit on them would be a false positive. They are *counted* in the report (so a re-ingest can
re-confirm them), never asserted on.

**Tests (Rule 9 — they encode WHY).** GREEN: two genuine terminations both silent ≥ K →
force-exit-safe, no raise. RED: a leg silent < K (terminated by the classifier's calendar cutoff but
not yet past the K *trading-day* force-exit threshold — the realistic 16–21-calendar-day window) is
still carried → fails loud. The 3 real T06.5 ghosts (HDFC/INOXLEISUR/TATAMTRDVR), terminated long
before the edge, classify force-exit-safe (the production case). `data_gap_suspect` cluster silent
< K does **not** trip the check. Graceful skips on empty / pre-T07.1 (missing-column) stores.

**Honest notes (Rule 12).**
- **Check 9 proves a *data-layer precondition*, not the live book itself.** It guarantees the
  silence force-exit *will* fire by the edge for the whole liquid population; the actual "0 carried
  holdings on the warm-started S3 book, parity ≈ 0.0 bps" proof is still **T07.5**. The two are
  complementary: Check 9 is the universe-wide gate, T07.5 is the single-book confirmation.
- **The K trading-day vs calendar-day boundary is real and intentional.** A leg terminated just past
  the classifier's 15-*calendar*-day cutoff but short of K=15 *trading* days (~16–21 calendar days
  silent) is genuinely carried at the edge — Check 9 fails loud on it rather than hiding it. On the
  real store every genuine liquid termination is far older than this window, so the check is expected
  to pass; the boundary exists to catch a *future* very-recent termination before a warm-start.
- **Read-only — no prices, holdings, engine, or FINAL_OOS state mutated.** The validator only labels
  and asserts. FINAL_OOS untouched.
