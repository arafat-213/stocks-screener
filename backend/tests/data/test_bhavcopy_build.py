"""T7 build-orchestrator tests.

Offline only — fake HTTP sessions, synthetic zip fixtures, injected _ca_records=[].
No network, no time.sleep (CLAUDE.md Rules 4, 5).

Covers:
  * Full run over a small date range produces all three tables.
  * Resume: killing mid-run (partial checkpoint) → restart skips done days,
    final output identical to an uninterrupted run.
  * A single bad day (download error) is recorded and skipped, not fatal.
  * Idempotent: running twice over the same range produces no duplicates.
  * Missing day (404 both formats) is recorded as 'missing', not an error.
  * Weekend days are skipped automatically.
"""

import io
import zipfile
from datetime import date

import pandas as pd
import pytest

from app.data.bhavcopy import build as bld
from app.data.bhavcopy import download as dl
from app.data.bhavcopy import parse as parse_mod
from app.data.bhavcopy import store as store_mod

# --------------------------------------------------------------------------- #
# UDiFF fixture helpers                                                        #
# --------------------------------------------------------------------------- #
_UDIFF_HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,"
    "XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,"
    "LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,"
    "ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,"
    "Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4"
)
_COLS = _UDIFF_HEADER.split(",")


def _udiff_row(**kw: str) -> str:
    defaults: dict[str, str] = {
        "TradDt": "2024-07-08",
        "BizDt": "2024-07-08",
        "Sgmt": "CM",
        "Src": "NSE",
        "FinInstrmTp": "STK",
        "FinInstrmId": "1",
        "ISIN": "INE000A00000",
        "TckrSymb": "DUMMY",
        "SctySrs": "EQ",
        "XpryDt": "",
        "FininstrmActlXpryDt": "",
        "StrkPric": "",
        "OptnTp": "",
        "FinInstrmNm": "DUMMY LTD",
        "OpnPric": "100.00",
        "HghPric": "105.00",
        "LwPric": "98.00",
        "ClsPric": "103.00",
        "LastPric": "103.00",
        "PrvsClsgPric": "100.00",
        "UndrlygPric": "",
        "SttlmPric": "103.00",
        "OpnIntrst": "",
        "ChngInOpnIntrst": "",
        "TtlTradgVol": "10000",
        "TtlTrfVal": "1030000.00",
        "TtlNbOfTxsExctd": "500",
        "SsnId": "F1",
        "NewBrdLotQty": "1",
        "Rmks": "",
        "Rsvd1": "",
        "Rsvd2": "",
        "Rsvd3": "",
        "Rsvd4": "",
    }
    defaults.update(kw)
    return ",".join(defaults[c] for c in _COLS)


def _udiff_csv(trad_dt: str, close: float = 103.0, isin: str = "INE002A01018") -> str:
    """Minimal 1-row UDiFF CSV for ``trad_dt``."""
    return (
        _UDIFF_HEADER
        + "\n"
        + _udiff_row(
            TradDt=trad_dt,
            BizDt=trad_dt,
            ISIN=isin,
            TckrSymb="RELIANCE",
            FinInstrmNm="RELIANCE INDUSTRIES LTD",
            OpnPric="2800.00",
            HghPric="2850.00",
            LwPric="2790.00",
            ClsPric=str(close),
            TtlTradgVol="1000000",
            TtlTrfVal=str(round(close * 1_000_000, 2)),
        )
        + "\n"
    )


def _zip(csv_text: str, inner: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner, csv_text.encode())
    return buf.getvalue()


def _udiff_zip(trad_dt: str, close: float = 103.0, isin: str = "INE002A01018") -> bytes:
    fn = f"BhavCopy_NSE_CM_0_0_0_{trad_dt.replace('-', '')}_F_0000.csv"
    return _zip(_udiff_csv(trad_dt, close=close, isin=isin), fn)


# Test dates: Mon–Wed post-cutover (UDiFF format).
_DAY1 = date(2024, 7, 8)  # Monday (cutover day)
_DAY2 = date(2024, 7, 9)  # Tuesday
_DAY3 = date(2024, 7, 10)  # Wednesday


# --------------------------------------------------------------------------- #
# Fake HTTP                                                                    #
# --------------------------------------------------------------------------- #
_ZIP_MAGIC = dl._ZIP_MAGIC


