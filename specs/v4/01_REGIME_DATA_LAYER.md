# v4 / 01 — Regime Data Layer: market-internals (breadth, A/D) + India VIX ingestion

> **Status: COMPLETE — 2026-06-23 (Arafat). §9 LOCKED; Part A + Part B DONE, committed, 223 data-layer
> tests green. Full 5-factor regime inputs available (breadth/A-D + India VIX merged at 99.2%).**
> Forward = draft `00_SWING_PREREG.md` (the strategy/regime-score prereg). This was the cheap, low-risk
> **data unblock**
> that must land *before* the v4 swing strategy can be pre-registered. You cannot pre-register a
> regime score against inputs you have not confirmed are clean and point-in-time correct.
> **Owner:** Arafat. **Created:** 2026-06-23.
>
> **What this doc is NOT:** it does **not** define the regime score, the entry/exit rules, position
> sizing, or any backtest. Those are strategy decisions reserved for the forthcoming
> `00_SWING_PREREG.md` (the anti-HARKing master prereg). **This doc lands only the raw daily series**
> the score will later be *built from* — nothing that touches a return number. Keeping the data layer
> and the strategy commitment strictly separate is deliberate (v1's sin was a data-layer defect that
> silently biased every downstream number; we isolate the data layer so it can be verified on its own).

---

## 0. Context — why v4 needs this, and what tier is gated on what

v4 is a **daily, single-name swing strategy** (event-driven entry/exit), philosophically distinct from
S3 (cross-sectional monthly-rebalanced momentum, currently in `11` probation). Its regime overlay is a
**continuous score** (0–5 points) rather than S3's binary risk-on/off. The score's five candidate inputs:

| # | Condition | Raw series needed | Available today? |
|---|---|---|---|
| 1 | Nifty > 200 DMA | `^NSEI`/`^CRSLDX` daily close | ✅ in pipeline |
| 2 | 50 DMA > 200 DMA (Nifty) | same | ✅ in pipeline |
| 3 | Breadth > 60% | daily advancers / total across the universe | ❌ **derive (Part A)** |
| 4 | A/D ratio > 1 | daily advancers / decliners | ❌ **derive (Part A)** |
| 5 | India VIX < 20 | India VIX daily close | ❌ **ingest (Part B)** |

**Pre-registered tiering (locked with Arafat 2026-06-23):** the swing strategy ships a **3-factor regime
score (conditions 1–3) buildable today**, and the **full 5-factor score (adds 4–5) is gated on Part A +
Part B landing.** A VIX or A/D data hiccup must never block the whole v4 research arc — the 3-factor
score is the floor, the 5-factor is the upgrade. The score *definition* (point weights, bucket cuts,
sizing map) is locked in `00_SWING_PREREG.md`, not here.

> **Plain-language note (Rule 13):** "market breadth" = *how broad* a rally is — the % of stocks going
> up on a given day, not just the index. A rising index with collapsing breadth (a few megacaps
> dragging it up) is a weak, narrow market. "A/D ratio" = advancers ÷ decliners — same idea as a ratio.
> "India VIX" = the market's expected near-term volatility (a fear gauge) — high VIX = stressed market.
> These are *market-state* inputs; the score uses them to scale how aggressively v4 deploys capital.

---

## 1. What we have / what is missing (verified 2026-06-23)

- **Nifty index series (conditions 1–2):** present — `^NSEI`/`^BSESN`/`^CRSLDX` flow through the v1
  pipeline (`pipeline/fetcher.py`, `signal_digest.py`, `rs_ranks.py`). *(Caveat: that path is v1
  yfinance. For v4 we standardize on the v2 bhavcopy-derived series — see §2 open decision 1.)*
- **`MarketBreadth` DB table (`db/models.py:657`):** a **schema-only orphan** — defined but **nothing in
  the codebase populates it** (verified: no writer in `app/` or `scripts/`). It was hand-populated once
  by an old script on **v1 yfinance data**, which we do **not** reuse. Treat as absent.
- **A/D ratio:** does not exist anywhere. Derivable (Part A).
- **India VIX:** **no ingestion anywhere** in the repo. Must be sourced (Part B).
- **The clean foundation:** the v2 **bhavcopy data layer** (`backend/app/data/bhavcopy/`) holds
  **point-in-time, survivorship-free, split/bonus-adjusted** daily OHLCV per ISIN
  (`store.read_prices_adjusted`), with the corporate-action correctness fixed in `v2/05` and the
  ISIN-identity stitching in `v2/06`+`07`. **This is what we build breadth/AD from** — its PIT-cleanliness
  is the property that protects us from v1's sin.

---

## 2. The plan

### Part A — Self-compute breadth + A/D from bhavcopy (free, PIT-clean)

Breadth and A/D are the **same calculation** off data already in hand. For each trading day `D`, over
the set of ISINs **present in the adjusted store on both `D` and the prior trading day**:

