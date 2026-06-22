"""P11.0 — daily incremental-append tests (specs/v3/11 §5a, §5b, §5d).

Offline only — fake HTTP sessions + injected ``_ca_records`` (no network, no sleep).

Covers:
  * §5b: a daily incremental append (re-running the full-history build off the
    checkpoint) reproduces a from-scratch full rebuild **byte-for-byte**, including
    across an injected split whose retroactive back-adjustment rewrites prior history.
  * §5d: the post-append reconciliation guard flags CA-explained drift as expected
    and HALTS on unexplained retroactive drift (no logged CA).
"""

import io
import zipfile
from datetime import date

import pandas as pd
import pytest

from app.data.bhavcopy import incremental as inc
from app.data.bhavcopy import store as store_mod

# --------------------------------------------------------------------------- #
# Minimal UDiFF fixture helpers (mirrors tests/data/test_bhavcopy_build.py)    #
# --------------------------------------------------------------------------- #
_HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,"
    "XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,"
    "LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,"
    "ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,"
    "Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4"
)
_COLS = _HEADER.split(",")
_ISIN = "INE002A01018"


def _row(trad_dt: str, close: float) -> str:
    d = {c: "" for c in _COLS}
    d.update(
        TradDt=trad_dt,
        BizDt=trad_dt,
        Sgmt="CM",
        Src="NSE",
        FinInstrmTp="STK",
        FinInstrmId="1",
        ISIN=_ISIN,
        TckrSymb="RELIANCE",
        SctySrs="EQ",
        FinInstrmNm="RELIANCE INDUSTRIES LTD",
        OpnPric=str(close * 0.99),
        HghPric=str(close * 1.01),
        LwPric=str(close * 0.98),
        ClsPric=str(close),
        LastPric=str(close),
        PrvsClsgPric=str(close),
        SttlmPric=str(close),
        TtlTradgVol="1000000",
        TtlTrfVal=str(round(close * 1_000_000, 2)),
        TtlNbOfTxsExctd="500",
        SsnId="F1",
        NewBrdLotQty="1",
    )
    return ",".join(d[c] for c in _COLS)


def _zip_for(trad_dt: str, close: float) -> bytes:
    csv = _HEADER + "\n" + _row(trad_dt, close) + "\n"
    fn = f"BhavCopy_NSE_CM_0_0_0_{trad_dt.replace('-', '')}_F_0000.csv"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(fn, csv.encode())
    return buf.getvalue()


class _Resp:
    def __init__(self, status, content=b""):
        self.status_code = status
        self.content = content


class _Session:
    """Serves zip bytes per date token in the URL; records calls; 404 otherwise."""

    def __init__(self, days):
        self._days = days
        self.calls = []

    def get(self, url, timeout=None, **kw):
        self.calls.append(url)
        for d, payload in self._days.items():
            if d.strftime("%Y%m%d") in url:
                return _Resp(200, payload)
        return _Resp(404, b"")

    def close(self):
        pass


def _noop(*_):
    pass


_D1 = date(2024, 7, 8)  # Mon
_D2 = date(2024, 7, 9)  # Tue
_D3 = date(2024, 7, 10)  # Wed

# 1:5 face-value split, ex-date D3 → adj_factor 0.2 on all rows < D3 once D3 exists.
_SPLIT_CA = {
    "isin": _ISIN,
    "symbol": "RELIANCE",
    "series": "EQ",
    "faceVal": "10",
    "subject": "Face Value Split From Rs 10/- To Rs 2/-",
    "exDate": "10-Jul-2024",
    "recDate": "10-Jul-2024",
    "bcStartDate": "-",
    "bcEndDate": "-",
    "ndStartDate": "-",
    "comp": "Reliance Industries Limited",
    "ndEndDate": "-",
    "caBroadcastDate": None,
}


def _read_sorted(root):
    return (
        store_mod.read_prices_adjusted(root=root)
        .sort_values(["isin", "date"])
        .reset_index(drop=True)
    )