class FakeResp:
    def __init__(self, status: int, content: bytes = b""):
        self.status_code = status
        self.content = content


class FakeSession:
    """Returns responses via a per-URL handler; records call URLs."""

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[str] = []

    def get(self, url, timeout=None, **kwargs):
        self.calls.append(url)
        return self._handler(url)

    def close(self):
        pass


def _noop(*_):
    pass


def _session_serving(days: dict[date, bytes | int]) -> FakeSession:
    """Build a FakeSession that serves zip bytes or a status code per date."""

    def handler(url: str) -> FakeResp:
        for d, payload in days.items():
            token = d.strftime("%Y%m%d")
            if token in url:
                if isinstance(payload, int):
                    return FakeResp(payload, b"")
                return FakeResp(200, payload)
        return FakeResp(404, b"")

    return FakeSession(handler)


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #
class TestFullRun:
    """A two-day run produces all three tables with expected content."""

    def test_all_three_tables_populated(self, tmp_path):
        sess = _session_serving(
            {
                _DAY1: _udiff_zip(_DAY1.isoformat()),
                _DAY2: _udiff_zip(_DAY2.isoformat(), close=110.0),
            }
        )
        report = bld.run_build(
            _DAY1,
            _DAY2,
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _session=sess,
            _ca_records=[],
        )

        assert report.days_ok == 2, report
        assert report.days_error == 0
        assert report.rows_written == 2  # one row per trading day (1 ISIN × 2 days)
        assert report.distinct_isins == 1

        prices = store_mod.read_prices_adjusted(root=tmp_path / "store")
        assert len(prices) == 2
        assert set(prices.columns) == set(store_mod.PRICES_ADJUSTED_SCHEMA)

        membership = store_mod.read_universe_membership(root=tmp_path / "store")
        assert len(membership) == 2

        isin_map = store_mod.read_isin_symbol_map(root=tmp_path / "store")
        assert len(isin_map) == 1
        assert isin_map.iloc[0]["isin"] == "INE002A01018"

    def test_prices_are_adjusted_by_ca_events(self, tmp_path):
        """With a 1:5 split CA (ratio=0.2), adjusted prices should be 0.2× raw."""
        ca_record = {
            "isin": "INE002A01018",
            "symbol": "RELIANCE",
            "series": "EQ",
            "faceVal": "10",
            "subject": "Face Value Split From Rs 10/- To Rs 2/-",
            "exDate": "09-Jul-2024",  # Day2 is ex-date
            "recDate": "09-Jul-2024",
            "bcStartDate": "-",
            "bcEndDate": "-",
            "ndStartDate": "-",
            "comp": "Reliance Industries Limited",
            "ndEndDate": "-",
            "caBroadcastDate": None,
        }
        sess = _session_serving(
            {
                _DAY1: _udiff_zip(_DAY1.isoformat(), close=2840.0),
                _DAY2: _udiff_zip(_DAY2.isoformat(), close=568.0),
            }
        )
        report = bld.run_build(
            _DAY1,
            _DAY2,
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _session=sess,
            _ca_records=[ca_record],
        )

        assert report.ca_events == 1
        prices = store_mod.read_prices_adjusted(root=tmp_path / "store")
        day1_row = prices[prices["date"] == pd.Timestamp(_DAY1)].iloc[0]
        day2_row = prices[prices["date"] == pd.Timestamp(_DAY2)].iloc[0]

        # Day1 (before ex-date 2024-07-09) gets adj_factor 0.2 (1:5 split).
        assert abs(day1_row["adj_factor"] - 0.2) < 1e-9
        assert abs(day1_row["close"] - day1_row["close_raw"] * 0.2) < 1e-6

        # Day2 (on/after ex-date) has adj_factor = 1.0 (no back-adjustment needed).
        assert abs(day2_row["adj_factor"] - 1.0) < 1e-9