```
advancers  = count(adj_close[D] > adj_close[D-1])
decliners  = count(adj_close[D] < adj_close[D-1])
unchanged  = count(adj_close[D] == adj_close[D-1])
total      = advancers + decliners + unchanged
breadth_pct = 100 * advancers / (advancers + decliners)      # % of directional names that are up
ad_ratio    = advancers / decliners                          # NaN-guard: decliners == 0 -> capped sentinel
```

- **Use the split/bonus-ADJUSTED close** (`close`, not `close_raw`) for the up/down test, so a corporate
  action never manufactures a phantom decliner. This depends on the `v2/05` adjustment fix being in
  place (it is). *(This is the exact lookahead/data-integrity trap from v1 — we use the corrected series.)*
- **Universe each day = whatever traded that day** in `prices_adjusted` (naturally survivorship-free and
  point-in-time — no use of today's membership for a past day). Apply the **same ₹-liquidity context as
  v2** only if `00_SWING_PREREG.md` later asks for a liquid-universe breadth; the default Part-A series
  is **all-EQ breadth** (broadest, most standard). Both can be stored; the prereg picks which it consumes.
- **Storage:** new parquet artifact `market_internals/` in the bhavcopy store, mirroring the existing
  `write_corporate_actions`/`write_terminations` pattern (`store.py`). Schema:

  | column | type | note |
  |---|---|---|
  | `date` | date | primary key |
  | `advancers` / `decliners` / `unchanged` | int | counts |
  | `total` | int | universe size that day |
  | `breadth_pct` | float | 100·adv/(adv+dec) |
  | `ad_ratio` | float | adv/dec (decliners==0 → sentinel) |

- **Computed inside the build pipeline** (a new derivation step after `prices_adjusted` is written), so
  it is **regenerated PIT-correctly on every rebuild** — never a one-off hand-populated table (the
  orphan `MarketBreadth`'s failure mode). Backfill = run the existing build over the full range.
- **No DB / no Alembic** — parquet keeps it consistent with the rest of the data layer (per `v2/05` §9's
  resolved recommendation). The orphan `MarketBreadth` DB table is left untouched (flagged for later
  cleanup, §8 open decision 2 — not in scope here).

### Part B — Ingest India VIX (the one genuine external fetch)

India VIX is an NSE-published index level (launched 2008; history to ~2008–2009). Two paths:

1. **Robust / PIT-clean (recommended):** NSE **index bhavcopy** (`ind_close_all_<DDMMYYYY>.csv`) includes
   India VIX alongside index closes. Extend the existing `download.py`/`parse.py` to also pull the
   index-close file per day → store India VIX as a daily series. Official number, fed through
   infrastructure we already trust, and clean (an index level is never restated).
2. **Quick fallback:** yfinance ticker `^INDIAVIX` through the existing fetcher (one-line universe add).
   **Caveat: verify history depth back to the backtest start and check for gaps** before trusting it —
   yfinance India VIX coverage is known to be patchy.

- **Storage:** add `india_vix` as a column to the `market_internals` parquet (single date-keyed series).
- **Timing/lookahead discipline:** the score acts on **prior-completed-day VIX** (a signal computed
  post-close on day `D` uses VIX[`D`], and trades day `D+1` open) — never an in-progress intraday value.
- **One-off live fetch is allowed** for the historical backfill (same exemption `v2/05` Phase 0 used for
  the CA fetch); **no live API call may enter any `pytest`** (CLAUDE.md §5 — mock the fetch in tests).

---

## 3. Point-in-time / lookahead discipline (the v1-sin guardrail — non-negotiable)

v1's actual sin was a **data-layer lookahead bias discovered late**. Every item below is a check, not a
nicety:

- **Adjusted, not raw, close** for breadth/AD (corporate actions must not create phantom decliners).
- **Daily universe = names that traded that day** — never reindex a past day against today's membership.
- **Causal rolling only** — any DMA/smoothing computed from these series (in the strategy layer) uses
  `min_periods` = window and trailing windows; this doc emits only same-day point values, no forward fill
  across gaps.
- **VIX acts on the completed prior day**, never an intraday/in-progress value.
- **Regeneration, not hand-population** — the series live in the build pipeline so a rebuild reproduces
  them deterministically; an orphan hand-filled table is forbidden (it is exactly what we are replacing).

---

## 4. Testing (CLAUDE.md §5, Rule 9 — encode WHY)

- **Breadth/AD unit tests (synthetic, no live API):** a hand-built 3-day, 5-ISIN adjusted-price frame
  with known up/down counts → assert exact `advancers`/`decliners`/`breadth_pct`/`ad_ratio`.
- **Split-day regression (the WHY test):** an ISIN with a split-adjusted step on day `D` must **not** be
  counted as a decliner — assert the adjusted-close path produces the correct sign where the raw-close
  path would have produced a false decline. This test fails if anyone reverts to `close_raw`.
- **Survivorship test:** a name absent on `D-1` but present on `D` (new listing / late-entering ISIN) is
  **excluded** from that day's directional count (no phantom advancer/decliner from a missing prior).
- **VIX ingestion:** mock the fetch; assert parse → date-keyed series; assert a gap day is surfaced
  (fail-loud / logged), not silently forward-filled.
- **Build-integration:** the `market_internals` derivation runs as part of the build over a tiny fixture
  range and round-trips through `write_/read_market_internals`.

---

## 5. Definition of done
- [x] **Part A** `store.write_market_internals` / `read_market_internals` + `MARKET_INTERNALS_SCHEMA` added
      (mirrors the CA-artifact pattern). *(2026-06-23)*
- [x] **Part A** breadth/AD derivation (`market_internals.compute_market_internals`) wired into the build as
      Stage 7b; **regenerates on every rebuild** from the in-memory adjusted panel (not hand-run).
- [x] **Part A** full-range backfill executed (non-destructive, from the existing store):
      **2336 trading days, 2017-01-02 → 2026-06-19, 0 gaps** (1 NaN = day-1 warmup, by design). Spot-checks
      pass: COVID low 2020-03-23 breadth **3.9%** / AD 0.04; election crash 2024-06-04 **4.9%** / 0.05;
      COVID bounce 2020-04-07 **86.1%** / 6.18; exit-poll rally 2024-06-03 **68.9%**.
- [x] **Part B** India VIX ingested — **yfinance `^INDIAVIX`** (§8.4 deviation, 2026-06-23) cached to
      `india_vix.parquet` + folded into `market_internals.india_vix`. Depth **verified 2008-03-03 → 2026-06-23
      (4483 days)**; merged coverage **2318/2336 = 99.2%**, 18 NaN trading days (Jan-1 sessions + a 2021
      yfinance gap cluster) **surfaced loudly, not filled**. Cross-check **PASS**: max VIX **83.61 on
      2020-03-24** == India VIX's COVID record close (matches NSE-published); range 9.15–83.61.
- [x] Tests green: synthetic breadth/AD, the **split-day WHY test** (fails if anyone reverts to `close_raw`),
      survivorship test, VIX left-join/None tests, store round-trips, **Part B VIX parse/dedupe/NaN-drop/
      fail-loud + end-to-end merge-with-gap** — **15 new + 223 data-layer all green**, no live-API in `pytest`.
- [x] **3-factor inputs (conditions 1–3) buildable** (breadth/AD + Nifty DMA) **AND 5-factor (4–5) landed**
      (India VIX merged at 99.2%) — the tier gate (§0) resolves to **full 5-factor available**; degrade-to-3
      remains the documented fallback for the 18 NaN days / any future VIX hiccup.
- [x] CI green — full data-layer suite **223 passed**; Part A + Part B both committed.

> **Execution log (2026-06-23) — Part A DONE:** new `app/data/bhavcopy/market_internals.py` (pure,
> vectorized `(date×isin)` pivot/diff on the **split-adjusted** close; survivorship-free via NaN-on-either-
> side exclusion; liquid subset gates `adv_20 >= 5e7` matching `signals_v3.py`). Store I/O + Stage-7b build
> wiring + `backfill_from_store()` (`python -m app.data.bhavcopy.market_internals`). **Additive only** —
> reads `prices_adjusted`, writes one new parquet; `prices_adjusted`/membership/engine untouched ⇒ S3 `11`
> probation and `FINAL_OOS` unaffected (§7 confirmed: 216/216 data-layer tests unchanged). (Committed
> `05ca9aab`.)
>
> **Execution log (2026-06-23) — Part B DONE:** §8.4 source switched to yfinance `^INDIAVIX` (deviation
> above). New `app/data/bhavcopy/india_vix.py` (`fetch_india_vix` with a `_history` injection point so no
> test touches the network → tz-strip, drop source NaNs, dedupe, fail-loud-on-empty; `backfill_india_vix`
> writes the `india_vix.parquet` source cache). Store gained `INDIA_VIX_SCHEMA` + write/read. Both
> `market_internals.backfill_from_store` and build Stage-7b read the VIX cache and merge it (the build stays
> network-free for VIX — refresh is `india_vix`'s own job). Live one-off backfill: 4483 VIX days 2008→2026,
> merged at 99.2% (18 NaN surfaced). Cross-check PASS (COVID max 83.61 == NSE record). 7 new tests; 223
> data-layer green. **`01` COMPLETE → next is `00_SWING_PREREG.md`.**

## 6. File map
| Concern | File |
|---|---|
| Parquet store + new `market_internals` schema/read/write | `backend/app/data/bhavcopy/store.py` |
| Build orchestrator (add breadth/AD derivation step) | `backend/app/data/bhavcopy/build.py` |
| Adjusted prices source for the up/down test | `backend/app/data/bhavcopy/adjust.py` / `store.read_prices_adjusted` |
| Breadth/AD derivation (Part A) | `backend/app/data/bhavcopy/market_internals.py` (new) |
| India VIX ingestion (Part B) | `backend/app/data/bhavcopy/india_vix.py` (new — yfinance `^INDIAVIX`, §8.4 deviation) |
| Store schemas + I/O | `backend/app/data/bhavcopy/store.py` (`MARKET_INTERNALS_SCHEMA`, `INDIA_VIX_SCHEMA`) |
| Tests | `backend/tests/data/test_bhavcopy_market_internals.py` + `test_bhavcopy_india_vix.py` (new) |
| Downstream consumer (later) | `00_SWING_PREREG.md` (regime score — not this doc) |

## 7. Blast radius (stated up front)
- **Additive only.** A new parquet artifact + one build step. **No change** to `prices_adjusted`,
  `universe_membership`, the engine, or any existing backtest → S3/`11` probation is **untouched** and
  byte-identical. Nothing here can move a v2/v3 number or the pristine `FINAL_OOS`.
- The orphan `MarketBreadth` DB table remains; this doc does not read or write it.

## 8. Open decisions (resolve with Arafat before/early)
1. **Nifty series for conditions 1–2** — standardize on the **v2 bhavcopy/cached index series**
   (recommended, same PIT pipeline) vs. the v1 yfinance pipeline series. (Consistency argues bhavcopy.)
2. **Orphan `MarketBreadth` table** — leave as-is (recommended; out of scope) vs. drop via a cleanup
   migration (migrations are holy — would need Alembic). Not required for v4.
3. **Breadth universe** — all-EQ breadth (recommended default, most standard) vs. liquid-subset breadth;
   store **both** so `00_SWING_PREREG.md` picks — low cost, avoids a future re-backfill.
4. **VIX source** — NSE index-bhavcopy (recommended, PIT-clean) vs. yfinance `^INDIAVIX` (faster, verify gaps).

---

## 9. Locked commitments (Arafat — sign to flip DRAFT → LOCKED)

Confirm or redline each before any code:

1. Data layer emits **raw inputs only** (breadth %, A/D ratio, India VIX); the regime *score* is defined
   in `00_SWING_PREREG.md`, not here (§0).
2. Breadth/AD **self-computed from split-adjusted bhavcopy close**, daily survivorship-free universe,
   stored as a **parquet `market_internals` artifact regenerated in the build** (§2A, §3) — no DB/Alembic,
   orphan `MarketBreadth` untouched.
3. India VIX ingested via the §8-decision-4 path, acting on the **completed prior day**; one-off live
   backfill allowed, **no live API in tests** (§2B, §4).
4. **Tier gate:** 3-factor (1–3) is the floor and buildable now; 5-factor (4–5) gated on this doc landing;
   a VIX/AD slip degrades to 3-factor rather than blocking v4 (§0).
5. Open decisions §8 (1–4) resolved as recommended unless redlined.

> **Signed:** Arafat — 2026-06-23 (all 5 commitments approved as drafted; DRAFT → LOCKED; Part A/B authorized).
>
> **§8 resolutions (as recommended):** (1) Nifty conditions 1–2 use the **v2 bhavcopy/cached index series**
> (same PIT pipeline). (2) Orphan `MarketBreadth` DB table **left as-is** (out of scope). (3) Breadth stored
> for **both** all-EQ and liquid-subset universes (cheap; `00_SWING_PREREG.md` picks its consumer). (4) India
> VIX sourced from **NSE index-bhavcopy** (`ind_close_all`, PIT-clean); yfinance `^INDIAVIX` is the documented
> fallback if the index-bhavcopy path proves unavailable for the full range.
>
> **§13-style DEVIATION — §8.4 source REVISED to yfinance `^INDIAVIX` (Arafat, 2026-06-23).** The pre-build
> depth probe showed `^INDIAVIX` covers **2008-03-03 → present, 99.3% of the 2336 bhavcopy trading days,
> 0 NaN, max gaps 4–5 days** (holiday clusters). India VIX is an index *level* — never restated, not
> adjustment- or survivorship-sensitive — so the PIT-cleanliness argument that justified the NSE-bhavcopy
> path does **not** apply here (v1's sin was an *adjustment* bug, inapplicable to an unadjusted level). The
> one-line yfinance fetch therefore carries no integrity penalty over a per-day `ind_close_all` parser.
> Guardrail retained: a one-time cross-check vs a few NSE-published closes (the COVID-2020 spike) is part of
> the Part-B done-criterion; the live fetch is a one-off (no live API in `pytest`).
