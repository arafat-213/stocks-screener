"""P11.0 — §5e corporate-action portfolio-state reconciliation tests (v3/11).

A held position whose ISIN splits must be rescaled into the new back-adjustment
anchor BEFORE the daily catastrophic-stop check, or a clean split reads as a crash
and falsely trips the stop. These tests prove the three §5e gate conditions:

  (a) no catastrophic stop fires from the split alone (after reconcile);
  (b) the position value (shares × cost_basis) is invariant across the rescale;
  (c) the reconciled live cost_basis byte-matches what a from-scratch shadow
      backtest derives in the new anchor.
"""

import pytest

from app.paper_v2 import ca_reconcile as cr

# A held name entered at raw close ₹1000 when it was the anchor (adj_factor = 1.0),
# then a clean 2:1 split (ratio 0.5) on a later day moves the anchor.
_RAW_ENTRY_CLOSE = 1000.0
_F_OLD = 1.0  # entry-day factor in the old anchor (entry was the latest date then)
_F_NEW = 0.5  # entry-day factor after the split re-anchors the series
_SHARES = 10.0
_STOP_PCT = 25.0


def _old_cost_basis() -> float:
    # Adjusted-space cost basis recorded live, in the OLD anchor.
    return _RAW_ENTRY_CLOSE * _F_OLD


def _shadow_cost_basis() -> float:
    # A from-scratch backtest re-derives the basis in the CURRENT (new) anchor:
    # adjusted entry close = raw entry close × new factor. Derived independently
    # from the reconcile path, so the (c) assertion is not a tautology.
    return _RAW_ENTRY_CLOSE * _F_NEW


def _new_adjusted_close(raw_close: float) -> float:
    # The freshly re-adjusted close for `raw_close` in the new anchor.
    return raw_close * _F_NEW


class TestReconcilePosition:
    def test_a_no_false_stop_after_reconcile(self):
        """Price unchanged (still ₹1000 raw) — only the split moved the anchor."""
        old_basis = _old_cost_basis()
        new_close = _new_adjusted_close(_RAW_ENTRY_CLOSE)  # 500, purely from the split

        # Pre-reconcile: the daily stop would FALSELY fire (500 ≤ 1000×0.75 = 750).
        assert cr.would_stop_fire(new_close, old_basis, _STOP_PCT) is True

        st = cr.reconcile_position(old_basis, _SHARES, _F_OLD, _F_NEW)

        # Post-reconcile: basis is in the same anchor as close ⇒ no stop (500 > 375).
        assert cr.would_stop_fire(new_close, st.cost_basis, _STOP_PCT) is False
        assert st.rescaled is True
        assert st.factor_ratio == pytest.approx(0.5)

    def test_b_position_value_invariant(self):
        old_basis = _old_cost_basis()
        st = cr.reconcile_position(old_basis, _SHARES, _F_OLD, _F_NEW)
        assert st.shares * st.cost_basis == pytest.approx(_SHARES * old_basis)
        assert st.shares == pytest.approx(_SHARES / 0.5)  # 2:1 split doubles shares

    def test_c_reconciled_basis_matches_shadow_backtest(self):
        st = cr.reconcile_position(_old_cost_basis(), _SHARES, _F_OLD, _F_NEW)
        assert st.cost_basis == _shadow_cost_basis()

    def test_no_ca_today_is_a_noop(self):
        old_basis = _old_cost_basis()
        st = cr.reconcile_position(old_basis, _SHARES, _F_OLD, _F_OLD)
        assert st.rescaled is False
        assert st.cost_basis == old_basis
        assert st.shares == _SHARES
        assert st.factor_ratio == 1.0

    @pytest.mark.parametrize("old,new", [(0.0, 0.5), (1.0, 0.0), (-1.0, 0.5)])
    def test_non_positive_factor_halts(self, old, new):
        with pytest.raises(cr.UnreconcilableCorporateActionError):
            cr.reconcile_position(1000.0, 10.0, old, new)
