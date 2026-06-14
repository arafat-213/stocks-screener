"""T4 — Corporate actions: fetch + parse the NSE CA feed and build, per ISIN,
the cumulative split/bonus back-adjustment factor and the dividend stream for the
total-return (TR) series (specs/v2/01_DATA_LAYER.md §4–§5.3, T0 findings).

Source (verified in `01_DATA_LAYER.md` §4 — the feed carries ISIN, the join key):

    https://www.nseindia.com/api/corporates-corporateActions?index=equities
    params: from_date, to_date (dd-mm-yyyy). Returns a JSON list of records.
    Fields (14): symbol, series, ind, faceVal, subject, exDate, recDate,
      bcStartDate, bcEndDate, ndStartDate, comp, isin, ndEndDate, caBroadcastDate.

``subject`` is **free text** — split / bonus / dividend ratios are parsed from it
(e.g. ``"Bonus 2:1"``, ``"Face Value Split From Rs 10/- To Rs 1/-"``,
``"Dividend - Rs 5 Per Share"``). This free-text parse is the T4 burden; anything
that cannot be classified+parsed is **flagged** into ``unmatched`` rather than
silently dropped or inferred from price gaps (CLAUDE.md Rule 12; `01` §5.3:
"Prefer the explicit CA feed over inferring ratios from price gaps").

Factor conventions (back-adjustment — most recent prices are the reference basis):
  * An event with ex-date ``E`` affects prices on dates **strictly before ``E``**
    (on/after ``E`` the traded price already reflects the action). So the
    cumulative factor at date ``d`` is the product of the per-event price
    multipliers for every event whose ex-date ``> d``. The latest prices get
    factor 1.0; older prices are scaled to today's share basis.
  * Split (face value ``old → new``): price multiplier ``new / old`` (a 1:5 split,
    FV 10→2, gives 0.2 — pre-split prices ×0.2 to remove the −80% pseudo-drop).
  * Bonus ``a:b`` (``a`` new shares per ``b`` held): multiplier ``b / (a + b)``
    (Bonus 2:1 → 1/3).
  * Dividend ``D`` per share (TR only): multiplier ``1 − D / close_cum`` where
    ``close_cum`` is the last cum-dividend close (close on the trading day before
    ex-date) — standard reinvestment (`01` §5.3). Signal prices are **not**
    dividend-adjusted (`01` §4 rationale); only ``close_tr`` is.

This module produces the events and the factor series. Applying the factors to the
OHLC columns and writing ``adj_factor`` / ``tr_factor`` / ``close_tr`` is T5
(``adjust.py``); T5 supplies the price/close context the dividend formula needs.
"""

import logging
import re
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests

from app.data.bhavcopy.download import NSE_HOME, build_session

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #
CA_API_URL = "https://www.nseindia.com/api/corporates-corporateActions"

# exDate format in the feed, e.g. "17-Oct-2023".
CA_DATE_FMT = "%d-%b-%Y"

# Event types (the only values ``type`` takes in the events frame).
SPLIT = "split"
BONUS = "bonus"
DIVIDEND = "dividend"

# Canonical column order of the parsed events frame.
CA_EVENT_COLUMNS: list[str] = [
    "isin",
    "symbol",
    "ex_date",
    "type",
    "ratio",
    "dividend",
    "subject",
]
# Columns of the flagged/unmatched frame.
CA_UNMATCHED_COLUMNS: list[str] = ["isin", "symbol", "ex_date_raw", "subject", "reason"]

_RETRY_STATUS = {429, 500, 502, 503, 504}

# --------------------------------------------------------------------------- #
# Subject free-text parsing                                                    #
# --------------------------------------------------------------------------- #
# Explicit capital-structure (split/consolidation) keywords. A bare "face value"
# is deliberately NOT here — dividend subjects routinely say "X% on face value",
# so it only implies a split via the guarded check in `_classify`.
_SPLIT_KEYWORDS = (
    "split",
    "sub-division",
    "sub division",
    "subdivision",
    "consolidation",
)

