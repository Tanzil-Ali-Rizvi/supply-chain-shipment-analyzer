import pandas as pd

from shipiq import metrics as m
from shipiq.data import q


def test_source_grain_and_shipments():
    k = m.kpis()
    assert k["lines"] == 10324 and k["shipments"] == 7030 and k["countries"] == 43
    assert round(k["value_usd"] / 1e6, 1) == 1627.6


def test_freight_is_recorded_once_per_shipment():
    per = q("SELECT shipment_id, count(freight_usd) AS n FROM lines GROUP BY shipment_id")
    assert per.n.max() == 1
    shared = q("SELECT count(*) AS n FROM lines WHERE freight_status = 'on another line'").n[0]
    assert shared == 2445


def test_on_time_definition():
    d = m.lines()
    assert ((d.days_late > 0) == d.late).all()
    assert round(m.kpis()["otd_rate"] * 100, 1) == 88.5


def test_route_effect_is_like_for_like_and_significant():
    e = m.route_effect()
    assert e["odds_ratio"] > 5 and e["p_value"] < 0.01
    assert e["strata"] == 127 and e["lines"] == 4836


def test_mode_shift_is_monotonic_and_bounded():
    a = m.mode_shift(1000, 180)
    b = m.mode_shift(2000, 180)
    c = m.mode_shift(1000, 240)
    assert b["eligible_shipments"] <= a["eligible_shipments"] and c["eligible_shipments"] <= a["eligible_shipments"]
    assert 0 < a["saving_usd"] <= a["eligible_air_freight_usd"]
    assert a["eligible_shipments"] == 140


def test_bigger_shipments_cost_less_per_kg():
    b = m.by_weight_band()
    assert b.median_usd_per_kg.is_monotonic_decreasing
    assert len(b) == 5


def test_air_is_the_largest_freight_cost():
    md = m.by_mode().set_index("mode")
    assert md.share_of_freight.idxmax() == "Air"
    assert md.loc["Air", "freight_per_kg"] > 2.5 * md.loc["Ocean", "freight_per_kg"]


def test_vendor_scorecard_threshold():
    v = m.vendor_scorecard()
    assert (v.lines >= m.MIN_VENDOR_LINES).all() and "SCMS from RDC" not in set(v.vendor)


def test_worklist_ranked_by_late_value():
    w = m.worklist(n=10)
    assert w.late_value_usd.is_monotonic_decreasing and isinstance(w, pd.DataFrame)
    assert w.iloc[0].country == "Mozambique"
