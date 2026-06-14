"""T2 — Download layer for the v2 bhavcopy data pipeline.

Fetch raw daily NSE bhavcopy files (legacy CM bhavcopy + UDiFF) into a disk
cache, idempotently and politely (specs/v2/01_DATA_LAYER.md §5.1, T0 findings).

Sources (verified in `01_DATA_LAYER.md` §1–§3, both carry ISIN):

  * legacy CM bhavcopy  — trading dates ``< 2024-07-08``
    ``.../content/historical/EQUITIES/{YYYY}/{MMM}/cm{DD}{MMM}{YYYY}bhav.csv.zip``
  * UDiFF CM bhavcopy    — trading dates ``>= 2024-07-08``
    ``.../content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip``

The cutover (``BHAVCOPY_UDIFF_CUTOVER``) is a single deterministic date; both
formats coexisted in the late-June→early-July 2024 overlap, so on a 404 for the
chosen format we fall back to the other (T0: "fall back to the other format on
404").

Design notes
------------
* Idempotent: the raw ``.zip`` is cached under ``data/raw/bhavcopy/`` keyed by
  the NSE source filename. A present, non-empty file is never re-fetched, so a
  second run over the same range does zero network calls (CLAUDE.md Pipeline
  Laws: idempotency).
* Polite: a configurable inter-request rate limit, browser-like headers, and a
  warmup-cookie GET to ``nseindia.com`` (NSE blocks naive requests — T0 §6).
* Resilient: explicit retry with exponential backoff on 429/5xx, and on
  transient connection errors. 404 (non-trading day / not yet published) is
  surfaced as ``missing`` and never crashes the range (CLAUDE.md Rule 12).
* Defensive: a 200 whose body is not a ZIP (NSE sometimes serves an HTML block
  page with HTTP 200) is treated as an error and **not** cached.

This is the network/cache boundary only — no parsing happens here (that is T3).
"""

import logging
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #
NSE_HOME = "https://www.nseindia.com"
ARCHIVE_BASE = "https://nsearchives.nseindia.com"

# Single deterministic legacy→UDiFF cutover (01_DATA_LAYER.md §3; NSE Circular
# 62424). Dates < cutover -> legacy CM bhavcopy; >= cutover -> UDiFF.
BHAVCOPY_UDIFF_CUTOVER = date(2024, 7, 8)

FMT_LEGACY = "legacy"
FMT_UDIFF = "udiff"

# ZIP local-file-header magic; guards against NSE returning an HTML block page
# with a 200 status.
_ZIP_MAGIC = b"PK\x03\x04"

_RETRY_STATUS = {429, 500, 502, 503, 504}

# Polite defaults; tunable per call.
DEFAULT_RATE_LIMIT = 0.5  # seconds slept before each request
DEFAULT_MAX_RETRIES = 4  # retries (beyond the first attempt) on 429/5xx/conn err
DEFAULT_BACKOFF = 1.0  # base seconds for exponential backoff
DEFAULT_TIMEOUT = 30  # per-request timeout (seconds)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HOME,
}


@dataclass
class DownloadResult:
    """Per-date outcome of a download attempt.

    ``status`` is one of:
      * ``downloaded`` — fetched from NSE and written to ``path``.
      * ``cached``     — already present on disk; no network call.
      * ``missing``    — both formats 404 (non-trading day / not yet published).
      * ``error``      — exhausted retries / bad payload; ``detail`` explains.
    """

    date: date
    fmt: str
    status: str
    path: Path | None = None
    detail: str = ""


# --------------------------------------------------------------------------- #
# Paths / URLs                                                                 #
# --------------------------------------------------------------------------- #
def default_raw_root() -> Path:
    """Raw cache root: ``<CACHE_DIR or backend/data>/raw/bhavcopy/``.

    Mirrors ``store.default_root`` / ``OHLCVCache`` so all v2 batch artifacts
    live under one ``data/`` tree.
    """
    base = os.environ.get(
        "CACHE_DIR",
        str(Path(__file__).resolve().parents[3] / "data"),
    )
    return Path(base) / "raw" / "bhavcopy"


def _raw_root(root: str | Path | None) -> Path:
    return Path(root) if root is not None else default_raw_root()


def bhavcopy_format(d: date) -> str:
    """Return the bhavcopy format (``legacy``/``udiff``) for trading date ``d``."""
    return FMT_UDIFF if d >= BHAVCOPY_UDIFF_CUTOVER else FMT_LEGACY


def _other_format(fmt: str) -> str:
    return FMT_LEGACY if fmt == FMT_UDIFF else FMT_UDIFF


def source_filename(d: date, fmt: str) -> str:
    """NSE source basename for date ``d`` in the given format."""
    if fmt == FMT_LEGACY:
        mmm = d.strftime("%b").upper()  # uppercase 3-letter month
        return f"cm{d:%d}{mmm}{d.year}bhav.csv.zip"
    if fmt == FMT_UDIFF:
        return f"BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    raise ValueError(f"unknown format {fmt!r}")


def source_url(d: date, fmt: str) -> str:
    """Full download URL for date ``d`` in the given format."""
    fn = source_filename(d, fmt)
    if fmt == FMT_LEGACY:
        mmm = d.strftime("%b").upper()
        return f"{ARCHIVE_BASE}/content/historical/EQUITIES/{d.year}/{mmm}/{fn}"
    return f"{ARCHIVE_BASE}/content/cm/{fn}"


def _cache_path(root: Path, d: date, fmt: str) -> Path:
    return root / source_filename(d, fmt)


