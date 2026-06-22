# Spec 06 — ISIN-Succession *Identity* Continuity (open data-layer gap)

> **Status: FINDING / WRITE-UP — not started.** Surfaced 2026-06-22 during the v3/11
> S3 forward-paper warm-start (`specs/v3/11_PROBATIONARY_DEPLOY_PREREG.md`). Deferred to a
> dedicated data-layer session (owner decision, 2026-06-22). **Worker + Celery beat are
> left STOPPED so the probation does not auto-start on a contaminated book.**
>
> **Relationship to `05`:** `05_DATA_ADJUSTMENT_REMEDIATION.md` already identified
> **ISIN succession** as a mechanism and fixed it at the **adjustment** layer — the
> `events_by_symbol` bridge in `adjust.py` so that a CA event filed under the *old* ISIN
> is applied to prices now trading under the *new* ISIN (the new leg is correctly
> split-adjusted; 62 bridged, 180 with no CA event in the feed). **This doc is the
> still-open *next* layer of the same root cause: identity continuity.** `05` made the
> new leg's prices *correct*; it did **not** stitch old + new into one continuous
> *instrument* for the holdings/signal layer. That gap is what `06` is about.

---

## 1. The gap in one sentence

When a company changes ISIN (typically a face-value sub-division — `INE296A01024 → INE296A01032`),
the old and new ISINs remain **two separate instruments** in `prices_adjusted`, so the
strategy (a) can **never sell** a position held under the old ISIN once it stops trading
(unsellable **ghost position**), and (b) sees the new ISIN as a **brand-new name with no
momentum history**, making it unselectable for ~the lookback window after the change.

## 2. How it surfaced (v3/11 warm-start)

Replaying frozen S3 inception→2026-06-18 as a paper book (faithful — shadow-parity
`max_dev_bps = 0.0` vs a from-scratch backtest) left the book in a **degenerate** state:
**6 holdings, ₹2.63M idle cash** instead of a 20-name momentum portfolio. Of the 6:

| Symbol | Held (dead) ISIN | Current live ISIN | Cause |
|---|---|---|---|
| BAJFINANCE | INE296A01024 | **INE296A01032** | ISIN succession (unstitched) |
| MCX | INE745G01035 | **INE745G01043** | ISIN succession (unstitched) |
| NAZARA | INE418L01021 | **INE418L01047** | ISIN succession (unstitched) |
| EASEMYTRIP | INE07O001018 | **INE07O001026** | ISIN succession (unstitched) |
| HDFC | INE001A01036 | — | legit (merged into HDFC Bank, Jul 2023) |
| TATAMTRDVR | IN9155A01020 | — | legit (DVR cancelled, 2024) |

The 4 succession names still trade today under the new ISIN; the book holds the dead leg,
can't sell it (no future prices → "fill dropped, position carried"), and MTM-freezes it.
**Parity passing means the backtest does the identical thing — this is NOT a live-shell
bug; it is in the data/identity layer and contaminates the backtest too (see §5).**

## 3. Blast radius (full universe, 2017→2026, measured 2026-06-22)

| Metric | Count |
|---|---|
| Symbols with >1 ISIN | 388 |
| Sequential ISIN-change events (old leg ends, new leg begins next day) | **406** |
| ...new leg since 2024 | 168 |
| **...old leg liquid (≥ ₹5 cr ADV) → S3-eligible, ghost risk** | **150** |
| ...liquid **and** recent (≥ 2024) | 79 |
| Total symbols | 3,389 |

Top liquid successions are exactly the names a momentum book holds: `IRCTC`, `HDFCBANK`,
`BAJAJFINSV`, `TATASTEEL`, `BAJFINANCE`, `YESBANK`, `EICHERMOT`, `KOTAKBANK`, `HAL`,
`COFORGE`, `MAZDOCK`, `CANBK`, `TATAINVEST`. Every transition is **next-day**
(`old_last` → `new_first` consecutive) and the last two ISIN digits increment
(`...A01024 → ...A01032`) — a strong, mappable signal.

