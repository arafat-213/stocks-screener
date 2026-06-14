# Spec 01 — Data Layer (survivorship-free NSE OHLCV)

> Depends on: `00_OVERVIEW.md`. This is **build step 1** and the long pole.
> Nothing downstream is trustworthy until this passes its acceptance checks.

---

## 1. Goal

Produce a **point-in-time, survivorship-free, corporate-action-adjusted** daily OHLCV
dataset for the NSE equity universe, plus a **point-in-time universe membership** map and
a **liquidity** series, all keyed by a stable instrument identity (**ISIN**).

Source: **NSE daily Bhavcopy** (free). Live trading data (later) will come from Zerodha
Kite Connect — out of scope here, but design the adjusted-price contract so Kite data can
slot in later (see §8).

---

## 2. Why bhavcopy, and the three hazards

Bhavcopy is free and, because a delisted stock appears in the daily files until it stops
trading, the **union of all daily files = a survivorship-free universe**. But the raw data
has three hazards that, if mishandled, corrupt a momentum backtest *silently*:

1. **Unadjusted prices.** Raw traded prices. A 1:5 split looks like an −80% return to a
   momentum calc. **You must apply corporate-action adjustments yourself.** This is the
   single most important correctness task in this spec.
2. **Symbol renames.** Symbols change over time. **Join on ISIN**, not symbol. The full
   bhavcopy contains ISIN.
3. **Format change mid-2024.** NSE moved from the legacy bhavcopy to the **UDiFF** format
   (~July 2024). A 2018→present backtest spans both schemas; the loader must handle both.

**Verify at build time** (do a quick WebFetch/WebSearch first — these URLs/formats move):
- Current legacy "full bhavcopy" download URL + schema (was `sec_bhavdata_full_DDMMYYYY.csv`).
- Current UDiFF bhavcopy URL + schema and the exact cutover date.
- Corporate-actions feed URL/format (splits, bonuses, dividends).
- Index TRI history download (niftyindices.com) — needed by `03`.
- Whether to use a maintained wrapper (`jugaad-data`, `nsepython`) vs direct HTTP. NSE
  blocks naive requests; you need browser-like headers + a warmup cookie + rate limiting.

State your verified findings at the top of the implementation before writing the loader.

---

## 3. Module layout

```
backend/app/data/bhavcopy/
  __init__.py
  download.py        # fetch raw daily bhavcopy files (both formats), cache to disk
  parse.py           # parse legacy + UDiFF schemas → unified raw schema
  corporate_actions.py  # fetch + parse CA feed; build adjustment factors
  adjust.py          # apply back-adjustment to OHLCV
  universe.py        # point-in-time membership + liquidity floor
  store.py           # write/read the canonical parquet dataset
  build.py           # orchestrator: end-to-end pipeline, idempotent + resumable
  validate.py        # acceptance checks (see §7)
```

Keep this independent of the FastAPI app and the v1 engine. It is a batch pipeline.

---

## 4. Canonical dataset (the contract every downstream component reads)

Write **adjusted** daily OHLCV partitioned by symbol/ISIN to parquet. One logical table:

`prices_adjusted` — one row per (isin, date):

| column | type | notes |
|---|---|---|
| `isin` | str | **stable identity key** |
| `symbol` | str | NSE symbol *as of that date* (may change over time for same ISIN) |
| `date` | date | trading date (IST calendar), UTC-naive |
| `open`,`high`,`low`,`close` | float | **fully adjusted** for splits + bonuses (and dividend-adjusted variant, see below) |
| `close_raw` | float | unadjusted close, retained for audit/debug |
| `volume` | int | shares traded |
| `traded_value` | float | ₹ turnover for the day (from bhavcopy if present, else close_raw×volume) |
| `adv_20` | float | 20-day rolling median of `traded_value` (liquidity) |
| `series` | str | keep only `EQ` (and `BE` if you choose); drop F&O/ETF/etc. |

Two price conventions — produce **both**, store the factor so either is reconstructable:
- **Split/bonus-adjusted** (`open/high/low/close`): used for **signals/ranking** (momentum,
  EMAs). Do NOT dividend-adjust signal prices — dividends shouldn't create momentum.
- **Total-return adjusted** close (`close_tr`): split+bonus+dividend reinvested. Used only
  for **portfolio P&L / equity curve** so realized returns include dividends. Store as a
  separate column `close_tr` plus the cumulative `adj_factor` and `tr_factor`.

> Rationale: rank on price momentum (ex-dividend), but account P&L on total return. Mixing
> these is a common, subtle source of wrong backtests.

Supporting tables:

