"""Tools the supply-chain assistant can call. Each returns JSON-serialisable facts from the governed metrics.

TOOL_SPECS is the OpenAI-compatible function schema used in LLM mode; the offline planner calls the same
functions, so both modes answer from identical facts.
"""
from __future__ import annotations

import re

import pandas as pd

from . import metrics as m
from .data import PERIOD, SOURCE, q

COUNTRIES = m.countries()
RANK_MIN_LINES = 100  # countries need this many line items to be ranked
VENDORS = m.vendors()
VENDOR_GENERIC = {"ltd", "limited", "inc", "plc", "pvt", "pharma", "pharmaceuticals", "pharmaceutical", "laboratories", "laboratory",
                  "labs", "the", "of", "and", "co", "corp", "corporation", "company", "sa", "ag", "gmbh", "bv", "llc", "formerly",
                  "logistics", "industries", "healthcare", "health", "international", "global", "from", "scms", "rdc", "s", "a",
                  "de", "group", "products", "diagnostics", "medical", "biotech", "chemicals", "fine", "trading", "france", "india",
                  "usa", "uk", "africa", "south", "kenya", "limitada", "drug", "drugs", "wholesaler", "standard", "life", "sciences"}


def _r(x, n: int = 1):
    return None if x is None or pd.isna(x) else round(float(x), n)


def _i(x):
    return None if x is None or pd.isna(x) else int(round(float(x)))


def _pct(x, n: int = 1):
    return None if x is None or pd.isna(x) else round(float(x) * 100, n)


def _m(x, n: int = 1):
    """US dollars to millions."""
    return None if x is None or pd.isna(x) else round(float(x) / 1e6, n)


def network_summary() -> dict:
    k = m.kpis()
    e = m.route_effect()
    md = m.by_mode().set_index("mode")
    ms = m.mode_shift()
    return {"source": SOURCE, "period": PERIOD, "line_items": _i(k["lines"]), "shipments": _i(k["shipments"]), "countries": _i(k["countries"]),
            "commodity_value_musd": _m(k["value_usd"]), "on_time_pct": _pct(k["otd_rate"]), "on_time_value_pct": _pct(k["otd_value_rate"]),
            "late_value_musd": _m(k["late_value_usd"]), "median_days_late": _i(k["median_days_late"]),
            "warehouse_late_pct": _pct(e["rdc_late_rate"]), "direct_late_pct": _pct(e["direct_late_rate"]),
            "warehouse_late_odds_ratio": _r(e["odds_ratio"]), "freight_musd": _m(k["freight_usd"]),
            "air_share_of_freight_pct": _pct(md.loc["Air", "share_of_freight"]), "air_usd_per_kg": _r(md.loc["Air", "freight_per_kg"], 2),
            "ocean_usd_per_kg": _r(md.loc["Ocean", "freight_per_kg"], 2), "mode_shift_saving_musd": _m(ms["saving_usd"], 2),
            "mode_shift_shipments": ms["eligible_shipments"]}


def route_comparison() -> dict:
    e = m.route_effect()
    r = m.by_route().set_index("route")
    yr = m.by_year_route().pivot(index="year", columns="route", values="late_rate")
    w, d = "From regional warehouse (RDC)", "Direct from vendor"
    worst = yr[w].idxmax()
    return {"warehouse_lines": _i(r.loc[w, "lines"]), "direct_lines": _i(r.loc[d, "lines"]),
            "warehouse_late_pct": _pct(r.loc[w, "late_rate"]), "direct_late_pct": _pct(r.loc[d, "late_rate"]),
            "warehouse_value_musd": _m(r.loc[w, "value_usd"]), "direct_value_musd": _m(r.loc[d, "value_usd"]),
            "like_for_like_odds_ratio": _r(e["odds_ratio"]), "like_for_like_p_value": _r(e["p_value"], 3),
            "like_for_like_groups": e["strata"], "like_for_like_lines": e["lines"],
            "warehouse_worst_year": _i(worst), "warehouse_worst_year_late_pct": _pct(yr.loc[worst, w]),
            "direct_same_year_late_pct": _pct(yr.loc[worst, d]),
            "warehouse_late_pct_2013_2015": _pct(q("SELECT avg(late::INT) AS r FROM lines WHERE fulfill_via='From RDC' AND year BETWEEN 2013 AND 2015").r[0]),
            "direct_late_pct_2013_2015": _pct(q("SELECT avg(late::INT) AS r FROM lines WHERE fulfill_via='Direct Drop' AND year BETWEEN 2013 AND 2015").r[0])}


