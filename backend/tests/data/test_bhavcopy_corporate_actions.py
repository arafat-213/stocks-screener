"""T4 corporate-actions tests.

Offline only — in-memory record dicts and a fake HTTP session, no network
(CLAUDE.md Rule 4). Sample records use the T0-verified CA feed layout
(01_DATA_LAYER.md §4), including the verbatim GENSOL bonus record.

Covers:
  * subject free-text parse → split / bonus / dividend with correct values.
  * unparseable / keyword-less / missing-ISIN / bad-ex-date records flagged
    (surfaced in `unmatched`, never dropped silently — Rule 12).
  * cumulative split factor (hand-checked 1:5) and bonus factor (hand-checked 2:1).
  * compounding of multiple events.
  * TR factor: dividend reinvestment, and TR factor ≤ split/bonus factor
    everywhere (sets up T8 §7.5).
  * fetch builds the right request and unwraps the JSON list (fake session).
"""

import pandas as pd
import pytest

from app.data.bhavcopy import corporate_actions as ca


# --------------------------------------------------------------------------- #
# Record fixtures (T0-verified feed layout)                                    #
# --------------------------------------------------------------------------- #
def _rec(**overrides) -> dict:
    base = {
        "symbol": "DUMMY",
        "series": "EQ",
        "ind": "-",
        "faceVal": "10",
        "subject": "",
        "exDate": "17-Oct-2023",
        "recDate": "17-Oct-2023",
        "bcStartDate": "-",
        "bcEndDate": "-",
        "ndStartDate": "-",
        "comp": "Dummy Limited",
        "isin": "INE000A00000",
        "ndEndDate": "-",
        "caBroadcastDate": None,
    }
    base.update(overrides)
    return base


# Verbatim GENSOL bonus record from 01_DATA_LAYER.md §4.
_GENSOL = {
    "symbol": "GENSOL",
    "series": "EQ",
    "ind": "-",
    "faceVal": "10",
    "subject": "Bonus 2:1",
    "exDate": "17-Oct-2023",
    "recDate": "17-Oct-2023",
    "bcStartDate": "-",
    "bcEndDate": "-",
    "ndStartDate": "-",
    "comp": "Gensol Engineering Limited",
    "isin": "INE06H201014",
    "ndEndDate": "-",
    "caBroadcastDate": None,
}


# --------------------------------------------------------------------------- #
# Parse                                                                        #
# --------------------------------------------------------------------------- #
def test_parse_classifies_and_values():
    recs = [
        _GENSOL,
        _rec(
            isin="INE111A01011",
            symbol="SPL",
            subject="Face Value Split From Rs 10/- To Rs 1/-",
        ),
        _rec(isin="INE222A01022", symbol="DIV", subject="Dividend - Rs 5 Per Share"),
    ]
    res = ca.parse_corporate_actions(recs)
    assert res.unmatched.empty
    ev = res.events.set_index("isin")

    # Bonus 2:1 → price multiplier b/(a+b) = 1/3.
    assert ev.loc["INE06H201014", "type"] == ca.BONUS
    assert ev.loc["INE06H201014", "ratio"] == pytest.approx(1 / 3)

    # Split FV 10→1 → multiplier new/old = 0.1.
    assert ev.loc["INE111A01011", "type"] == ca.SPLIT
    assert ev.loc["INE111A01011", "ratio"] == pytest.approx(0.1)

    # Dividend Rs 5 → ₹5/share.
    assert ev.loc["INE222A01022", "type"] == ca.DIVIDEND
    assert ev.loc["INE222A01022", "dividend"] == pytest.approx(5.0)


def test_dividend_ignores_face_value_mention():
    # "of Rs 10" is the face value, not the payout — must not be summed.
    res = ca.parse_corporate_actions(
        [_rec(subject="Dividend Rs 2.50 Per Equity Share of Rs 10")]
    )
    assert res.unmatched.empty
    assert res.events.iloc[0]["dividend"] == pytest.approx(2.50)


def test_dividend_percentage_fallback_uses_face_value():
    res = ca.parse_corporate_actions(
        [_rec(faceVal="10", subject="Dividend - 50% on face value")]
    )
    assert res.events.iloc[0]["dividend"] == pytest.approx(5.0)  # 50% × 10


def test_unmatched_surfaced_not_dropped():
    recs = [
        _rec(subject="Annual General Meeting"),  # no action keyword
        _rec(subject="Dividend declared"),  # dividend but no amount / %
        _rec(isin="", subject="Bonus 1:1"),  # missing join key
        _rec(exDate="-", subject="Bonus 1:1"),  # unparseable ex-date
    ]
    res = ca.parse_corporate_actions(recs)
    assert res.events.empty
    assert len(res.unmatched) == 4
    reasons = " ".join(res.unmatched["reason"])
    assert "keyword" in reasons
    assert "could not parse" in reasons
    assert "missing isin" in reasons
    assert "ex-date" in reasons


def test_parse_dedupes_and_sorts():
    recs = [
        _rec(subject="Bonus 1:1", exDate="10-Jan-2022"),
        _rec(subject="Bonus 1:1", exDate="10-Jan-2022"),  # exact dup
        _rec(subject="Face Value Split From Rs 10 To Rs 2", exDate="01-Jan-2020"),
    ]
    res = ca.parse_corporate_actions(recs)
    assert len(res.events) == 2  # dup collapsed
    # sorted by (isin, ex_date) → split (2020) before bonus (2022).
    assert list(res.events["type"]) == [ca.SPLIT, ca.BONUS]