`universe_membership` — one row per (isin, date) for every date the instrument actually
traded (i.e. appeared in that day's bhavcopy with series in scope). This *is* the
point-in-time universe — downstream asks "which ISINs were tradeable on date D?".

`isin_symbol_map` — (isin, symbol, first_date, last_date) to resolve renames and for
human-readable reporting.

---

## 5. Pipeline stages (`build.py`)

Idempotent and resumable per CLAUDE.md Pipeline Laws. Checkpoint by date.

1. **Download** raw daily files for the date range → local cache (`data/raw/bhavcopy/`).
   Skip files already present. Handle both legacy and UDiFF by date. Backoff + retry on
   429/5xx. Respect a polite rate limit.
2. **Parse** each day → unified raw rows `(isin, symbol, date, o,h,l,c, volume,
   traded_value, series)`. Filter to in-scope series. Drop suspended/empty rows.
3. **Corporate actions:** fetch CA feed, parse split ratios, bonus ratios, dividend
   amounts with **ex-dates**. Build, per ISIN, a cumulative **back-adjustment factor**
   time series:
   - split/bonus factor applies multiplicatively on/after each ex-date (back-adjust
     *historical* prices so the series is continuous at "today's" share basis).
   - dividend factor for the TR series uses the standard `(1 - D/close_cum)` reinvestment.
   Prefer the **explicit CA feed** over inferring ratios from price gaps (gap inference is
   noisy and conflates moves with actions). If a CA has no clean feed entry, flag it.
4. **Adjust:** apply factors → `close`/`ohlc` (split+bonus) and `close_tr` (+dividends).
   Keep `close_raw`. Recompute `traded_value` consistency.
5. **Liquidity:** compute `adv_20` (20-day rolling **median** traded value — median, not
   mean, to resist single-day spikes).
6. **Universe membership:** emit `universe_membership` from presence in scoped daily files.
7. **Store:** write parquet partitioned for fast per-ISIN reads. Write `isin_symbol_map`.
8. **Validate:** run `validate.py` (§7). Fail the build loudly if checks fail.

---

## 6. Liquidity floor (tradeability ≠ survivorship-free)

The survivorship-free universe contains thousands of untradeable microcaps. Downstream
(`02`) selects only names passing a liquidity floor **as of the decision date** (no
lookahead): e.g. `adv_20 >= ₹X crore` on the rebalance date. Make the threshold a config
value (default to a deliberately conservative number, e.g. ₹5 crore/day, tune later).
Also expose `adv_20` so `03`'s slippage model can scale impact by position/ADV.

---

## 7. Acceptance criteria (validate.py must assert)

The build is **not done** until these pass. Fail loud, do not warn-and-continue.

1. **Known corporate actions adjust correctly.** Hard-code ~5 well-known NSE
   split/bonus events (pick liquid names with documented ratios). Assert the adjusted
   series has **no spurious >40% single-day gap** on those ex-dates, and that the ratio
   matches the documented split/bonus.
2. **Survivorship sanity.** Assert the universe contains ISINs whose `last_date` is well
   before today (i.e. delisted names are present). Count them; expect a non-trivial number
   over a multi-year window. If zero delisted names → the build is silently current-only;
   FAIL.
3. **ISIN continuity across rename.** Pick a known rename; assert one continuous ISIN
   series spans both symbols with no gap.
4. **No lookahead in liquidity/universe.** `adv_20` and membership on date D use only data
   ≤ D.
5. **TR ≥ price-adjusted over long horizons** (dividends are non-negative): assert
   `close_tr` cumulative return ≥ split/bonus-adjusted cumulative return for a sample.
6. **Coverage report:** print rows, distinct ISINs, distinct delisted ISINs, date range,
   % days with gaps, count of CA events applied vs flagged-unmatched.

---

## 8. Forward-compatibility with Kite (later, out of scope to build)

When live OHLCV switches to Kite Connect: Kite is vendor-adjusted and current-universe
only, so it does **not** replace bhavcopy for backtests. At go-live, add a parity check
that signal inputs (momentum, EMAs) computed from bhavcopy-adjusted vs Kite-adjusted data
match within tolerance on a sample of liquid names. Keep the adjusted-price contract in §4
identical so the strategy code is source-agnostic.

---

## 9. Open questions to resolve at build time

- Exact current bhavcopy + UDiFF + CA-feed endpoints and the cutover date (verify live).
- Whether to include `BE` series or `EQ` only.
- Liquidity floor numeric default (start conservative; it is tuned in `04`, not guessed).
- Storage layout that makes "all ISINs on date D" and "full history for ISIN X" both fast
  (consider a date-partitioned table for membership and an ISIN-partitioned table for
  prices, or a single parquet + duckdb).
