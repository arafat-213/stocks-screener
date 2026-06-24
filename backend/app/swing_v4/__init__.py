"""swing_v4 — daily event-driven swing engine (spec v4/02).

Additive-only package. Reads the bhavcopy adjusted store, market_internals,
India VIX and the Nifty 50 price series; imports the v2 costs / accounting
primitives without modifying them. Writes nothing into the data layer and
cannot move an S3 / `11` / FINAL_OOS number (v4/02 §8).

V4.0a (this milestone): indicators + regime + signal precompute.
"""
