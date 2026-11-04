"""Write the Tableau extract files (tableau/data/*.csv) from the governed metrics.

lines.csv      one row per line item: delivery facts (on-time, value late) by country, route, mode, vendor, year
shipments.csv  one row per priced shipment: freight cost, weight, size band
kpis.csv       one row of governed headline numbers (also used to reconcile the Tableau view)
vendors.csv    direct-ship vendor scorecard (20+ line items)
mode_shift.csv mode-shift scenario saving by country (default thresholds)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shipiq import metrics as m  # noqa: E402
from shipiq import tools as t  # noqa: E402

OUT = ROOT / "tableau" / "data"
GEO = {"Congo, DRC": "Democratic Republic of the Congo"}  # names Tableau's geocoder recognises
SHORT_ROUTE = {"From regional warehouse (RDC)": "Warehouse (RDC)", "Direct from vendor": "Direct from vendor"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = m.lines()
    w = m.worklist(n=12)
    top = set(zip(w.country, w.route))
    lines = pd.DataFrame({
        "line_id": d.line_id, "shipment_id": d.shipment_id, "country": d.country.replace(GEO), "route": d.route.map(SHORT_ROUTE),
        "mode": d["mode"], "vendor": d.vendor, "product_group": d.product_group, "year": d.year.astype(int),
        "scheduled_date": d.scheduled.dt.strftime("%Y-%m-%d"), "lines": 1, "late": d.late.astype(int),
        "days_late": d.days_late.clip(lower=0), "value_usd": d.value_usd.round(2), "late_value_usd": (d.value_usd * d.late).round(2),
        "lane": d.country.replace(GEO) + " · " + d.route.map(SHORT_ROUTE),
        "top_lane": ["Top 12" if (c, r) in top else "Other" for c, r in zip(d.country, d.route)]})
    lines.to_csv(OUT / "lines.csv", index=False)

    p = m.priced()
    p["band"] = pd.cut(p.weight_kg, m.WEIGHT_BANDS, labels=m.BAND_LABELS, right=False).astype(str)
    p["band_order"] = p.band.map({b: i + 1 for i, b in enumerate(m.BAND_LABELS)})
    ships = pd.DataFrame({"shipment_id": p.shipment_id, "country": p.country.replace(GEO), "route": p.route.map(SHORT_ROUTE),
                          "mode": p["mode"], "weight_kg": p.weight_kg, "freight_usd": p.freight_usd.round(2), "value_usd": p.value_usd.round(2),
                          "weight_band": p.band, "band_order": p.band_order, "shipments": 1})
    ships.to_csv(OUT / "shipments.csv", index=False)

    n, r, s = t.network_summary(), t.route_comparison(), t.mode_shift_scenario()
    k = {**{f"net_{a}": b for a, b in n.items() if isinstance(b, (int, float))},
         **{f"route_{a}": b for a, b in r.items() if isinstance(b, (int, float))},
         **{f"shift_{a}": b for a, b in s.items() if isinstance(b, (int, float))}}
    pd.DataFrame([k]).to_csv(OUT / "kpis.csv", index=False)

    v = m.vendor_scorecard()
    pd.DataFrame({"vendor": v.vendor, "lines": v.lines, "late_lines": v.late_lines.astype(int), "late_rate": v.late_rate.round(4),
                  "value_musd": (v.value_usd / 1e6).round(2), "median_days_late": v.median_days_late,
                  "countries": v.countries}).to_csv(OUT / "vendors.csv", index=False)

    ms = m.mode_shift()["by_country"]
    pd.DataFrame({"country": ms.country.replace(GEO), "shipments": ms.shipments, "air_freight_musd": (ms.air_freight_usd / 1e6).round(3),
                  "saving_musd": (ms.saving_usd / 1e6).round(3)}).to_csv(OUT / "mode_shift.csv", index=False)

    # reconcile: recompute the headline numbers from the exported files exactly as the Tableau calculations do
    L, S = pd.read_csv(OUT / "lines.csv"), pd.read_csv(OUT / "shipments.csv")
    checks = {
        "on_time_pct": (round((1 - L.late.sum() / L.lines.sum()) * 100, 1), n["on_time_pct"]),
        "late_value_musd": (round(L.late_value_usd.sum() / 1e6, 1), n["late_value_musd"]),
        "warehouse_late_pct": (round(L[L.route == "Warehouse (RDC)"].late.mean() * 100, 1), r["warehouse_late_pct"]),
        "direct_late_pct": (round(L[L.route == "Direct from vendor"].late.mean() * 100, 1), r["direct_late_pct"]),
        "air_share_of_freight_pct": (round(S[S["mode"] == "Air"].freight_usd.sum() / S.freight_usd.sum() * 100, 1), n["air_share_of_freight_pct"]),
        "air_usd_per_kg": (round(S[S["mode"] == "Air"].freight_usd.sum() / S[S["mode"] == "Air"].weight_kg.sum(), 2), n["air_usd_per_kg"]),
    }
    bad = {a: b for a, b in checks.items() if not np.isclose(b[0], b[1])}
    for a, (got, exp) in checks.items():
        print(f"{a:28s} extract {got:>8}  governed {exp:>8}  {'OK' if a not in bad else 'MISMATCH'}")
    if bad:
        raise SystemExit(f"reconciliation failed: {bad}")
    print(f"wrote {len(lines):,} lines, {len(ships):,} shipments, {len(v)} vendors to {OUT}")


if __name__ == "__main__":
    main()