## 4. Root cause & why `05`'s bridge doesn't cover it

`05` keyed its fix to **adjustment factor lookup**: find the CA event (filed under old
ISIN) and apply the multiplier to the new ISIN's prices. Correct, but the two ISINs stay
**distinct rows / distinct instruments**. The simulation/signal layer keys everything on
ISIN (`02_SIMULATION_CORE.md`), so:

- **Momentum discontinuity:** `mom_12_1` etc. on the new ISIN only see post-succession
  history → the name is invisible to selection for ~12 months after every change.
- **Ghost holdings:** a position in the old ISIN has no price after the change → the
  engine's next-open fill finds no price → sell dropped → carried forever (`engine.py`
  fill model). The §5e CA *price-rescale* in `11` does not help — that handles a moving
  adjustment anchor on a still-trading ISIN, not an ISIN that ceased to exist.

## 5. Impact on validation (research-integrity note)

Because the live warm-start is byte-identical to the backtest, **S3's reported backtest
metrics were computed on identity-broken data**: ~150 liquid names had truncated momentum
history and any held leg that succeeded became a frozen ghost. This does not by itself
invalidate the v2/v3 conclusions, but **any future "validated" claim must be re-run on
identity-continuous data.** Record alongside the `11` "exploratory" ceiling.

## 6. Recommended fix (for the dedicated session — NOT started)

1. **Build a successor map** `old_isin → new_isin` from converging signals: (a) the CA
   feed already persisted by `05` (face-value-split subjects), (b) same `symbol` with
   non-overlapping, **consecutive-day** date ranges, (c) the `INE######01NN` issuer-prefix
   match with incrementing suffix. Require ≥2 signals to assert a link; log singletons for
   manual triage (mirror `05`'s `unmatched` audit discipline).
2. **Stitch identity for the sim/signal layer** — choose one:
   - *Canonical-ID column:* add a stable `instrument_id` to `prices_adjusted` that is
     constant across a succession chain; key momentum + holdings on it instead of raw ISIN.
     (Cleanest; larger blast radius — touches `02` signal store + `backtest_v2`.)
   - *Holding remap only:* on a succession ex-date, migrate a held old-ISIN position to the
     new ISIN (rename + the `05` factor already aligns price space). Smaller change; fixes
     ghosts + keeps the book tradeable, but momentum history on the new leg stays truncated.
3. **Re-derive** `prices_adjusted`, re-run `validate.py` (extend with a succession-coverage
   check), then **re-run the `11` warm-start** and re-check shadow-parity.
4. **Re-validation caveat:** acknowledge backtest metrics must be regenerated on the
   stitched data before any "validated" verdict.

## 7. Secondary observations (lower priority, captured here)

- **0-row weekdays are mostly NSE holidays, not gaps:** `2026-03-26, 03-31, 04-03, 04-14,
  05-01, 05-28` are trading holidays — expected (the bhavcopy pipeline tolerates them).
- **Checkpoint vs store max-date mismatch:** `.build_checkpoint.json` marks `2026-06-22`
  "ok" but `prices_adjusted` max date is `2026-06-19` (today's bhavcopy not yet
  published/landed at append time). Cosmetic, but the incremental append should not mark a
  date "ok" when it produced zero stored rows — worth a guard so the checkpoint can't claim
  coverage it doesn't have.

## 8. Current operational state (as of 2026-06-22)

- `s3_probation` paper book exists but is in the **degenerate warm-start state** (6 ghost
  holdings, lpd `2026-06-18`). **Do not start the forward probation** until `06` is done;
  the book should be reset + re-warm-started on stitched data.
- **Worker + Celery beat are STOPPED** — the daily post-close job will not auto-fire.
- P11.2 code work (engine-context hoist, hydrate cash-snap, warm-start parity/alert gating,
  `adj_factor` lookup) is complete and test-green (26 `paper_v2` tests); it is sound and
  independent of this data finding — it is what made the warm-start fast enough to surface
  the issue.