# --------------------------------------------------------------------------- #
# Split / bonus cumulative factor                                             #
# --------------------------------------------------------------------------- #
def test_split_factor_series_hand_checked():
    # 1:5 split, FV 10→2 → multiplier 0.2, ex-date 2020-03-10.
    events = ca.parse_corporate_actions(
        [_rec(subject="Face Value Split From Rs 10 To Rs 2", exDate="10-Mar-2020")]
    ).events
    dates = pd.to_datetime(["2020-03-06", "2020-03-09", "2020-03-10", "2020-03-11"])
    f = ca.split_bonus_factor_series(events, dates)
    # strictly before ex-date → 0.2; on/after ex-date → 1.0.
    assert f.loc["2020-03-06"] == pytest.approx(0.2)
    assert f.loc["2020-03-09"] == pytest.approx(0.2)
    assert f.loc["2020-03-10"] == pytest.approx(1.0)
    assert f.loc["2020-03-11"] == pytest.approx(1.0)


def test_bonus_factor_series_hand_checked():
    events = ca.parse_corporate_actions([_GENSOL]).events  # Bonus 2:1, 2023-10-17
    dates = pd.to_datetime(["2023-10-16", "2023-10-17", "2023-10-18"])
    f = ca.split_bonus_factor_series(events, dates)
    assert f.loc["2023-10-16"] == pytest.approx(1 / 3)
    assert f.loc["2023-10-17"] == pytest.approx(1.0)
    assert f.loc["2023-10-18"] == pytest.approx(1.0)


def test_multiple_events_compound():
    # Split 0.2 (2020-03-10) then Bonus 1:1 → 0.5 (2021-06-01).
    events = ca.parse_corporate_actions(
        [
            _rec(subject="Face Value Split From Rs 10 To Rs 2", exDate="10-Mar-2020"),
            _rec(subject="Bonus 1:1", exDate="01-Jun-2021"),
        ]
    ).events
    dates = pd.to_datetime(["2020-01-01", "2020-12-31", "2021-12-31"])
    f = ca.split_bonus_factor_series(events, dates)
    assert f.loc["2020-01-01"] == pytest.approx(0.2 * 0.5)  # before both
    assert f.loc["2020-12-31"] == pytest.approx(0.5)  # after split, before bonus
    assert f.loc["2021-12-31"] == pytest.approx(1.0)  # after both


def test_factor_series_no_events_is_unity():
    empty = ca.parse_corporate_actions([]).events
    dates = pd.to_datetime(["2022-01-01", "2022-06-01"])
    f = ca.split_bonus_factor_series(empty, dates)
    assert (f.values == 1.0).all()


# --------------------------------------------------------------------------- #
# TR factor (dividends)                                                        #
# --------------------------------------------------------------------------- #
def test_tr_factor_dividend_reinvestment():
    # Dividend Rs 10, ex-date 2022-06-02; close on prior day (06-01) = 100.
    events = ca.parse_corporate_actions(
        [_rec(subject="Dividend - Rs 10 Per Share", exDate="02-Jun-2022")]
    ).events
    dates = pd.to_datetime(["2022-06-01", "2022-06-02", "2022-06-03"])
    close = [100.0, 92.0, 95.0]
    tr = ca.tr_factor_series(events, dates, close)
    # multiplier 1 - 10/100 = 0.9 applied strictly before ex-date.
    assert tr.loc["2022-06-01"] == pytest.approx(0.9)
    assert tr.loc["2022-06-02"] == pytest.approx(1.0)
    assert tr.loc["2022-06-03"] == pytest.approx(1.0)


def test_tr_factor_le_split_bonus_everywhere():
    # A split and a dividend on the same name: tr_factor must be ≤ adj_factor at
    # every date (dividends only shrink older factors → TR return ≥ price return).
    events = ca.parse_corporate_actions(
        [
            _rec(subject="Face Value Split From Rs 10 To Rs 2", exDate="10-Mar-2021"),
            _rec(subject="Dividend - Rs 4 Per Share", exDate="05-Aug-2021"),
        ]
    ).events
    dates = pd.date_range("2021-01-01", "2021-12-31", freq="B")
    close = pd.Series(100.0, index=dates)
    adj = ca.split_bonus_factor_series(events, dates)
    tr = ca.tr_factor_series(events, dates, close)
    assert (tr.values <= adj.values + 1e-12).all()
    assert (tr.values < adj.values - 1e-9).any()  # dividend actually moved it


def test_tr_factor_skips_dividend_without_prior_close():
    # Dividend on the very first date → no cum close → skipped, not a crash/NaN.
    events = ca.parse_corporate_actions(
        [_rec(subject="Dividend - Rs 10 Per Share", exDate="01-Jun-2022")]
    ).events
    dates = pd.to_datetime(["2022-06-01", "2022-06-02"])
    tr = ca.tr_factor_series(events, dates, [100.0, 100.0])
    assert (tr.values == 1.0).all()


# --------------------------------------------------------------------------- #
# Fetch (fake session, no network)                                            #
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return _FakeResp(self._payload)


def test_fetch_builds_request_and_returns_list():
    sess = _FakeSession([_GENSOL])
    out = ca.fetch_corporate_actions(
        "2023-01-01", "2023-12-31", session=sess, sleep=lambda _s: None
    )
    assert out == [_GENSOL]
    call = sess.calls[0]
    assert call["url"] == ca.CA_API_URL
    assert call["params"]["index"] == "equities"
    assert call["params"]["from_date"] == "01-01-2023"  # dd-mm-yyyy
    assert call["params"]["to_date"] == "31-12-2023"


def test_fetch_unwraps_data_envelope():
    sess = _FakeSession({"data": [_GENSOL]})
    out = ca.fetch_corporate_actions(
        "2023-01-01", "2023-12-31", session=sess, sleep=lambda _s: None
    )
    assert out == [_GENSOL]