class TestResume:
    """Killing mid-run and restarting skips completed days; output is identical."""

    def test_resume_skips_checkpointed_days(self, tmp_path):
        root = tmp_path / "store"
        raw_root = tmp_path / "raw"

        # Simulate a partial run: Day1 already processed (parquet + checkpoint).
        day1_df = parse_mod.parse_bytes(
            _udiff_csv(_DAY1.isoformat()).encode(), dl.FMT_UDIFF
        )
        day1_parquet = bld._parsed_path(root, _DAY1)
        day1_parquet.parent.mkdir(parents=True, exist_ok=True)
        day1_df.to_parquet(day1_parquet, index=False)

        cp = {"version": 1, "days": {_DAY1.isoformat(): "ok"}, "errors": {}}
        bld._save_checkpoint(root, cp)

        # Only Day2 should be downloaded — Day1 must be skipped.
        sess = _session_serving({_DAY2: _udiff_zip(_DAY2.isoformat(), close=110.0)})
        report = bld.run_build(
            _DAY1,
            _DAY2,
            root=root,
            raw_root=raw_root,
            sleep=_noop,
            _session=sess,
            _ca_records=[],
        )

        assert report.days_ok == 2
        # Day1 URL must NOT appear in session calls.
        day1_token = _DAY1.strftime("%Y%m%d")
        assert not any(day1_token in url for url in sess.calls), sess.calls

        prices = store_mod.read_prices_adjusted(root=root)
        assert len(prices) == 2  # both days present in final output

    def test_identical_output_with_or_without_resume(self, tmp_path):
        """Full run and a resumed run starting from same checkpoint give same table."""
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        raw_a = tmp_path / "raw_a"
        raw_b = tmp_path / "raw_b"

        kwargs = dict(sleep=_noop, _ca_records=[])

        # Full uninterrupted run → root_a.
        sess_a = _session_serving(
            {
                _DAY1: _udiff_zip(_DAY1.isoformat()),
                _DAY2: _udiff_zip(_DAY2.isoformat()),
            }
        )
        bld.run_build(
            _DAY1, _DAY2, root=root_a, raw_root=raw_a, _session=sess_a, **kwargs
        )

        # Partial run: Day1 already done → run with Day1 in checkpoint.
        day1_df = parse_mod.parse_bytes(
            _udiff_csv(_DAY1.isoformat()).encode(), dl.FMT_UDIFF
        )
        p = bld._parsed_path(root_b, _DAY1)
        p.parent.mkdir(parents=True, exist_ok=True)
        day1_df.to_parquet(p, index=False)
        bld._save_checkpoint(
            root_b, {"version": 1, "days": {_DAY1.isoformat(): "ok"}, "errors": {}}
        )

        sess_b = _session_serving({_DAY2: _udiff_zip(_DAY2.isoformat())})
        bld.run_build(
            _DAY1, _DAY2, root=root_b, raw_root=raw_b, _session=sess_b, **kwargs
        )

        pa = (
            store_mod.read_prices_adjusted(root=root_a)
            .sort_values("date")
            .reset_index(drop=True)
        )
        pb = (
            store_mod.read_prices_adjusted(root=root_b)
            .sort_values("date")
            .reset_index(drop=True)
        )
        pd.testing.assert_frame_equal(pa, pb)


class TestErrorHandling:
    """Per-day errors are recorded and skipped; the run completes on remaining days."""

    def test_download_error_skipped_not_fatal(self, tmp_path):
        # Day1 ok, Day2 returns a non-ZIP 200 (bad body — NSE block page), Day3 ok.
        sess = _session_serving(
            {
                _DAY1: _udiff_zip(_DAY1.isoformat()),
                _DAY2: b"<html>Access denied</html>",  # treated as error by download_day
                _DAY3: _udiff_zip(_DAY3.isoformat()),
            }
        )
        report = bld.run_build(
            _DAY1,
            _DAY3,
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _session=sess,
            _ca_records=[],
        )

        assert report.days_ok == 2, report
        assert report.days_error == 1, report
        assert len(report.error_details) == 1

        prices = store_mod.read_prices_adjusted(root=tmp_path / "store")
        dates = set(prices["date"].dt.date)
        assert _DAY1 in dates
        assert _DAY2 not in dates  # errored day must not appear
        assert _DAY3 in dates

    def test_404_recorded_as_missing_not_error(self, tmp_path):
        """Both-format 404 is a holiday / not-yet-published — recorded as missing."""
        # Day2 returns 404 for both legacy and UDiFF formats.
        sess = _session_serving(
            {
                _DAY1: _udiff_zip(_DAY1.isoformat()),
                # Day2 not in the dict → handler returns 404
                _DAY3: _udiff_zip(_DAY3.isoformat()),
            }
        )
        report = bld.run_build(
            _DAY1,
            _DAY3,
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _session=sess,
            _ca_records=[],
        )

        assert report.days_missing == 1
        assert report.days_error == 0
        assert report.days_ok == 2

        # Checkpoint must record Day2 as "missing".
        cp = bld._load_checkpoint(tmp_path / "store")
        assert cp["days"][_DAY2.isoformat()] == "missing"

    def test_error_detail_written_to_checkpoint(self, tmp_path):
        # Day1 has a non-ZIP body → error recorded with detail.
        sess = _session_serving({_DAY1: b"not a zip at all"})
        bld.run_build(
            _DAY1,
            _DAY1,
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _session=sess,
            _ca_records=[],
        )

        cp = bld._load_checkpoint(tmp_path / "store")
        assert cp["days"][_DAY1.isoformat()] == "error"
        assert _DAY1.isoformat() in cp["errors"]


