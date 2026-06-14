"""T2 download-layer tests.

Offline only — a fake session, a tmp cache root, no network and no real
``time.sleep`` (CLAUDE.md Rule 4; tests must not hit live NSE — Rule: Mocking
External APIs). Covers format selection by cutover date, URL construction,
idempotent skip-if-present, 429 retry/backoff, 404 → missing (range survives),
and weekend skipping.
"""

from datetime import date

import pytest

from app.data.bhavcopy import download as dl

# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #
_ZIP = dl._ZIP_MAGIC + b"payload"


class FakeResp:
    def __init__(self, status_code: int, content: bytes = b""):
        self.status_code = status_code
        self.content = content


class FakeSession:
    """Records requested URLs and returns whatever ``handler(url)`` yields."""

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[str] = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        return self._handler(url)

    def close(self):
        pass


def _noop_sleep(_seconds):
    return None


# --------------------------------------------------------------------------- #
# Pure helpers                                                                 #
# --------------------------------------------------------------------------- #
def test_format_selection_by_cutover():
    assert dl.bhavcopy_format(date(2024, 7, 5)) == dl.FMT_LEGACY  # pre-cutover
    assert dl.bhavcopy_format(date(2024, 7, 8)) == dl.FMT_UDIFF  # cutover day
    assert dl.bhavcopy_format(date(2024, 7, 25)) == dl.FMT_UDIFF  # post-cutover
    assert dl.bhavcopy_format(date(2020, 1, 1)) == dl.FMT_LEGACY


def test_url_builders_match_verified_findings():
    # Legacy: cm{DD}{MMM}{YYYY}bhav.csv.zip under historical/EQUITIES (01 §1).
    assert dl.source_url(date(2020, 1, 1), dl.FMT_LEGACY) == (
        "https://nsearchives.nseindia.com/content/historical/EQUITIES/"
        "2020/JAN/cm01JAN2020bhav.csv.zip"
    )
    # UDiFF: BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip (01 §2, real file).
    assert dl.source_url(date(2024, 7, 25), dl.FMT_UDIFF) == (
        "https://nsearchives.nseindia.com/content/cm/"
        "BhavCopy_NSE_CM_0_0_0_20240725_F_0000.csv.zip"
    )


# --------------------------------------------------------------------------- #
# download_day / download_range                                                #
# --------------------------------------------------------------------------- #
def test_downloads_then_skips_present_files(tmp_path):
    """Second run over the same trading days does zero network calls."""
    # 2024-07-25 Thu, 2024-07-26 Fri — both trading days, both UDiFF.
    sess1 = FakeSession(lambda url: FakeResp(200, _ZIP))
    res1 = dl.download_range(
        "2024-07-25",
        "2024-07-26",
        root=tmp_path,
        session=sess1,
        rate_limit=0,
        sleep=_noop_sleep,
    )
    assert [r.status for r in res1] == ["downloaded", "downloaded"]
    assert all(r.fmt == dl.FMT_UDIFF for r in res1)
    assert len(sess1.calls) == 2  # one primary hit per day, no fallback
    for r in res1:
        assert r.path.exists() and r.path.stat().st_size > 0

    # Second run: fresh session — must make no calls (idempotent).
    sess2 = FakeSession(lambda url: FakeResp(200, _ZIP))
    res2 = dl.download_range(
        "2024-07-25",
        "2024-07-26",
        root=tmp_path,
        session=sess2,
        rate_limit=0,
        sleep=_noop_sleep,
    )
    assert [r.status for r in res2] == ["cached", "cached"]
    assert sess2.calls == []


def test_picks_correct_format_per_date(tmp_path):
    seen: dict[date, str] = {}

    def handler(url):
        return FakeResp(200, _ZIP)

    # A pre-cutover and a post-cutover trading day.
    for d in (date(2024, 7, 5), date(2024, 7, 25)):
        sess = FakeSession(handler)
        r = dl.download_day(
            d, root=tmp_path, session=sess, rate_limit=0, sleep=_noop_sleep
        )
        seen[d] = r.fmt
        assert "nsearchives.nseindia.com" in sess.calls[0]

    assert seen[date(2024, 7, 5)] == dl.FMT_LEGACY
    assert seen[date(2024, 7, 25)] == dl.FMT_UDIFF


