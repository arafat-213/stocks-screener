"""T7 — Build orchestrator: end-to-end idempotent + resumable pipeline,
checkpointed by date (CLAUDE.md Pipeline Laws).

Pipeline stages (01_DATA_LAYER.md §5):
  1. Download — fetch raw .zip files into ``data/raw/bhavcopy/``.
  2. Parse    — decode each day → unified raw rows; write per-day parquet checkpoint.
  3. CA       — fetch + parse corporate-actions feed for the date range.
  4. Adjust   — apply CA back-adjustment (split/bonus → prices; +dividend → close_tr).
  5. Universe — compute adv_20 (rolling median) + emit membership + isin_symbol_map.
  6. Store    — write final parquet tables via store.py.

Checkpoint design
-----------------
A JSON file (``{root}/.build_checkpoint.json``) records per-date status::

    {
        "version": 1,
        "days": {
            "2024-01-02": "ok",       # downloaded + parsed; per-day parquet written
            "2024-01-03": "missing",  # both format 404s (holiday / not yet published)
            "2024-01-04": "error",    # non-retryable failure
            "2024-01-05": "empty"     # downloaded but 0 in-scope rows → provisional
        },
        "errors": {
            "2024-01-04": "<detail string>"
        }
    }

On resume, dates already ``ok`` or ``missing`` load from their per-day parquet
(``{root}/raw_parsed/YYYY-MM-DD.parquet``) without re-downloading or re-parsing.
``empty`` (a date that downloaded but parsed to 0 in-scope rows, e.g. a not-yet-
final EOD file) is recorded but **never counted as coverage** — guarding the §7
over-claim where a date showed ``ok`` while ``prices_adjusted`` stored no rows.
Stages 4–6 always re-run from the assembled raw data — this ensures adv_20 rolling
windows are consistent across the full date range on every run.

Idempotency guarantee
---------------------
* Stage 1: present, non-empty .zip files are reused (T2 idempotency).
* Stage 2: checkpoint skip avoids re-parse of completed days.
* Stage 6: ``write_prices_adjusted`` / ``write_universe_membership`` use
  ``existing_data_behavior="delete_matching"`` — safe to overwrite (T1).

⚠ Chunked / incremental invocation caveat
------------------------------------------
Always build the **entire date range in a single ``run_build`` call**.
Calling ``run_build('2019','2020')`` after ``run_build('2018','2019')``
**silently clobbers the 2018 data**: Stage 2 only assembles ``ok_dates``
from the current invocation's range, then Stage 6 overwrites all partitions
for every ISIN seen in that range (``delete_matching`` is per-ISIN, not
per-date). The 20-day adv_20 rolling window would also be recomputed without
the earlier history. Resume-after-crash within a single invocation is safe —
the day loop re-walks start→end and loads checkpointed days from disk.

Per-day error handling
----------------------
A single download or parse failure is recorded and skipped rather than crashing
the whole run (CLAUDE.md Pipeline Laws: "classify/record per-symbol failures").
The ``BuildReport.error_details`` list collects all failures; the build completes
on the remaining good days and the run is not fatal.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from app.data.bhavcopy import adjust as adj_mod
from app.data.bhavcopy import corporate_actions as ca_mod
from app.data.bhavcopy import download as dl_mod
from app.data.bhavcopy import market_internals as mi_mod
from app.data.bhavcopy import parse as parse_mod
from app.data.bhavcopy import store as store_mod
from app.data.bhavcopy import succession as succ_mod
from app.data.bhavcopy import universe as uni_mod
from app.data.bhavcopy import validate as val_mod

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #
_CHECKPOINT_FILE = ".build_checkpoint.json"
_RAW_PARSED_DIR = "raw_parsed"

_STATUS_OK = "ok"
_STATUS_MISSING = "missing"
_STATUS_ERROR = "error"
_STATUS_EMPTY = "empty"  # downloaded + parsed but 0 in-scope rows → no coverage


# --------------------------------------------------------------------------- #
# Data classes                                                                 #
# --------------------------------------------------------------------------- #
@dataclass
class DayResult:
    """Per-date outcome of Stage 1 (download + parse)."""

    date: date
    status: str  # "ok", "missing", "error"
    detail: str = ""


@dataclass
class BuildReport:
    """Summary of a build run."""

    start: date
    end: date
    days_ok: int = 0
    days_missing: int = 0
    days_error: int = 0
    days_empty: int = 0
    ca_events: int = 0
    ca_unmatched: int = 0
    rows_written: int = 0
    distinct_isins: int = 0
    error_details: list[str] = field(default_factory=list)
    # Populated when skip_validation=False; None otherwise.
    val_report: object = None

    def summary(self) -> str:
        return (
            f"Build {self.start}→{self.end}: "
            f"{self.days_ok} days ok, {self.days_missing} missing, "
            f"{self.days_empty} empty, {self.days_error} errors | "
            f"{self.rows_written:,} rows, {self.distinct_isins} ISINs | "
            f"CA: {self.ca_events} events, {self.ca_unmatched} unmatched"
        )


# --------------------------------------------------------------------------- #
# Checkpoint helpers                                                           #
# --------------------------------------------------------------------------- #
def _load_checkpoint(root: Path) -> dict:
    """Load the checkpoint JSON; return a fresh empty checkpoint on any failure."""
    p = root / _CHECKPOINT_FILE
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "build: corrupt checkpoint at %s (%s); starting fresh", p, exc
            )
    return {"version": 1, "days": {}, "errors": {}}


def _save_checkpoint(root: Path, cp: dict) -> None:
    """Atomically write the checkpoint so a mid-write crash leaves a valid file."""
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / (_CHECKPOINT_FILE + ".tmp")
    tmp.write_text(json.dumps(cp, indent=2))
    tmp.replace(root / _CHECKPOINT_FILE)


def _parsed_path(root: Path, d: date) -> Path:
    """Canonical path for the per-day parsed parquet checkpoint."""
    return root / _RAW_PARSED_DIR / f"{d.isoformat()}.parquet"


# --------------------------------------------------------------------------- #
# Stage 1: per-day download + parse                                            #
# --------------------------------------------------------------------------- #
def _process_day(
    d: date,
    *,
    raw_root: Path,
    store_root: Path,
    checkpoint: dict,
    session: requests.Session,
    rate_limit: float,
    max_retries: int,
    sleep,
) -> DayResult:
    """Download and parse one trading day; write its per-day parquet checkpoint.

    Idempotent: days already marked ``ok`` or ``missing`` in the checkpoint are
    loaded from disk (zero network calls). Per-day errors are returned, not raised
    (the caller records and skips them — CLAUDE.md Pipeline Laws).
    """
    date_str = d.isoformat()
    days = checkpoint["days"]

    # Already processed — load from disk (no network). ``empty`` is terminal-on-
    # resume like ``missing`` (its cached .zip is reused by download anyway), so it
    # is recorded once and not re-parsed every run.
    if date_str in days and days[date_str] in (
        _STATUS_OK,
        _STATUS_MISSING,
        _STATUS_EMPTY,
    ):
        return DayResult(d, days[date_str])

    # Download.
    dl_result = dl_mod.download_day(
        d,
        root=raw_root,
        session=session,
        rate_limit=rate_limit,
        max_retries=max_retries,
        sleep=sleep,
    )

    if dl_result.status == _STATUS_MISSING:
        days[date_str] = _STATUS_MISSING
        return DayResult(d, _STATUS_MISSING)

    if dl_result.status == _STATUS_ERROR or dl_result.path is None:
        days[date_str] = _STATUS_ERROR
        checkpoint.setdefault("errors", {})[date_str] = dl_result.detail
        return DayResult(d, _STATUS_ERROR, dl_result.detail)

    # Parse.
    try:
        raw_df = parse_mod.parse_file(dl_result.path, dl_result.fmt)
    except Exception as exc:
        detail = f"parse error: {exc!r}"
        logger.warning("build: %s on %s", detail, d)
        days[date_str] = _STATUS_ERROR
        checkpoint.setdefault("errors", {})[date_str] = detail
        return DayResult(d, _STATUS_ERROR, detail)

    # Write per-day parquet (even if empty — valid for days with no EQ rows).
    parsed_p = _parsed_path(store_root, d)
    parsed_p.parent.mkdir(parents=True, exist_ok=True)
    raw_df.to_parquet(parsed_p, index=False)

    # T06.0 coverage guard (§7): a downloaded-but-zero-row day (e.g. a not-yet-final
    # EOD file that parses to no in-scope EQ rows) must NOT claim coverage. Mark it
    # "empty" — recorded but never counted as covered — rather than "ok", which would
    # over-claim a date that stored nothing.
    if raw_df.empty:
        days[date_str] = _STATUS_EMPTY
        return DayResult(d, _STATUS_EMPTY)

    days[date_str] = _STATUS_OK
    return DayResult(d, _STATUS_OK)


# --------------------------------------------------------------------------- #
# Stage 2: load all checkpointed raw days                                      #
# --------------------------------------------------------------------------- #
def _load_raw_days(root: Path, ok_dates: list[date]) -> pd.DataFrame:
    """Concat all per-day parsed parquets for the given dates into one frame."""
    parts = []
    for d in ok_dates:
        p = _parsed_path(root, d)
        if p.exists():
            df = pd.read_parquet(p)
            if not df.empty:
                parts.append(df)
        else:
            logger.warning(
                "build: expected per-day parquet missing for %s; skipping", d
            )
    if not parts:
        return pd.DataFrame(columns=parse_mod.UNIFIED_RAW_COLUMNS)
    return pd.concat(parts, ignore_index=True)


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #
def run_build(
    start,
    end,
    *,
    root: str | Path | None = None,
    raw_root: str | Path | None = None,
    rate_limit: float = dl_mod.DEFAULT_RATE_LIMIT,
    max_retries: int = dl_mod.DEFAULT_MAX_RETRIES,
    sleep=time.sleep,
    _session: requests.Session | None = None,
    _ca_records: list[dict] | None = None,
    skip_validation: bool = False,
    raise_on_check9: bool = True,
) -> BuildReport:
    """End-to-end bhavcopy pipeline: download → parse → CA → adjust → store.

    Parameters
    ----------
    start, end:
        Inclusive date range (``date``, ``str``, or ``pd.Timestamp``).
    root:
        Parquet store root (default: ``store.default_root()``).
    raw_root:
        Raw .zip cache root (default: ``download.default_raw_root()``).
    rate_limit:
        Seconds to sleep before each HTTP request (polite crawling).
    max_retries:
        Max retries on 429/5xx before recording a day as error.
    sleep:
        Injection point for ``time.sleep`` (tests pass a no-op).
    _session:
        Injected ``requests.Session``; when ``None``, one is created with cookie
        warmup. Closed here after Stage 1 if owned by this call.
    _ca_records:
        Injected raw CA records (list of dicts from the NSE feed). When provided,
        the CA fetch is skipped entirely — intended for tests.

    Returns
    -------
    BuildReport
        Summary of the run. Check ``report.days_error`` and
        ``report.error_details`` for any per-day failures.
    """
    start_d = dl_mod._to_date(start)
    end_d = dl_mod._to_date(end)
    if end_d < start_d:
        raise ValueError(f"end {end_d} is before start {start_d}")

    store_root = store_mod._root(root)
    dl_raw_root = dl_mod._raw_root(raw_root)
    store_root.mkdir(parents=True, exist_ok=True)

    checkpoint = _load_checkpoint(store_root)
    report = BuildReport(start=start_d, end=end_d)

    # ------------------------------------------------------------------ #
    # Stage 1: Download + parse (per-day, checkpointed)                   #
    # ------------------------------------------------------------------ #
    logger.info("build: Stage 1 — download+parse %s → %s", start_d, end_d)

    own_session = _session is None
    session = _session if _session is not None else dl_mod.build_session()

    ok_dates: list[date] = []
    try:
        d = start_d
        while d <= end_d:
            if d.weekday() >= 5:  # skip weekends (NSE is closed)
                d += timedelta(days=1)
                continue

            result = _process_day(
                d,
                raw_root=dl_raw_root,
                store_root=store_root,
                checkpoint=checkpoint,
                session=session,
                rate_limit=rate_limit,
                max_retries=max_retries,
                sleep=sleep,
            )

            if result.status == _STATUS_OK:
                report.days_ok += 1
                ok_dates.append(d)
            elif result.status == _STATUS_MISSING:
                report.days_missing += 1
            elif result.status == _STATUS_EMPTY:
                report.days_empty += 1
            else:
                report.days_error += 1
                report.error_details.append(result.detail)
                logger.warning("build: day %s failed: %s", d, result.detail)

            # Persist checkpoint after each day so a crash allows clean resume.
            _save_checkpoint(store_root, checkpoint)
            d += timedelta(days=1)
    finally:
        if own_session:
            session.close()

    if not ok_dates:
        logger.warning("build: no trading days with data in range; nothing to store")
        return report

    # ------------------------------------------------------------------ #
    # Stage 2: Load raw parsed days                                        #
    # ------------------------------------------------------------------ #
    logger.info("build: Stage 2 — loading %d parsed day(s)", len(ok_dates))
    raw_df = _load_raw_days(store_root, ok_dates)

    if raw_df.empty:
        logger.warning("build: all parsed days are empty (no in-scope EQ rows)")
        return report

    # ------------------------------------------------------------------ #
    # Stage 3: Corporate actions                                           #
    # ------------------------------------------------------------------ #
    logger.info("build: Stage 3 — corporate actions")
    if _ca_records is not None:
        ca_records = _ca_records
        logger.debug("build: using injected CA records (%d)", len(ca_records))
    else:
        logger.info("build: fetching CA records from NSE for %s → %s", start_d, end_d)
        ca_records = ca_mod.fetch_corporate_actions(
            start_d,
            end_d,
            max_retries=max_retries,
            sleep=sleep,
        )

    ca = ca_mod.parse_corporate_actions(ca_records)
    report.ca_events = len(ca.events)
    report.ca_unmatched = len(ca.unmatched)
    logger.info(
        "build: %d CA events, %d unmatched", report.ca_events, report.ca_unmatched
    )

    # Persist CA events and unmatched as an audit trail so subsequent validation /
    # diagnosis runs can inspect them without re-fetching from the NSE API.
    logger.info("build: persisting CA events audit trail")
    store_mod.write_corporate_actions(ca.events, root)
    store_mod.write_ca_unmatched(ca.unmatched, root)

    # ------------------------------------------------------------------ #
    # Stage 4: Adjust prices                                               #
    # ------------------------------------------------------------------ #
    logger.info("build: Stage 4 — adjusting prices")
    adjusted_df = adj_mod.adjust_prices(raw_df, ca.events)

    # ------------------------------------------------------------------ #
    # Stages 5–6: Universe (adv_20 + membership + isin_symbol_map)        #
    # ------------------------------------------------------------------ #
    logger.info("build: Stages 5–6 — universe + liquidity")
    # Chain-constant identity (06_ISIN_SUCCESSION_CONTINUITY, T06.2): if a successor
    # map already exists (built by T06.1 / succession.run_succession_build), collapse
    # each asserted chain onto its root ISIN so the rebuilt store carries
    # instrument_id natively. Absent (e.g. a first build) ⇒ identity for every ISIN.
    id_map = succ_mod.instrument_id_map(store_mod.read_successor_map(root))
    prices_df, membership_df, isin_map_df = uni_mod.build_universe(adjusted_df, id_map)

    # ------------------------------------------------------------------ #
    # Stage 7: Store parquet tables                                        #
    # ------------------------------------------------------------------ #
    logger.info("build: Stage 7 — storing parquet tables")
    store_mod.write_prices_adjusted(prices_df, root)
    store_mod.write_universe_membership(membership_df, root)
    store_mod.write_isin_symbol_map(isin_map_df, root)

    report.rows_written = len(prices_df)
    report.distinct_isins = prices_df["isin"].nunique()

    # ------------------------------------------------------------------ #
    # Stage 7b: Market internals (v4/01 — regime-score inputs)            #
    # ------------------------------------------------------------------ #
    # Derive daily breadth + A/D (all-EQ and liquid-subset) from the adjusted panel
    # and persist them, regenerated every build (the orphan-MarketBreadth fix — never
    # hand-populated; specs/v4/01_REGIME_DATA_LAYER.md §2A/§3). India VIX is left NaN
    # here — Part B lands it separately; the 3-factor regime tier works without it.
    # Additive only: this reads ``prices_df`` and writes a new artifact; it does not
    # touch prices_adjusted / membership / any backtest (01 §7).
    logger.info("build: Stage 7b — market internals (breadth + A/D)")
    # Fold in the India VIX source cache if present (Part B); absent ⇒ india_vix NaN
    # (the 3-factor regime tier still works). The build does not fetch VIX — that is
    # india_vix.backfill_india_vix's job, keeping the build network-free for VIX.
    vix_cache = store_mod.read_india_vix(root)
    internals_df = mi_mod.compute_market_internals(
        prices_df, vix_series=None if vix_cache.empty else vix_cache
    )
    store_mod.write_market_internals(internals_df, root)

    # ------------------------------------------------------------------ #
    # Stage 8: Validate (the gate — 01_DATA_LAYER.md §7)                  #
    # ------------------------------------------------------------------ #
    if not skip_validation:
        logger.info("build: Stage 8 — running validate.py acceptance checks")
        report.val_report = val_mod.run_validation(
            root,
            ca_events_applied=report.ca_events,
            ca_events_unmatched=report.ca_unmatched,
            raise_on_check9=raise_on_check9,
        )

    logger.info("build: %s", report.summary())
    return report