class TestZeroRowCoverageGuard:
    """T06.0 (§7): a downloaded-but-zero-row day must NOT claim coverage.

    The §7 over-claim: ``.build_checkpoint.json`` marked a date ``ok`` while
    ``prices_adjusted`` stored no rows for it (a not-yet-final EOD file that
    parses to zero in-scope EQ rows). Such a day must be marked ``empty``
    (provisional, re-attempted next run), never ``ok``.
    """

    def _zero_row_zip(self, trad_dt: str) -> bytes:
        # Valid UDiFF zip whose only row is an out-of-scope series (BE) → parses
        # to zero in-scope EQ rows (simulates a placeholder / not-yet-final file).
        csv = (
            _UDIFF_HEADER
            + "\n"
            + _udiff_row(TradDt=trad_dt, BizDt=trad_dt, SctySrs="BE")
            + "\n"
        )
        fn = f"BhavCopy_NSE_CM_0_0_0_{trad_dt.replace('-', '')}_F_0000.csv"
        return _zip(csv, fn)

    def test_zero_row_day_marked_empty_not_ok(self, tmp_path):
        sess = _session_serving(
            {
                _DAY1: _udiff_zip(_DAY1.isoformat()),
                _DAY2: self._zero_row_zip(_DAY2.isoformat()),  # downloads, 0 EQ rows
            }
        )
        report = bld.run_build(
            _DAY1,
            _DAY2,
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _session=sess,
            _ca_records=[],
        )

        # Day2 stored nothing → must not be counted as covered.
        assert report.days_ok == 1, report
        assert report.days_empty == 1, report
        assert report.days_error == 0, report

        cp = bld._load_checkpoint(tmp_path / "store")
        assert cp["days"][_DAY2.isoformat()] == "empty"
        assert cp["days"][_DAY2.isoformat()] != "ok"  # the §7 over-claim, guarded

        prices = store_mod.read_prices_adjusted(root=tmp_path / "store")
        assert _DAY2 not in set(prices["date"].dt.date)

    def test_empty_day_stays_empty_and_not_re_counted_on_resume(self, tmp_path):
        """Idempotency: an 'empty' day is terminal-on-resume (like 'missing') — a
        second run does not silently flip it to 'ok' nor double-count it."""
        root = tmp_path / "store"
        kwargs = dict(root=root, raw_root=tmp_path / "raw", sleep=_noop, _ca_records=[])

        sess1 = _session_serving(
            {
                _DAY1: _udiff_zip(_DAY1.isoformat()),
                _DAY2: self._zero_row_zip(_DAY2.isoformat()),
            }
        )
        r1 = bld.run_build(_DAY1, _DAY2, _session=sess1, **kwargs)
        assert (r1.days_ok, r1.days_empty) == (1, 1)

        # Second run: everything cached → no HTTP calls; counts unchanged; Day2 still
        # 'empty' (never promoted to coverage).
        sess2 = FakeSession(lambda url: FakeResp(500, b""))  # must not be called
        r2 = bld.run_build(_DAY1, _DAY2, _session=sess2, **kwargs)
        assert sess2.calls == [], f"unexpected HTTP calls: {sess2.calls}"
        assert (r2.days_ok, r2.days_empty) == (1, 1)

        cp = bld._load_checkpoint(root)
        assert cp["days"][_DAY2.isoformat()] == "empty"