def country_profile(country: str) -> dict:
    c = m.by_country().set_index("country")
    if country not in c.index:
        return {"error": f"no shipments to {country}", "known_countries": COUNTRIES}
    r = c.loc[country]
    ranked = c[c.lines >= RANK_MIN_LINES].sort_values("late_rate", ascending=False)
    rank = int(list(ranked.index).index(country)) + 1 if country in ranked.index else None
    lanes = m.worklist(n=5, country=country)
    modes = q("""SELECT mode, count(*) AS shipments, sum(freight_usd) AS freight_usd FROM shipments
                 WHERE country = ? AND usd_per_kg IS NOT NULL GROUP BY mode ORDER BY freight_usd DESC""", [country])
    return {"country": country, "line_items": _i(r.lines), "shipments": _i(r.shipments), "commodity_value_musd": _m(r.value_usd),
            "late_pct": _pct(r.late_rate), "on_time_pct": _pct(1 - r.late_rate), "late_lines": _i(r.late_lines),
            "late_value_musd": _m(r.late_value_usd), "warehouse_share_pct": _pct(r.rdc_share),
            "warehouse_late_pct": _pct(r.rdc_late_rate), "direct_late_pct": _pct(r.direct_late_rate),
            "freight_musd": _m(r.freight_usd, 2), "freight_usd_per_kg": _r(r.freight_per_kg, 2), "air_share_of_shipments_pct": _pct(r.air_share),
            "late_rank": rank, "countries_ranked": len(ranked), "rank_min_lines": RANK_MIN_LINES,
            "lanes": [{"route": x.route, "lines": _i(x.lines), "late_pct": _pct(x.late_rate), "late_value_musd": _m(x.late_value_usd, 2),
                       "median_days_late": _r(x.median_days_late)} for x in lanes.itertuples()],
            "freight_by_mode": [{"mode": x.mode, "shipments": _i(x.shipments), "freight_musd": _m(x.freight_usd, 2)} for x in modes.itertuples()]}


def vendor_profile(vendor: str) -> dict:
    v = m.vendor_scorecard().set_index("vendor")
    if vendor not in VENDORS:
        return {"error": f"unknown vendor {vendor}"}
    if vendor not in v.index:
        n = int(q("SELECT count(*) AS n FROM lines WHERE vendor = ? AND fulfill_via = 'Direct Drop'", [vendor]).n[0])
        return {"vendor": vendor, "error": f"{vendor} has {n} direct-ship line items; the scorecard needs {m.MIN_VENDOR_LINES}+"}
    r = v.loc[vendor]
    rank = int(list(v.sort_values("late_rate", ascending=False).index).index(vendor)) + 1
    return {"vendor": vendor, "direct_line_items": _i(r.lines), "commodity_value_musd": _m(r.value_usd), "late_pct": _pct(r.late_rate),
            "late_lines": _i(r.late_lines), "median_days_late": _r(r.median_days_late), "countries": _i(r.countries),
            "median_po_to_delivery_days": _r(r.median_po_to_delivery_days), "late_rank": rank, "vendors_scored": len(v),
            "all_direct_late_pct": _pct(q("SELECT avg(late::INT) AS r FROM lines WHERE fulfill_via='Direct Drop'").r[0])}


def freight_by_mode() -> dict:
    md = m.by_mode()
    md = md[md["mode"] != "Not recorded"]
    sm = m.small_shipments()
    return {"freight_musd": _m(md.freight_usd.sum()), "unrecorded_mode_freight_musd": _m(m.by_mode().set_index("mode").freight_usd.get("Not recorded")),
            "modes": [{"mode": x.mode, "shipments": _i(x.shipments), "freight_musd": _m(x.freight_usd), "share_of_freight_pct": _pct(x.share_of_freight),
                       "usd_per_kg": _r(x.freight_per_kg, 2), "median_weight_kg": _i(x.median_weight_kg), "late_pct": _pct(x.late_rate),
                       "median_po_to_delivery_days": _i(x.median_po_to_delivery_days)} for x in md.itertuples()],
            "small_shipments_under_kg": _i(sm["max_kg"]), "small_shipments": sm["shipments"], "small_share_of_shipments_pct": _pct(sm["share_of_shipments"]),
            "small_median_usd_per_kg": _r(sm["median_usd_per_kg"]), "small_freight_share_of_value_pct": _pct(sm["median_freight_share"]),
            "two_tonne_plus_median_usd_per_kg": _r(sm["large_median_usd_per_kg"])}


def mode_shift_scenario(min_kg: float = m.SHIFT_MIN_KG, min_plan_days: float = m.SHIFT_MIN_PLAN_DAYS) -> dict:
    s = m.mode_shift(float(min_kg), float(min_plan_days))
    return {"min_kg": _i(s["min_kg"]), "min_plan_days": _i(s["min_plan_days"]), "eligible_shipments": s["eligible_shipments"],
            "air_shipments": s["air_shipments"], "eligible_air_freight_musd": _m(s["eligible_air_freight_usd"], 2),
            "ocean_cost_musd": _m(s["ocean_cost_usd"], 2), "saving_musd": _m(s["saving_usd"], 2),
            "saving_share_of_air_freight_pct": _pct(s["saving_share_of_air_freight"]), "countries": s["countries"],
            "ocean_median_usd_per_kg": _r(s["ocean_median_usd_per_kg"], 2), "ocean_median_po_to_delivery_days": _i(s["ocean_median_po_to_delivery_days"]),
            "air_median_po_to_delivery_days": _i(s["air_median_po_to_delivery_days"]),
            "top_countries": [{"country": x.country, "shipments": _i(x.shipments), "saving_musd": _m(x.saving_usd, 2)}
                              for x in s["by_country"].head(5).itertuples()]}