# --------------------------------------------------------------------------- #
# HTTP                                                                         #
# --------------------------------------------------------------------------- #
def build_session(warmup: bool = True, timeout: int = 10) -> requests.Session:
    """Create a browser-like session and (best-effort) warm a cookie.

    NSE rejects naive requests; hitting the home page first seeds the cookies
    the archive host expects (T0 §6). Warmup failures are non-fatal — the
    archive request may still succeed and will retry on its own.
    """
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    if warmup:
        try:
            s.get(NSE_HOME, timeout=timeout)
        except requests.RequestException as exc:
            logger.warning("bhavcopy.download: warmup cookie fetch failed: %s", exc)
    return s


def _get(
    session: requests.Session,
    url: str,
    *,
    rate_limit: float,
    max_retries: int,
    backoff: float,
    timeout: int,
    sleep,
) -> requests.Response:
    """GET ``url`` with a polite rate limit and explicit 429/5xx + connection
    retry/backoff. Returns the final response (which may be non-200); raises
    only if connection errors persist past ``max_retries``."""
    attempt = 0
    while True:
        if rate_limit:
            sleep(rate_limit)
        try:
            resp = session.get(url, timeout=timeout)
        except requests.RequestException as exc:
            if attempt >= max_retries:
                raise
            wait = backoff * (2**attempt)
            logger.warning(
                "bhavcopy.download: %s on %s; retry %d/%d in %.1fs",
                exc.__class__.__name__,
                url,
                attempt + 1,
                max_retries,
                wait,
            )
            sleep(wait)
            attempt += 1
            continue

        if resp.status_code in _RETRY_STATUS and attempt < max_retries:
            wait = backoff * (2**attempt)
            logger.warning(
                "bhavcopy.download: HTTP %d on %s; retry %d/%d in %.1fs",
                resp.status_code,
                url,
                attempt + 1,
                max_retries,
                wait,
            )
            sleep(wait)
            attempt += 1
            continue

        return resp


def _write_atomic(content: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #
def _to_date(x) -> date:
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    return pd.Timestamp(x).date()


def download_day(
    d,
    *,
    root: str | Path | None = None,
    session: requests.Session,
    rate_limit: float = DEFAULT_RATE_LIMIT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    timeout: int = DEFAULT_TIMEOUT,
    sleep=time.sleep,
) -> DownloadResult:
    """Download one trading day's bhavcopy, choosing format by date and falling
    back to the other format on 404. Idempotent: a present file is reused.

    ``session`` is required (created/closed by :func:`download_range` for ranges).
    """
    d = _to_date(d)
    root = _raw_root(root)
    primary = bhavcopy_format(d)
    order = [primary, _other_format(primary)]

    # 1) Idempotency: reuse a present, non-empty cached file (no network).
    for fmt in order:
        path = _cache_path(root, d, fmt)
        if path.exists() and path.stat().st_size > 0:
            return DownloadResult(d, fmt, "cached", path)

    # 2) Fetch: try primary, then the other format on 404.
    details: list[str] = []
    hard_error = False  # a non-404 failure occurred (vs. a clean "not published")
    for fmt in order:
        url = source_url(d, fmt)
        try:
            resp = _get(
                session,
                url,
                rate_limit=rate_limit,
                max_retries=max_retries,
                backoff=backoff,
                timeout=timeout,
                sleep=sleep,
            )
        except requests.RequestException as exc:
            details.append(f"{fmt}: connection error {exc.__class__.__name__}")
            hard_error = True
            logger.warning("bhavcopy.download: %s on %s", details[-1], url)
            continue

        if resp.status_code == 200:
            if not resp.content.startswith(_ZIP_MAGIC):
                details.append(
                    f"{fmt}: 200 but body is not a ZIP ({len(resp.content)} bytes)"
                )
                hard_error = True
                logger.warning("bhavcopy.download: %s on %s", details[-1], url)
                continue
            path = _cache_path(root, d, fmt)
            _write_atomic(resp.content, path)
            logger.info(
                "bhavcopy.download: fetched %s (%s)", source_filename(d, fmt), fmt
            )
            return DownloadResult(d, fmt, "downloaded", path)

        if resp.status_code == 404:
            details.append(f"{fmt}: 404")
            continue

        details.append(f"{fmt}: HTTP {resp.status_code}")
        hard_error = True

    detail = "; ".join(details)
    # Both formats 404 with no harder failure -> non-trading day / not published.
    status = "error" if hard_error else "missing"
    return DownloadResult(d, primary, status, None, detail)


def download_range(
    start,
    end,
    *,
    root: str | Path | None = None,
    session: requests.Session | None = None,
    rate_limit: float = DEFAULT_RATE_LIMIT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    timeout: int = DEFAULT_TIMEOUT,
    skip_weekends: bool = True,
    sleep=time.sleep,
) -> list[DownloadResult]:
    """Download the bhavcopy for every day in ``[start, end]`` (inclusive).

    Missing files (holidays / not-yet-published) are recorded, not fatal. If no
    ``session`` is given, one is created (with cookie warmup) and closed here.
    Weekends are skipped by default (NSE is closed).
    """
    start = _to_date(start)
    end = _to_date(end)
    if end < start:
        raise ValueError(f"end {end} is before start {start}")

    own_session = session is None
    if own_session:
        session = build_session()

    results: list[DownloadResult] = []
    try:
        d = start
        while d <= end:
            if skip_weekends and d.weekday() >= 5:  # 5=Sat, 6=Sun
                d += timedelta(days=1)
                continue
            results.append(
                download_day(
                    d,
                    root=root,
                    session=session,
                    rate_limit=rate_limit,
                    max_retries=max_retries,
                    backoff=backoff,
                    timeout=timeout,
                    sleep=sleep,
                )
            )
            d += timedelta(days=1)
    finally:
        if own_session:
            session.close()

    return results