# A rupee amount: "Rs 5", "Rs.5", "Rs500", "Re 1", "Rs. 2.50".
_RS_RE = re.compile(r"(?:rs|re)\.?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
# "From Rs 10/- To Rs 1/-" → captures old (10) and new (1) face value.
_FV_RE = re.compile(
    r"(?:rs|re)\.?\s*([0-9]+(?:\.[0-9]+)?)\D+?to\b\D*?(?:rs|re)\.?\s*([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE | re.DOTALL,
)
# A "a:b" ratio (bonus, or a ratio-form split).
_RATIO_RE = re.compile(r"(\d+)\s*:\s*(\d+)")
# A percentage (dividend fallback when expressed as % of face value).
_PCT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*%")


def _classify(subject: str) -> str | None:
    """Return the action type implied by ``subject``, or ``None`` if no known
    action keyword is present.

    Dividend subjects often mention "face value", so when "dividend" is present we
    classify it as a dividend unless an *explicit* split/bonus keyword also
    appears (the rare combined-action case). Otherwise a split is recognised by an
    explicit keyword, or by a bare "face value" only when a concrete
    ``Rs X → Rs Y`` change is also present."""
    s = subject.lower()
    has_split_kw = any(k in s for k in _SPLIT_KEYWORDS)
    if "dividend" in s:
        if has_split_kw:
            return SPLIT
        if "bonus" in s:
            return BONUS
        return DIVIDEND
    if has_split_kw or ("face value" in s and _FV_RE.search(subject)):
        return SPLIT
    if "bonus" in s:
        return BONUS
    return None


def _parse_split(subject: str) -> float | None:
    """Price multiplier ``new/old`` for a split/consolidation, or None."""
    m = _FV_RE.search(subject)
    if m:
        old, new = float(m.group(1)), float(m.group(2))
        if old > 0 and new > 0:
            return new / old
    # Ratio-form fallback ("split 1:5" → 1 new face unit per 5 old → 1/5).
    m = _RATIO_RE.search(subject)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a > 0 and b > 0:
            return a / b
    return None


def _parse_bonus(subject: str) -> float | None:
    """Price multiplier ``b/(a+b)`` for a bonus ``a:b``, or None."""
    m = _RATIO_RE.search(subject)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a >= 0 and b > 0:
            return b / (a + b)
    return None


def _parse_dividend(subject: str, face_val: float | None) -> float | None:
    """Total ₹/share dividend, or None.

    Takes the first rupee amount that follows each "dividend" token (so a trailing
    "...of Rs 10 face value" is not mistaken for the payout), summing across
    multiple dividend clauses. Falls back to ``pct% × face_val`` for legacy
    percentage-of-face-value records. Over- or under-counting a dividend only
    nudges the TR series and never breaks the TR ≥ price invariant (`01` §7.5),
    so a pragmatic first-amount rule is acceptable here.
    """
    low = subject.lower()
    amts: list[float] = []
    for dm in re.finditer(r"dividend", low):
        m = _RS_RE.search(subject, dm.end())
        if m:
            amts.append(float(m.group(1)))
    if amts:
        return sum(amts)
    if face_val and face_val > 0:
        pm = _PCT_RE.search(subject)
        if pm:
            return float(pm.group(1)) / 100.0 * face_val
    return None


def _to_face_val(raw) -> float | None:
    try:
        v = float(str(raw).strip())
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Parse                                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class CorporateActions:
    """Result of parsing the CA feed.

    ``events``   — clean, classified actions ready for factor building.
    ``unmatched``— records that could not be classified+parsed (or lack an ISIN /
                   ex-date). Surfaced, never dropped silently (Rule 12).
    """

    events: pd.DataFrame
    unmatched: pd.DataFrame


def parse_corporate_actions(records: list[dict]) -> CorporateActions:
    """Parse raw CA feed records → :class:`CorporateActions`.

    Each record is classified by its free-text ``subject`` into split / bonus /
    dividend and reduced to ``(isin, symbol, ex_date, type, ratio, dividend)``.
    Anything unclassifiable, unparseable, or missing the ISIN / ex-date join keys
    is flagged into ``unmatched`` with a ``reason``.
    """
    events: list[dict] = []
    unmatched: list[dict] = []

    for rec in records:
        isin = (rec.get("isin") or "").strip()
        symbol = (rec.get("symbol") or "").strip()
        subject = (rec.get("subject") or "").strip()
        ex_raw = (rec.get("exDate") or "").strip()

        def _flag(reason: str) -> None:
            unmatched.append(
                {
                    "isin": isin,
                    "symbol": symbol,
                    "ex_date_raw": ex_raw,
                    "subject": subject,
                    "reason": reason,
                }
            )

        if not isin:
            _flag("missing isin (cannot join)")
            continue
        try:
            ex_date = pd.to_datetime(ex_raw, format=CA_DATE_FMT)
        except (ValueError, TypeError):
            _flag(f"unparseable ex-date {ex_raw!r}")
            continue

        kind = _classify(subject)
        if kind is None:
            _flag("no split/bonus/dividend keyword in subject")
            continue

        ratio = np.nan
        dividend = np.nan
        if kind == SPLIT:
            ratio = _parse_split(subject)
        elif kind == BONUS:
            ratio = _parse_bonus(subject)
        else:  # DIVIDEND
            dividend = _parse_dividend(subject, _to_face_val(rec.get("faceVal")))

        if (kind in (SPLIT, BONUS) and not ratio) or (
            kind == DIVIDEND and not dividend
        ):
            _flag(f"{kind}: could not parse value from subject")
            continue

        events.append(
            {
                "isin": isin,
                "symbol": symbol,
                "ex_date": ex_date,
                "type": kind,
                "ratio": float(ratio) if ratio == ratio else np.nan,  # NaN-safe
                "dividend": float(dividend) if dividend == dividend else np.nan,
                "subject": subject,
            }
        )

    events_df = (
        pd.DataFrame(events, columns=CA_EVENT_COLUMNS)
        .drop_duplicates(subset=["isin", "ex_date", "type", "ratio", "dividend"])
        .sort_values(["isin", "ex_date"])
        .reset_index(drop=True)
    )
    unmatched_df = pd.DataFrame(unmatched, columns=CA_UNMATCHED_COLUMNS).reset_index(
        drop=True
    )

    if not unmatched_df.empty:
        logger.warning(
            "bhavcopy.corporate_actions: %d CA record(s) flagged unmatched "
            "(see CorporateActions.unmatched)",
            len(unmatched_df),
        )
    return CorporateActions(events=events_df, unmatched=unmatched_df)


# --------------------------------------------------------------------------- #
# Factor building                                                             #
# --------------------------------------------------------------------------- #
def _cumulative_back_factor(
    ex_dates, multipliers, dates: pd.DatetimeIndex
) -> np.ndarray:
    """For each ``d`` in ``dates``, the product of ``multipliers`` whose ex-date is
    **strictly after ``d``** (the back-adjustment factor at ``d``).

    ``ex_dates``/``multipliers`` need not be sorted. Returns 1.0 where no event
    applies (most recent prices)."""
    dates_arr = np.asarray(pd.DatetimeIndex(dates).values, dtype="datetime64[ns]")
    if len(ex_dates) == 0:
        return np.ones(len(dates_arr))

    ex_arr = np.asarray(pd.DatetimeIndex(ex_dates).values, dtype="datetime64[ns]")
    mult = np.asarray(multipliers, dtype="float64")
    order = np.argsort(ex_arr)
    ex_sorted = ex_arr[order]
    mult_sorted = mult[order]

    # suffix[i] = product of mult_sorted[i:]; suffix[len] = 1.0
    suffix = np.ones(len(mult_sorted) + 1)
    for i in range(len(mult_sorted) - 1, -1, -1):
        suffix[i] = suffix[i + 1] * mult_sorted[i]

    # count of ex-dates <= d → j; events with ex-date > d are suffix[j:] → suffix[j].
    j = np.searchsorted(ex_sorted, dates_arr, side="right")
    return suffix[j]


def split_bonus_factor_series(events: pd.DataFrame, dates) -> pd.Series:
    """Cumulative split+bonus back-adjustment factor at each of ``dates``.

    ``events`` must be the events for a **single ISIN** (the caller groups by
    ISIN). The result is the ``adj_factor`` applied to signal prices in T5 — no
    dividend adjustment (`01` §4)."""
    idx = pd.DatetimeIndex(dates)
    sb = events[events["type"].isin((SPLIT, BONUS))]
    factor = _cumulative_back_factor(sb["ex_date"], sb["ratio"], idx)
    return pd.Series(factor, index=idx, name="adj_factor")


def tr_factor_series(events: pd.DataFrame, dates, close) -> pd.Series:
    """Cumulative total-return back-adjustment factor (split+bonus+dividend).

    ``events`` are for a **single ISIN**. ``close`` is the **raw** (unadjusted)
    close aligned positionally to ``dates`` — T5 supplies ``close_raw``. The
    dividend multiplier ``1 − D/close_cum`` uses the last close strictly before the
    ex-date as ``close_cum``. Dividends with no prior close, a non-positive
    ``close_cum``, or ``D ≥ close_cum`` are skipped (logged) rather than producing a
    non-positive factor. Result is ``≤`` the split/bonus factor everywhere (sets up
    the TR ≥ price check, `01` §7.5)."""
    idx = pd.DatetimeIndex(dates)
    close_s = pd.Series(np.asarray(close, dtype="float64"), index=idx).sort_index()

    ex_list: list = []
    mult_list: list[float] = []
    for ev in events.itertuples(index=False):
        if ev.type in (SPLIT, BONUS):
            ex_list.append(ev.ex_date)
            mult_list.append(float(ev.ratio))
        elif ev.type == DIVIDEND:
            prior = close_s[close_s.index < ev.ex_date]
            if prior.empty:
                logger.warning(
                    "tr_factor: dividend %s on %s has no prior close; skipped",
                    ev.isin,
                    ev.ex_date.date(),
                )
                continue
            cum = prior.iloc[-1]
            d = float(ev.dividend)
            if not np.isfinite(cum) or cum <= 0 or not np.isfinite(d) or d <= 0:
                continue
            m = 1.0 - d / cum
            if m <= 0:
                logger.warning(
                    "tr_factor: dividend %s on %s (D=%.4f) >= close_cum=%.4f; skipped",
                    ev.isin,
                    ev.ex_date.date(),
                    d,
                    cum,
                )
                continue
            ex_list.append(ev.ex_date)
            mult_list.append(m)

    factor = _cumulative_back_factor(ex_list, mult_list, idx)
    return pd.Series(factor, index=idx, name="tr_factor")


# --------------------------------------------------------------------------- #
# Fetch                                                                       #
# --------------------------------------------------------------------------- #
def fetch_corporate_actions(
    start,
    end,
    *,
    session: requests.Session | None = None,
    max_retries: int = 4,
    backoff: float = 1.0,
    timeout: int = 30,
    sleep=time.sleep,
) -> list[dict]:
    """Fetch raw CA records (JSON) from the NSE feed for ``[start, end]``.

    Requires a browser-like, cookie-warmed session (NSE blocks naive requests —
    T0 §6); one is created/closed here if not supplied. Retries on 429/5xx with
    exponential backoff. Returns the raw record list (parse with
    :func:`parse_corporate_actions`)."""
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    own_session = session is None
    if own_session:
        session = build_session()

    params = {
        "index": "equities",
        "from_date": start.strftime("%d-%m-%Y"),
        "to_date": end.strftime("%d-%m-%Y"),
    }
    headers = {"Accept": "application/json, text/plain, */*", "Referer": NSE_HOME}

    try:
        attempt = 0
        while True:
            try:
                resp = session.get(
                    CA_API_URL, params=params, headers=headers, timeout=timeout
                )
            except requests.RequestException as exc:
                if attempt >= max_retries:
                    raise
                wait = backoff * (2**attempt)
                logger.warning(
                    "fetch_corporate_actions: %s; retry %d/%d in %.1fs",
                    exc.__class__.__name__,
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
                    "fetch_corporate_actions: HTTP %d; retry %d/%d in %.1fs",
                    resp.status_code,
                    attempt + 1,
                    max_retries,
                    wait,
                )
                sleep(wait)
                attempt += 1
                continue

            resp.raise_for_status()
            break
    finally:
        if own_session:
            session.close()

    data = resp.json()
    # The feed is a bare list; tolerate a {"data": [...]} envelope defensively.
    if isinstance(data, dict):
        for key in ("data", "records", "rows"):
            if isinstance(data.get(key), list):
                return data[key]
        return []
    return data if isinstance(data, list) else []
