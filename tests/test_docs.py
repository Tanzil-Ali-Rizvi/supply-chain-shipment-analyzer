"""The memo must quote the same numbers the metrics compute."""
from pathlib import Path

from shipiq import metrics as m
from shipiq import tools as t

MEMO = (Path(__file__).resolve().parents[1] / "docs" / "findings.md").read_text()


def test_memo_headline_numbers_match_metrics():
    n, r, f, s = t.network_summary(), t.route_comparison(), t.freight_by_mode(), t.mode_shift_scenario()
    c = m.late_value_concentration()
    air = next(x for x in f["modes"] if x["mode"] == "Air")
    for figure in [f"{n['on_time_pct']}%", f"{n['on_time_value_pct']}%", f"${n['late_value_musd']}M", f"${n['commodity_value_musd']:,}M",
                   f"{r['warehouse_late_pct']}%", f"{r['direct_late_pct']}%", f"{r['like_for_like_odds_ratio']}x",
                   f"{r['like_for_like_groups']} groups", f"{r['like_for_like_lines']:,} lines", f"{r['warehouse_worst_year_late_pct']}% late in 2011",
                   f"{r['warehouse_late_pct_2013_2015']}% late", f"{air['share_of_freight_pct']}%", f"${air['usd_per_kg']}/kg",
                   f"{f['small_shipments']:,} shipments under 100 kg", f"${f['small_median_usd_per_kg']}/kg", f"{s['eligible_shipments']} of",
                   f"${s['eligible_air_freight_musd']}M", f"${s['saving_musd']}M", f"{c['warehouse_share'] * 100:.0f}%", f"{c['top_share'] * 100:.0f}%"]:
        assert figure in MEMO, figure