class TestIdempotency:
    """Running twice over the same range produces identical output (no duplicates)."""

    def test_run_twice_no_duplicates(self, tmp_path):
        sess = _session_serving(
            {
                _DAY1: _udiff_zip(_DAY1.isoformat()),
                _DAY2: _udiff_zip(_DAY2.isoformat()),
            }
        )
        kwargs = dict(
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _ca_records=[],
        )

        r1 = bld.run_build(_DAY1, _DAY2, _session=sess, **kwargs)
        # Second run uses a fresh session (no URLs served — all should come from cache).
        r2 = bld.run_build(
            _DAY1,
            _DAY2,
            _session=FakeSession(lambda url: FakeResp(500, b"")),  # must not be called
            **kwargs,
        )

        assert r1.rows_written == r2.rows_written
        prices = store_mod.read_prices_adjusted(root=tmp_path / "store")
        assert len(prices) == r1.rows_written  # no row duplication

    def test_second_run_zero_network_calls(self, tmp_path):
        """All days cached → second run does no HTTP calls (idempotency)."""
        sess1 = _session_serving(
            {
                _DAY1: _udiff_zip(_DAY1.isoformat()),
                _DAY2: _udiff_zip(_DAY2.isoformat()),
            }
        )
        kwargs = dict(
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _ca_records=[],
        )
        bld.run_build(_DAY1, _DAY2, _session=sess1, **kwargs)

        sess2 = FakeSession(lambda url: FakeResp(500, b""))
        bld.run_build(_DAY1, _DAY2, _session=sess2, **kwargs)

        assert sess2.calls == [], f"unexpected HTTP calls: {sess2.calls}"


class TestWeekends:
    """Weekends are skipped; they do not appear in the checkpoint or output."""

    def test_weekend_between_trading_days_skipped(self, tmp_path):
        # 2024-07-12 Fri, 2024-07-13 Sat, 2024-07-14 Sun, 2024-07-15 Mon.
        fri = date(2024, 7, 12)
        mon = date(2024, 7, 15)

        sess = _session_serving(
            {fri: _udiff_zip(fri.isoformat()), mon: _udiff_zip(mon.isoformat())}
        )
        report = bld.run_build(
            fri,
            mon,
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _session=sess,
            _ca_records=[],
        )

        assert report.days_ok == 2
        assert report.days_missing == 0

        cp = bld._load_checkpoint(tmp_path / "store")
        assert date(2024, 7, 13).isoformat() not in cp["days"]
        assert date(2024, 7, 14).isoformat() not in cp["days"]


class TestEdgeCases:
    """Boundary and trivial-input cases."""

    def test_start_after_end_raises(self, tmp_path):
        with pytest.raises(ValueError, match="before start"):
            bld.run_build(_DAY2, _DAY1, root=tmp_path)

    def test_single_day_run(self, tmp_path):
        sess = _session_serving({_DAY1: _udiff_zip(_DAY1.isoformat())})
        report = bld.run_build(
            _DAY1,
            _DAY1,
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _session=sess,
            _ca_records=[],
        )
        assert report.days_ok == 1
        assert report.rows_written == 1

    def test_all_missing_range(self, tmp_path):
        """All 404s → nothing stored but no crash."""
        sess = FakeSession(lambda url: FakeResp(404, b""))
        report = bld.run_build(
            _DAY1,
            _DAY2,
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _session=sess,
            _ca_records=[],
        )
        assert report.days_missing == 2
        assert report.rows_written == 0

    def test_report_summary_string(self, tmp_path):
        sess = _session_serving({_DAY1: _udiff_zip(_DAY1.isoformat())})
        report = bld.run_build(
            _DAY1,
            _DAY1,
            root=tmp_path / "store",
            raw_root=tmp_path / "raw",
            sleep=_noop,
            _session=sess,
            _ca_records=[],
        )
        s = report.summary()
        assert "2024-07-08" in s
        assert "1 days ok" in s