def worklist(country: str | None = None, n: int = 10) -> dict:
    if country and country not in COUNTRIES:
        return {"error": f"no shipments to {country}", "known_countries": COUNTRIES}
    w = m.worklist(n=int(n), country=country)
    return {"country": country, "count": len(w),
            "items": [{"country": x.country, "route": x.route, "lines": _i(x.lines), "late_lines": _i(x.late_lines), "late_pct": _pct(x.late_rate),
                       "late_value_musd": _m(x.late_value_usd, 2), "median_days_late": _r(x.median_days_late)} for x in w.itertuples()]}


def find_vendor(name: str) -> dict:
    return {"query": name, "matches": match_vendors(name)[:8]}


# ------------------------------------------------------------------ name matching
def _vtokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", s.lower().replace(".", "")) if t not in VENDOR_GENERIC and len(t) > 2]


def match_vendors(text: str) -> list[str]:
    """Vendors whose first distinctive name word appears in the text (best: most distinctive words matched)."""
    words = set(re.findall(r"[a-z0-9]+", text.lower().replace(".", "")))
    hits = []
    for v in VENDORS:
        toks = _vtokens(v)
        if toks and toks[0] in words:
            hits.append((v, sum(t in words for t in toks)))
    if not hits:
        return []
    best = max(n for _, n in hits)
    top = [v for v, n in hits if n == best]
    scored = [v for v in top if v in _scored()]
    return scored if len(top) > 1 and len(scored) == 1 else top


def _scored() -> set[str]:
    return set(m.vendor_scorecard().vendor)


def match_country(text: str) -> str | None:
    low = text.lower()
    aliases = {"ivory coast": "Côte d'Ivoire", "cote d'ivoire": "Côte d'Ivoire", "drc": "Congo, DRC", "congo": "Congo, DRC",
               "democratic republic of the congo": "Congo, DRC"}
    for c in sorted(COUNTRIES, key=len, reverse=True):
        if re.search(r"(?<![\w])" + re.escape(c.lower()) + r"(?![\w])", low):
            return c
    for a, c in sorted(aliases.items(), key=lambda x: -len(x[0])):
        if re.search(r"(?<![\w])" + re.escape(a) + r"(?![\w])", low) and c in COUNTRIES:
            return c
    return None


TOOLS = {"network_summary": network_summary, "route_comparison": route_comparison, "country_profile": country_profile,
         "vendor_profile": vendor_profile, "freight_by_mode": freight_by_mode, "mode_shift_scenario": mode_shift_scenario,
         "worklist": worklist, "find_vendor": find_vendor}

_COUNTRY = {"type": "string", "enum": COUNTRIES, "description": "destination country, as named in the data"}
TOOL_SPECS = [
    {"type": "function", "function": {"name": "network_summary",
     "description": "Whole-network picture: on-time delivery, value delivered late, warehouse vs direct lateness, freight spend and the mode-shift saving.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "route_comparison",
     "description": "Regional warehouse (RDC) vs direct-from-vendor delivery: late rates, like-for-like odds ratio within country, year and mode, worst year.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "country_profile",
     "description": "One destination country: on-time delivery by route, value delivered late, freight cost and mode mix, worst lanes.",
     "parameters": {"type": "object", "properties": {"country": _COUNTRY}, "required": ["country"]}}},
    {"type": "function", "function": {"name": "vendor_profile",
     "description": f"One vendor's direct-ship scorecard ({m.MIN_VENDOR_LINES}+ line items): late rate, days late, lead time, rank. Use find_vendor first.",
     "parameters": {"type": "object", "properties": {"vendor": {"type": "string", "description": "exact vendor name from find_vendor"}}, "required": ["vendor"]}}},
    {"type": "function", "function": {"name": "freight_by_mode",
     "description": "Freight spend, cost per kg, lateness and lead time by transport mode (air, air charter, truck, ocean), plus the small-shipment penalty.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "mode_shift_scenario",
     "description": "Estimated saving if heavy air shipments planned far enough ahead had gone by ocean at ocean rates.",
     "parameters": {"type": "object", "properties": {"min_kg": {"type": "number", "default": m.SHIFT_MIN_KG},
                                                     "min_plan_days": {"type": "number", "default": m.SHIFT_MIN_PLAN_DAYS,
                                                                       "description": "days from PO to scheduled delivery"}}}}},
    {"type": "function", "function": {"name": "worklist",
     "description": "Country x route lanes ranked by commodity value delivered late, optionally for one country.",
     "parameters": {"type": "object", "properties": {"country": _COUNTRY, "n": {"type": "integer", "default": 10}}}}},
    {"type": "function", "function": {"name": "find_vendor",
     "description": "Look up exact vendor names from part of a name.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
]
