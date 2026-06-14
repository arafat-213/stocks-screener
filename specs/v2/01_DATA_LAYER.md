# Spec 01 — Data Layer (survivorship-free NSE OHLCV)

> Depends on: `00_OVERVIEW.md`. This is **build step 1** and the long pole.
> Nothing downstream is trustworthy until this passes its acceptance checks.

---

## Verified findings (T0 research spike — 2026-06-14)

> Resolves the "verify live" items in §2 and §9. Findings confirmed via web research,
> not a cookie-warmed live pull (NSE blocks naive requests — see wrapper note). Where a
> verbatim live row could not be fetched without a warmup cookie, the schema is confirmed
> from multiple independent sources and the verbatim row is flagged for capture at T2.

### ⚠ Correction to §2 — the legacy ISIN-bearing file

§2 says "the full bhavcopy contains ISIN." **This is wrong for `sec_bhavdata_full`.** The
`sec_bhavdata_full_DDMMYYYY.csv` (security-deliverable) file has **no ISIN column** — its
columns are `SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE,
LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY,
DELIV_PER`. Since v2 **joins on ISIN** (§2 hazard 2), the correct legacy source is the
**old CM bhavcopy** (`cm<DD><MMM><YYYY>bhav.csv`), which *does* carry ISIN and OHLCV. We do
**not** need delivery data for momentum, so `sec_bhavdata_full` is not used. Both chosen
sources (legacy CM bhavcopy + UDiFF) carry ISIN, so the join key is present across the
whole 2018→present range.

### 1. Legacy source — old CM bhavcopy (pre-cutover) — HAS ISIN

- **Use for trading dates `< 2024-07-08`.**
- URL (historical archive):
  `https://nsearchives.nseindia.com/content/historical/EQUITIES/{YYYY}/{MMM}/cm{DD}{MMM}{YYYY}bhav.csv.zip`
  (e.g. `.../2020/JAN/cm01JAN2020bhav.csv.zip`). `{MMM}` is uppercase 3-letter month.
- **Columns (13):** `SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE, TOTTRDQTY,
  TOTTRDVAL, TIMESTAMP, TOTALTRADES, ISIN`.