def test_retry_then_success_on_429(tmp_path):
    """429 twice, then 200 — file is written and backoff sleeps were taken."""
    responses = [FakeResp(429), FakeResp(429), FakeResp(200, _ZIP)]
    sess = FakeSession(lambda url: responses.pop(0))
    slept: list[float] = []

    r = dl.download_day(
        date(2024, 7, 25),
        root=tmp_path,
        session=sess,
        rate_limit=0,
        max_retries=3,
        backoff=0.01,
        sleep=slept.append,
    )

    assert r.status == "downloaded"
    assert r.path.exists()
    assert len(sess.calls) == 3  # 2 retried + 1 success
    assert slept == [0.01, 0.02]  # exponential backoff between the 3 attempts


def test_retry_exhausted_is_error_not_crash(tmp_path):
    sess = FakeSession(lambda url: FakeResp(503))
    r = dl.download_day(
        date(2024, 7, 25),
        root=tmp_path,
        session=sess,
        rate_limit=0,
        max_retries=2,
        backoff=0.0,
        sleep=_noop_sleep,
    )
    assert r.status == "error"
    assert r.path is None
    assert "503" in r.detail


def test_404_both_formats_is_missing(tmp_path):
    """A holiday: primary 404, fallback 404 -> missing, no crash, two calls."""
    sess = FakeSession(lambda url: FakeResp(404))
    r = dl.download_day(
        date(2024, 7, 25),
        root=tmp_path,
        session=sess,
        rate_limit=0,
        sleep=_noop_sleep,
    )
    assert r.status == "missing"
    assert r.path is None
    assert len(sess.calls) == 2  # primary + 404-fallback to the other format


def test_missing_day_does_not_break_range(tmp_path):
    """One 404 day in the middle of a range must not abort the surrounding days."""
    hole = date(2024, 7, 25)

    def handler(url):
        # 404 both the UDiFF (20240725) and legacy (25JUL2024) forms of the hole.
        if hole.strftime("%Y%m%d") in url or hole.strftime("%d%b%Y").upper() in url:
            return FakeResp(404)
        return FakeResp(200, _ZIP)

    sess = FakeSession(handler)
    # 2024-07-24 Wed, 25 Thu (hole), 26 Fri.
    res = dl.download_range(
        "2024-07-24",
        "2024-07-26",
        root=tmp_path,
        session=sess,
        rate_limit=0,
        sleep=_noop_sleep,
    )
    statuses = {r.date: r.status for r in res}
    assert statuses[date(2024, 7, 24)] == "downloaded"
    assert statuses[date(2024, 7, 25)] == "missing"
    assert statuses[date(2024, 7, 26)] == "downloaded"


def test_non_zip_200_is_not_cached(tmp_path):
    """NSE block page (HTTP 200, HTML body) must not be cached as a bhavcopy."""
    sess = FakeSession(lambda url: FakeResp(200, b"<html>blocked</html>"))
    r = dl.download_day(
        date(2024, 7, 25),
        root=tmp_path,
        session=sess,
        rate_limit=0,
        sleep=_noop_sleep,
    )
    assert r.status == "error"
    assert r.path is None
    assert not any(tmp_path.iterdir())


def test_weekends_are_skipped(tmp_path):
    """Sat/Sun are never requested (NSE closed)."""
    sess = FakeSession(lambda url: FakeResp(200, _ZIP))
    # 2024-07-26 Fri, 27 Sat, 28 Sun, 29 Mon.
    res = dl.download_range(
        "2024-07-26",
        "2024-07-29",
        root=tmp_path,
        session=sess,
        rate_limit=0,
        sleep=_noop_sleep,
    )
    got_dates = {r.date for r in res}
    assert got_dates == {date(2024, 7, 26), date(2024, 7, 29)}
    assert all("0727" not in u and "0728" not in u for u in sess.calls)


def test_end_before_start_raises(tmp_path):
    sess = FakeSession(lambda url: FakeResp(200, _ZIP))
    with pytest.raises(ValueError, match="before start"):
        dl.download_range(
            "2024-07-26",
            "2024-07-24",
            root=tmp_path,
            session=sess,
            rate_limit=0,
            sleep=_noop_sleep,
        )