# --------------------------------------------------------------------------- #
# §5b — incremental append == full rebuild, byte-for-byte (across a split)     #
# --------------------------------------------------------------------------- #
class TestIncrementalEqualsFullRebuild:
    def test_split_injection_incremental_matches_full_rebuild(self, tmp_path):
        inc_root = tmp_path / "inc"
        inc_raw = tmp_path / "inc_raw"
        kw = dict(root=inc_root, raw_root=inc_raw, sleep=_noop)

        # Day 1: first append (no prior history, no CA yet).
        inc.incremental_append(
            _D1,
            _session=_Session({_D1: _zip_for("2024-07-08", 2840.0)}),
            _ca_records=[],
            **kw,
        )
        # Day 2: append D2; checkpoint anchors inception back to D1 (D1 not re-fetched).
        sess2 = _Session({_D2: _zip_for("2024-07-09", 2860.0)})
        inc.incremental_append(_D2, _session=sess2, _ca_records=[], **kw)
        assert not any(_D1.strftime("%Y%m%d") in u for u in sess2.calls)

        # Day 3: the split publishes on its ex-date → retroactively rescales D1+D2.
        report, rec = inc.incremental_append(
            _D3,
            _session=_Session({_D3: _zip_for("2024-07-10", 580.0)}),
            _ca_records=[_SPLIT_CA],
            **kw,
        )
        assert report.ca_events == 1
        # §5d: the only drifted ISIN is the split name, and it IS CA-explained.
        assert rec is not None and rec.ok
        assert rec.ca_explained_isins == [_ISIN]
        assert rec.unexplained_isins == []

        # Full from-scratch rebuild over the whole range with the same CA.
        full_root = tmp_path / "full"
        from app.data.bhavcopy import build as build_mod

        build_mod.run_build(
            _D1,
            _D3,
            root=full_root,
            raw_root=tmp_path / "full_raw",
            sleep=_noop,
            _session=_Session(
                {
                    _D1: _zip_for("2024-07-08", 2840.0),
                    _D2: _zip_for("2024-07-09", 2860.0),
                    _D3: _zip_for("2024-07-10", 580.0),
                }
            ),
            _ca_records=[_SPLIT_CA],
        )

        pd.testing.assert_frame_equal(_read_sorted(inc_root), _read_sorted(full_root))

    def test_pre_split_history_is_back_adjusted_after_append(self, tmp_path):
        """The split rewrites D1's adjusted close to 0.2× raw — the retroactive
        rewrite the §5e portfolio reconciliation exists to absorb."""
        root, raw = tmp_path / "s", tmp_path / "r"
        kw = dict(root=root, raw_root=raw, sleep=_noop)
        inc.incremental_append(
            _D1,
            _session=_Session({_D1: _zip_for("2024-07-08", 2840.0)}),
            _ca_records=[],
            **kw,
        )
        inc.incremental_append(
            _D3,
            _session=_Session({_D3: _zip_for("2024-07-10", 580.0)}),
            _ca_records=[_SPLIT_CA],
            **kw,
        )
        prices = _read_sorted(root)
        d1 = prices[prices["date"] == pd.Timestamp(_D1)].iloc[0]
        assert abs(d1["adj_factor"] - 0.2) < 1e-9
        assert abs(d1["close"] - d1["close_raw"] * 0.2) < 1e-6


# --------------------------------------------------------------------------- #
# §5d — reconciliation guard unit behaviour                                    #
# --------------------------------------------------------------------------- #
class TestReconciliationGuard:
    def _frame(self, isin, close, factor=1.0):
        return pd.DataFrame(
            {
                "isin": [isin],
                "date": [pd.Timestamp(_D1)],
                "adj_factor": [factor],
                "close": [close],
            }
        )

    def test_no_drift_is_ok(self):
        prior = self._frame("INEAAA", 100.0)
        rep = inc.reconcile_appended_series(prior, prior.copy(), set())
        assert rep.ok and rep.drifted_isins == []

    def test_ca_explained_drift_is_ok(self):
        prior = self._frame("INEAAA", 100.0, 1.0)
        new = self._frame("INEAAA", 50.0, 0.5)  # split-rescaled
        rep = inc.reconcile_appended_series(prior, new, {"INEAAA"})
        assert rep.ok
        assert rep.ca_explained_isins == ["INEAAA"]

    def test_unexplained_drift_is_flagged(self):
        prior = self._frame("INEAAA", 100.0, 1.0)
        new = self._frame("INEAAA", 50.0, 0.5)  # drift with NO logged CA
        rep = inc.reconcile_appended_series(prior, new, set())
        assert not rep.ok
        assert rep.unexplained_isins == ["INEAAA"]

    def test_incremental_halts_on_unexplained_drift(self, tmp_path, monkeypatch):
        """If a non-CA ISIN's history silently drifts, the append must halt (§8)."""
        root, raw = tmp_path / "s", tmp_path / "r"
        kw = dict(root=root, raw_root=raw, sleep=_noop)
        inc.incremental_append(
            _D1,
            _session=_Session({_D1: _zip_for("2024-07-08", 2840.0)}),
            _ca_records=[],
            **kw,
        )
        # Force the guard to see drift with an empty CA set → unexplained.
        real = inc.reconcile_appended_series
        monkeypatch.setattr(
            inc,
            "reconcile_appended_series",
            lambda prior, new, ca, **k: real(
                prior, new.assign(close=new["close"] * 0.5), set()
            ),
        )
        with pytest.raises(inc.IncrementalReconciliationError):
            inc.incremental_append(
                _D2,
                _session=_Session({_D2: _zip_for("2024-07-09", 2860.0)}),
                _ca_records=[],
                **kw,
            )
