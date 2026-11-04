"""Governed supply-chain metrics. Every number in the app, memo, Tableau extract and assistant comes from here.

Definitions (docs/kpi_definitions.md):
  on-time        a line item delivered on or before its scheduled delivery date
  OTD            on-time delivery rate = on-time lines / all lines (also value-weighted)
  route          direct from vendor ("Direct Drop") or from a regional distribution centre ("From RDC")
  freight $/kg   shipment freight cost / shipment weight, for shipments with both recorded (priced)
  freight share  shipment freight cost / commodity value of the shipment
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from .data import q

WEIGHT_BANDS = [0, 100, 500, 2000, 10000, np.inf]
BAND_LABELS = ["Under 100 kg", "100-500 kg", "500 kg-2 t", "2-10 t", "Over 10 t"]
MIN_VENDOR_LINES = 20
SHIFT_MIN_KG = 1000          # mode-shift scenario defaults
SHIFT_MIN_PLAN_DAYS = 180    # PO to scheduled delivery; ocean takes a median 174 days from PO to delivery


def lines() -> pd.DataFrame:
    return q("SELECT * FROM lines")


def shipments() -> pd.DataFrame:
    return q("SELECT * FROM shipments")


def priced() -> pd.DataFrame:
    return q("SELECT * FROM shipments WHERE usd_per_kg IS NOT NULL")


# ------------------------------------------------------------------ headline
def kpis() -> dict:
    k = q("""SELECT count(*) AS lines, count(DISTINCT shipment_id) AS shipments, count(DISTINCT country) AS countries,
                    count(DISTINCT vendor) AS vendors, sum(value_usd) AS value_usd, avg(late::INT) AS late_rate,
                    sum(value_usd * late::INT) / sum(value_usd) AS late_value_rate, sum(value_usd * late::INT) AS late_value_usd,
                    sum(late::INT) AS late_lines, median(days_late) FILTER (WHERE late) AS median_days_late,
                    min(year) AS first_year, max(year) AS last_year FROM lines""").iloc[0]
    f = q("""SELECT count(*) AS priced_shipments, sum(freight_usd) AS freight_usd, sum(weight_kg) AS weight_kg
             FROM shipments WHERE usd_per_kg IS NOT NULL""").iloc[0]
    out = {**k.to_dict(), **f.to_dict()}
    out["otd_rate"] = 1 - out["late_rate"]
    out["otd_value_rate"] = 1 - out["late_value_rate"]
    out["freight_per_kg"] = out["freight_usd"] / out["weight_kg"]
    return out


# ------------------------------------------------------------------ delivery
def by_route() -> pd.DataFrame:
    return q("""SELECT route, count(*) AS lines, avg(late::INT) AS late_rate, sum(late::INT) AS late_lines,
                       sum(value_usd) AS value_usd, median(days_late) FILTER (WHERE late) AS median_days_late
                FROM lines GROUP BY route ORDER BY route""")


def by_year_route() -> pd.DataFrame:
    return q("""SELECT year, route, count(*) AS lines, avg(late::INT) AS late_rate FROM lines GROUP BY year, route ORDER BY year, route""")


def by_year() -> pd.DataFrame:
    return q("SELECT year, count(*) AS lines, avg(late::INT) AS late_rate, sum(value_usd) AS value_usd FROM lines GROUP BY year ORDER BY year")


def _cmh(late: np.ndarray, rdc: np.ndarray, strata: np.ndarray) -> float:
    """Mantel-Haenszel odds ratio of lateness, RDC vs direct, pooled across strata."""
    df = pd.DataFrame({"s": strata, "a": rdc & late, "b": rdc & ~late, "c": ~rdc & late, "d": ~rdc & ~late})
    g = df.groupby("s").sum()
    n = g.sum(axis=1)
    return float((g.a * g.d / n).sum() / (g.b * g.c / n).sum())


@lru_cache(maxsize=1)
def route_effect(n_perm: int = 1000, seed: int = 7) -> dict:
    """Is the warehouse route later than direct shipping for the same country, year and transport mode?

    Compares like with like: only (country, year, mode) groups that used both routes. Mantel-Haenszel odds
    ratio, with a permutation test that shuffles the route label within each group.
    """
    d = lines()
    d["stratum"] = d.country + "|" + d.year.astype(str) + "|" + d["mode"]
    both = d.groupby("stratum").fulfill_via.transform("nunique") == 2
    d = d[both]
    late, rdc, s = d.late.to_numpy(bool), (d.fulfill_via == "From RDC").to_numpy(bool), d.stratum.to_numpy()
    obs = _cmh(late, rdc, s)
    rng = np.random.default_rng(seed)
    codes = pd.factorize(s)[0]
    order = np.argsort(codes, kind="stable")
    bounds = np.flatnonzero(np.diff(codes[order])) + 1
    groups = np.split(order, bounds)
    ge = 0
    for _ in range(n_perm):
        perm = rdc.copy()
        for g in groups:
            perm[g] = rng.permutation(rdc[g])
        ge += _cmh(late, perm, s) >= obs
    rates = d.groupby("fulfill_via").late.mean()
    return {"odds_ratio": obs, "p_value": (ge + 1) / (n_perm + 1), "strata": int(pd.Series(s).nunique()), "lines": int(len(d)),
            "rdc_late_rate": float(rates["From RDC"]), "direct_late_rate": float(rates["Direct Drop"]), "n_perm": n_perm}


def by_country() -> pd.DataFrame:
    c = q("""SELECT country, count(*) AS lines, count(DISTINCT shipment_id) AS shipments, avg(late::INT) AS late_rate,
                    sum(late::INT) AS late_lines, sum(value_usd) AS value_usd, sum(value_usd * late::INT) AS late_value_usd,
                    avg(CASE WHEN fulfill_via = 'From RDC' THEN 1 ELSE 0 END) AS rdc_share,
                    avg(late::INT) FILTER (WHERE fulfill_via = 'From RDC') AS rdc_late_rate,
                    avg(late::INT) FILTER (WHERE fulfill_via = 'Direct Drop') AS direct_late_rate
             FROM lines GROUP BY country""")
    f = q("""SELECT country, sum(freight_usd) AS freight_usd, sum(freight_usd) / sum(weight_kg) AS freight_per_kg,
                    avg(CASE WHEN mode IN ('Air', 'Air Charter') THEN 1 ELSE 0 END) AS air_share
             FROM shipments WHERE usd_per_kg IS NOT NULL GROUP BY country""")
    return c.merge(f, on="country", how="left").sort_values("late_lines", ascending=False).reset_index(drop=True)


def vendor_scorecard() -> pd.DataFrame:
    """Direct-ship vendors with at least MIN_VENDOR_LINES lines (RDC lines are SCMS's own warehouse)."""
    v = q(f"""SELECT vendor, count(*) AS lines, sum(value_usd) AS value_usd, avg(late::INT) AS late_rate, sum(late::INT) AS late_lines,
                     median(days_late) FILTER (WHERE late) AS median_days_late, count(DISTINCT country) AS countries,
                     median(po_to_delivery_days) AS median_po_to_delivery_days
              FROM lines WHERE fulfill_via = 'Direct Drop' GROUP BY vendor HAVING count(*) >= {MIN_VENDOR_LINES}""")
    return v.sort_values("late_lines", ascending=False).reset_index(drop=True)


def worklist(n: int = 10, country: str | None = None) -> pd.DataFrame:
    """Country x route lanes ranked by commodity value delivered late: where a delivery fix protects the most stock."""
    where = "WHERE country = ?" if country else ""
    w = q(f"""SELECT country, route, count(*) AS lines, sum(late::INT) AS late_lines, avg(late::INT) AS late_rate,
                     sum(value_usd * late::INT) AS late_value_usd, median(days_late) FILTER (WHERE late) AS median_days_late
              FROM lines {where} GROUP BY country, route HAVING sum(late::INT) > 0
              ORDER BY late_value_usd DESC LIMIT {int(n)}""", [country] if country else None)
    return w


# ------------------------------------------------------------------ freight
def by_mode() -> pd.DataFrame:
    m = q("""SELECT mode, count(*) AS shipments, sum(freight_usd) AS freight_usd, sum(weight_kg) AS weight_kg,
                    sum(freight_usd) / sum(weight_kg) AS freight_per_kg, median(usd_per_kg) AS median_usd_per_kg,
                    median(weight_kg) AS median_weight_kg, sum(freight_usd) / sum(value_usd) AS freight_share_of_value
             FROM shipments WHERE usd_per_kg IS NOT NULL GROUP BY mode""")
    m["share_of_freight"] = m.freight_usd / m.freight_usd.sum()
    t = q("""SELECT mode, count(*) AS lines, avg(late::INT) AS late_rate, median(po_to_delivery_days) AS median_po_to_delivery_days
             FROM lines GROUP BY mode""")
    return m.merge(t, on="mode", how="outer").sort_values("freight_usd", ascending=False, na_position="last").reset_index(drop=True)


def by_weight_band() -> pd.DataFrame:
    p = priced()
    p["band"] = pd.cut(p.weight_kg, WEIGHT_BANDS, labels=BAND_LABELS, right=False)
    g = p.groupby("band", observed=True).agg(shipments=("shipment_id", "size"), freight_usd=("freight_usd", "sum"),
                                             weight_kg=("weight_kg", "sum"), median_usd_per_kg=("usd_per_kg", "median"),
                                             median_freight_share=("freight_pct_value", "median")).reset_index()
    g["band"] = g.band.astype(str)
    return g


def small_shipments(max_kg: float = 100) -> dict:
    p = priced()
    s = p[p.weight_kg < max_kg]
    return {"max_kg": max_kg, "shipments": int(len(s)), "share_of_shipments": len(s) / len(p), "freight_usd": float(s.freight_usd.sum()),
            "weight_share": float(s.weight_kg.sum() / p.weight_kg.sum()), "median_usd_per_kg": float(s.usd_per_kg.median()),
            "median_freight_share": float(s.freight_pct_value.median()),
            "large_median_usd_per_kg": float(p[p.weight_kg >= 2000].usd_per_kg.median())}


def mode_shift(min_kg: float = SHIFT_MIN_KG, min_plan_days: float = SHIFT_MIN_PLAN_DAYS) -> dict:
    """Air shipments heavy enough and planned far enough ahead to have gone by sea: what ocean rates would have cost.

    Ocean rate: the destination country's median ocean $/kg when it has 5+ priced ocean shipments, else the overall
    ocean median. Savings are capped at zero per shipment (never counts a shipment as cheaper by air).
    """
    p = priced()
    oc = p[p["mode"] == "Ocean"]
    cm = oc.groupby("country").usd_per_kg.agg(["median", "size"])
    country_rate = cm[cm["size"] >= 5]["median"]
    c = p[(p["mode"] == "Air") & (p.weight_kg >= min_kg) & (p.po_to_schedule_days >= min_plan_days)].copy()
    c["ocean_rate"] = c.country.map(country_rate).fillna(oc.usd_per_kg.median())
    c["ocean_cost"] = c.weight_kg * c.ocean_rate
    c["saving"] = (c.freight_usd - c.ocean_cost).clip(lower=0)
    air = p[p["mode"] == "Air"]
    by_c = c.groupby("country").agg(shipments=("shipment_id", "size"), air_freight_usd=("freight_usd", "sum"),
                                    saving_usd=("saving", "sum")).sort_values("saving_usd", ascending=False).reset_index()
    return {"min_kg": min_kg, "min_plan_days": min_plan_days, "eligible_shipments": int(len(c)), "air_shipments": int(len(air)),
            "eligible_air_freight_usd": float(c.freight_usd.sum()), "ocean_cost_usd": float(c.ocean_cost.sum()),
            "saving_usd": float(c.saving.sum()), "saving_share_of_air_freight": float(c.saving.sum() / air.freight_usd.sum()),
            "countries": int(c.country.nunique()), "ocean_median_usd_per_kg": float(oc.usd_per_kg.median()),
            "ocean_median_po_to_delivery_days": float(shipments().query("mode == 'Ocean'").po_to_delivery_days.median()),
            "air_median_po_to_delivery_days": float(shipments().query("mode == 'Air'").po_to_delivery_days.median()),
            "by_country": by_c}


# ------------------------------------------------------------------ data quality
def data_quality() -> dict:
    s = q("SELECT freight_status, count(*) AS n FROM shipments GROUP BY freight_status").set_index("freight_status").n
    ln = q("""SELECT avg(CASE WHEN freight_status = 'priced' THEN 0 ELSE 1 END) AS lines_without_own_freight,
                    avg(CASE WHEN record_lag_days > 0 THEN 1 ELSE 0 END) AS recorded_late_share,
                    count(*) FILTER (WHERE po_sent IS NULL AND fulfill_via = 'Direct Drop') AS direct_missing_po_date,
                    count(*) FILTER (WHERE fulfill_via = 'Direct Drop') AS direct_lines,
                    count(*) FILTER (WHERE mode = 'Not recorded') AS mode_not_recorded,
                    count(*) FILTER (WHERE weight_kg IS NULL AND freight_status = 'priced') AS priced_without_weight
             FROM lines""").iloc[0]
    total = int(s.sum())
    return {"shipments": total, "priced_shipments": int(s.get("priced", 0)),
            "freight_in_commodity_cost": int(s.get("included in commodity cost", 0)), "freight_invoiced_separately": int(s.get("invoiced separately", 0)),
            "unpriced_share": 1 - s.get("priced", 0) / total, **{k: float(v) for k, v in ln.items()}}


# ------------------------------------------------------------------ narrative helpers
def label_route(fulfill_via: str) -> str:
    return {"Direct Drop": "direct from vendor", "From RDC": "from the regional warehouse"}.get(fulfill_via, fulfill_via)


def countries() -> list[str]:
    return sorted(q("SELECT DISTINCT country FROM lines").country)


def vendors() -> list[str]:
    return sorted(q("SELECT DISTINCT vendor FROM lines").vendor)


def late_value_concentration(top: int = 5) -> dict:
    """How much of the commodity value delivered late sits in the top lanes, and in warehouse lanes."""
    w = q("""SELECT country, route, sum(value_usd * late::INT) AS late_value_usd FROM lines GROUP BY country, route
             ORDER BY late_value_usd DESC""")
    total = w.late_value_usd.sum()
    return {"top": top, "lanes": int((w.late_value_usd > 0).sum()), "top_share": float(w.head(top).late_value_usd.sum() / total),
            "warehouse_share": float(w[w.route.str.startswith("From regional")].late_value_usd.sum() / total)}