- `TOTTRDVAL` is turnover in **₹ (rupees)**, not lakhs → maps directly to `traded_value`.
- **Verbatim data row: ⚠ deferred to T2.** The historical archive needs a warmup cookie
  (WebFetch can't set one — see wrapper note), so a verbatim `cm...bhav.csv` row must be
  pasted into the T2 session log on first successful download. Schema above is confirmed
  across multiple independent sources. As a *real legacy NSE EOD reference row*, here is a
  verbatim `sec_bhavdata_full` row (the deliverable variant, header has leading spaces):
  ```
  SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER
  20MICRONS, EQ, 07-Jun-2024, 173.15, 175.75, 176.60, 172.00, 175.60, 175.70, 173.99, 77482, 134.81, 3195, 50468, 65.14
  ```

### 2. New source — UDiFF CM bhavcopy (post-cutover) — HAS ISIN

- **Use for trading dates `>= 2024-07-08`.**
- URL: `https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip`
- **Columns (34):** `TradDt, BizDt, Sgmt, Src, FinInstrmTp, FinInstrmId, ISIN, TckrSymb,
  SctySrs, XpryDt, FininstrmActlXpryDt, StrkPric, OptnTp, FinInstrmNm, OpnPric, HghPric,
  LwPric, ClsPric, LastPric, PrvsClsgPric, UndrlygPric, SttlmPric, OpnIntrst,
  ChngInOpnIntrst, TtlTradgVol, TtlTrfVal, TtlNbOfTxsExctd, SsnId, NewBrdLotQty, Rmks,
  Rsvd1, Rsvd2, Rsvd3, Rsvd4`.
- Unified-schema mapping: `ISIN→isin`, `TckrSymb→symbol`, `TradDt→date`, `OpnPric/HghPric/
  LwPric/ClsPric→o/h/l/c`, `TtlTradgVol→volume`, `TtlTrfVal→traded_value` (already ₹),
  `SctySrs→series`. Equity rows have `FinInstrmTp=STK` and no `XpryDt`; filter F&O/others.
- **Verbatim data row** (from `2024-07-25`, real UDiFF file):
  ```
  TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,...,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,...,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,...
  2024-07-25,2024-07-25,CM,NSE,STK,368,INE373A01013,BASF,EQ,,,,,BASF INDIA LTD,5898.00,6200.00,5819.50,6172.95,6200.00,5898.35,,6173.05,,,48235,292169028.65,11470,F1,1,,,,,
  ```

### 3. Cutover date (legacy → UDiFF)

- UDiFF go-live: **2024-06-21** (NSE Circular 62424, 2024-06-12). Old + new ran in
  **parallel until 2024-07-05**; legacy **discontinued 2024-07-08**.
- **Decision:** single deterministic cutover constant `BHAVCOPY_UDIFF_CUTOVER =
  2024-07-08`. Dates `< cutover` → legacy CM bhavcopy; `>= cutover` → UDiFF. (Both formats
  exist in the late-June→early-July overlap, so the boundary is safe; T2 should verify both
  files exist for the first UDiFF trading week and fall back to the other format on 404.)

### 4. Corporate-actions feed — HAS ISIN (join key present)

- **Endpoint:** `https://www.nseindia.com/api/corporates-corporateActions`
  Params: `index=equities` (also sme/debt/mf), optional `symbol`, `from_date`, `to_date`
  (format `dd-mm-yyyy`). Returns a JSON **list** of action records. Requires a warmup cookie
  (live fetch timed out without one — confirms NSE blocks naive requests).
- **Fields (14):** `symbol, series, ind, faceVal, subject, exDate, recDate, bcStartDate,
  bcEndDate, ndStartDate, comp, isin, ndEndDate, caBroadcastDate`.
- `subject` is **free text** — split/bonus/dividend ratios are parsed from it (e.g.
  `"Bonus 2:1"`, `"Face Value Split ... From Rs 10/- To Rs 1/-"`, `"Dividend - Rs 5 ..."`).
  This is the T4 parsing burden; unparseable subjects → flag as unmatched (§5.3 / T4).
- **Verbatim record** (real sample from NseIndiaApi `actions.json`):
  ```json
  {"symbol":"GENSOL","series":"EQ","ind":"-","faceVal":"10","subject":"Bonus 2:1",
   "exDate":"17-Oct-2023","recDate":"17-Oct-2023","bcStartDate":"-","bcEndDate":"-",
   "ndStartDate":"-","comp":"Gensol Engineering Limited","isin":"INE06H201014",
   "ndEndDate":"-","caBroadcastDate":null}
  ```

### 5. Index TRI history (needed by `03`, not built here) — EXISTS

- niftyindices.com publishes TRI history (e.g. Nifty200 Momentum 30 TRI). Access via the
  niftyindices.com "Historical Data / TRI" download (POST form) or the NSE historical-index
  portal. **Confirmed it exists; build deferred to `03`.**

### 6. Wrapper vs direct HTTP — **DECISION: direct HTTP**

- `jugaad-data` is maintained (last release 2025-05) **but does NOT support UDiFF** (issue
  #79 open since 2024-06-22). Since v2 spans both formats and the bulk of recent data is
  UDiFF, a wrapper that can't read post-2024-07 data is a non-starter.
- We control both URLs (nsearchives) directly. NSE needs browser-like headers + a warmup
  cookie (hit `https://www.nseindia.com` first to obtain cookies) + polite rate limiting +
  429/5xx backoff regardless of wrapper. **Go direct HTTP** (borrow jugaad-data's
  header/cookie approach as reference). This is the T2 contract.

### 7. Policy decisions

- **Series: `EQ` only** (recommended). `BE` is trade-to-trade settlement (surveillance /
  price-band restricted, often illiquid) — including it risks selecting names in
  surveillance/price-band jail in a monthly momentum portfolio. Retain non-EQ rows through
  parse for audit but scope the universe to `EQ`. Revisit only if coverage proves thin.
- **Liquidity floor default: `adv_20 >= ₹5 crore/day`** — a deliberately conservative
  placeholder. **To be tuned in `04`, not guessed here** (§6).

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
