"""Supply-chain assistant: plans tool calls, runs them, and answers only from their results.

Offline mode: a deterministic planner maps the question to tool calls (country, vendor and scenario thresholds
resolved from the text) and templates write the answer.
LLM mode: the model chooses tools through OpenAI-style function calling (max 4 rounds) and writes the answer;
a grounding check rejects any number not present in the tool results and falls back to the template answer.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import llm
from .tools import TOOL_SPECS, TOOLS, match_country, match_vendors

SHIFT = re.compile(r"\b(shift\w*|switch\w*|mov\w+ .*(ocean|sea)|by sea|sea freight|ocean instead|sav(e|ed|es|ing|ings)|cheaper|cut (freight|cost)|"
                   r"what if|scenario)\b", re.I)
ROUTE = re.compile(r"\b(warehouse\w*|rdc|distribution cent\w*|direct(ly)?|direct drop|route)\b", re.I)
FREIGHT = re.compile(r"\b(freight|air|ocean|truck\w*|sea|modes?|transport|per kg|kg|kilo\w*|shipping costs?|logistics costs?|consolidat\w*|"
                     r"small shipments?|charter)\b", re.I)
WORKLIST = re.compile(r"\b(where|priorit\w*|worst|lanes?|focus|first|rank\w*|biggest|largest|most|top|fix|act)\b", re.I)
KG = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(kg|kilo\w*|t\b|tonnes?|tons?)", re.I)
DAYS = re.compile(r"(\d[\d,]*)\s*days?", re.I)


@dataclass
class Answer:
    question: str
    text: str
    calls: list[dict] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)
    mode: str = "offline"
    grounded: bool = True
    ungrounded: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ planning
def _shift_args(text: str) -> dict:
    args = {}
    if (k := KG.search(text)):
        v = float(k.group(1).replace(",", ""))
        args["min_kg"] = v * 1000 if k.group(2).lower().startswith("t") else v
    if (d := DAYS.search(text)):
        args["min_plan_days"] = float(d.group(1).replace(",", ""))
    return args


def plan(question: str) -> list[dict]:
    vendors = match_vendors(question)
    if len(vendors) == 1:
        return [{"tool": "vendor_profile", "args": {"vendor": vendors[0]}}]
    if len(vendors) > 1:
        return [{"tool": "find_vendor", "args": {"name": question}}]
    country = match_country(question)
    if SHIFT.search(question):
        return [{"tool": "mode_shift_scenario", "args": _shift_args(question)}]
    if country:
        if WORKLIST.search(question) and not re.search(r"\bhow\b", question, re.I):
            return [{"tool": "worklist", "args": {"country": country}}]
        return [{"tool": "country_profile", "args": {"country": country}}]
    if ROUTE.search(question):
        return [{"tool": "route_comparison", "args": {}}]
    if FREIGHT.search(question):
        return [{"tool": "freight_by_mode", "args": {}}]
    if WORKLIST.search(question):
        return [{"tool": "worklist", "args": {}}]
    return [{"tool": "network_summary", "args": {}}]


# ------------------------------------------------------------------ templates
def _money(x) -> str:
    return f"${x:,}M"


def _render(call: dict, r: dict) -> str:
    t = call["tool"]
    if "error" in r:
        return f"I could not answer that from the data: {r['error']}."
    if t == "network_summary":
        return (f"Across {r['line_items']:,} line items in {r['shipments']:,} shipments to {r['countries']} countries ({r['period']}), "
                f"{r['on_time_pct']}% of lines arrived on or before the scheduled date, but only {r['on_time_value_pct']}% by value: "
                f"{_money(r['late_value_musd'])} of {_money(r['commodity_value_musd'])} arrived late (median {r['median_days_late']} days). "
                f"Lines shipped from the regional warehouse were late {r['warehouse_late_pct']}% of the time vs {r['direct_late_pct']}% for "
                f"direct shipments in the same country, year and mode, odds {r['warehouse_late_odds_ratio']}x higher. Air carries "
                f"{r['air_share_of_freight_pct']}% of the {_money(r['freight_musd'])} freight bill at ${r['air_usd_per_kg']}/kg vs "
                f"${r['ocean_usd_per_kg']}/kg by ocean; moving {r['mode_shift_shipments']} heavy, well-planned air shipments to ocean would "
                f"have saved about {_money(r['mode_shift_saving_musd'])}.")
    if t == "route_comparison":
        return (f"The regional warehouse route is the main delivery problem. Warehouse lines were late {r['warehouse_late_pct']}% of the time "
                f"({r['warehouse_lines']:,} lines, {_money(r['warehouse_value_musd'])}) vs {r['direct_late_pct']}% for direct shipments "
                f"({r['direct_lines']:,} lines). Comparing like with like ({r['like_for_like_lines']:,} lines in {r['like_for_like_groups']} "
                f"country-year-mode groups that used both routes), warehouse lines had {r['like_for_like_odds_ratio']}x the odds of arriving late "
                f"(permutation p = {r['like_for_like_p_value']}). It got worse over time: {r['warehouse_late_pct_2013_2015']}% late in 2013-2015 "
                f"vs {r['direct_late_pct_2013_2015']}% direct; the worst year was {r['warehouse_worst_year']} at "
                f"{r['warehouse_worst_year_late_pct']}% (direct: {r['direct_same_year_late_pct']}%).")
    if t == "country_profile":
        rank = f"ranks {r['late_rank']} of {r['countries_ranked']} countries for late rate" if r["late_rank"] else "has too few lines to rank"
        wh = (f"warehouse lines {r['warehouse_late_pct']}% late, direct {r['direct_late_pct']}%"
              if r["warehouse_late_pct"] is not None and r["direct_late_pct"] is not None else
              f"all lines {'from the warehouse' if r['direct_late_pct'] is None else 'direct'}")
        lanes = "; ".join(f"{x['route']}: {x['late_pct']}% late, {_money(x['late_value_musd'])} late" for x in r["lanes"])
        out = (f"{r['country']}: {r['line_items']:,} line items in {r['shipments']:,} shipments ({_money(r['commodity_value_musd'])}). "
               f"{r['late_pct']}% of lines arrived late ({_money(r['late_value_musd'])} of stock); {wh}; "
               f"the country {rank} (countries with {r['rank_min_lines']}+ line items). ")
        if r["freight_musd"] is not None:
            out += (f"Freight {_money(r['freight_musd'])} at ${r['freight_usd_per_kg']}/kg; {r['air_share_of_shipments_pct']}% of priced "
                    f"shipments went by air. ")
        return out + (f"Lanes: {lanes}." if lanes else "")
    if t == "vendor_profile":
        return (f"{r['vendor']} (direct shipments): {r['direct_line_items']:,} line items worth {_money(r['commodity_value_musd'])} to "
                f"{r['countries']} countries. {r['late_pct']}% arrived late ({r['late_lines']} lines, median {r['median_days_late']} days late) "
                f"vs {r['all_direct_late_pct']}% for all direct shipments; it ranks {r['late_rank']} of {r['vendors_scored']} scored vendors "
                f"for late rate. Median {r['median_po_to_delivery_days']} days from purchase order to delivery.")
    if t == "freight_by_mode":
        modes = "; ".join(f"{x['mode']}: {_money(x['freight_musd'])} ({x['share_of_freight_pct']}%), ${x['usd_per_kg']}/kg, "
                          f"{x['late_pct']}% late, median {x['median_po_to_delivery_days']} days PO to delivery" for x in r["modes"])
        return (f"Freight cost {_money(r['freight_musd'])} across priced shipments with a recorded mode "
                f"(another {_money(r['unrecorded_mode_freight_musd'])} has no mode recorded). By mode: {modes}. Size matters as much as mode: "
                f"{r['small_shipments']:,} shipments under {r['small_shipments_under_kg']} kg ({r['small_share_of_shipments_pct']}% of shipments) "
                f"paid a median ${r['small_median_usd_per_kg']}/kg, and freight was {r['small_freight_share_of_value_pct']}% of their commodity "
                f"value, vs ${r['two_tonne_plus_median_usd_per_kg']}/kg for shipments of 2 t or more. Consolidating small orders is the lever.")
    if t == "mode_shift_scenario":
        top = "; ".join(f"{x['country']} {_money(x['saving_musd'])} ({x['shipments']} shipments)" for x in r["top_countries"])
        return (f"Scenario: air shipments of {r['min_kg']:,} kg or more whose purchase order went out at least {r['min_plan_days']} days "
                f"before the scheduled delivery (ocean takes a median {r['ocean_median_po_to_delivery_days']} days from PO to delivery vs "
                f"{r['air_median_po_to_delivery_days']} by air). {r['eligible_shipments']} of {r['air_shipments']:,} air shipments qualify; they "
                f"cost {_money(r['eligible_air_freight_musd'])} by air and about {_money(r['ocean_cost_musd'])} at ocean rates "
                f"(median ${r['ocean_median_usd_per_kg']}/kg), a saving of about {_money(r['saving_musd'])} "
                f"({r['saving_share_of_air_freight_pct']}% of all air freight). Largest savings: {top}.")
    if t == "worklist":
        scope = f"for {r['country']}" if r.get("country") else "across the network"
        if not r["items"]:
            return f"No late deliveries {scope}."
        lines = [f"Top {r['count']} delivery lanes {scope}, by commodity value delivered late:"]
        lines += [f"- {x['country']}, {x['route']}: {_money(x['late_value_musd'])} late, {x['late_lines']} of {x['lines']:,} lines "
                  f"({x['late_pct']}%), median {x['median_days_late']} days late" for x in r["items"]]
        return "\n".join(lines)
    if t == "find_vendor":
        if not r["matches"]:
            return "I could not match that vendor. Try a distinctive word from the vendor's name."
        return "Several vendors match: " + "; ".join(r["matches"]) + ". Which one do you mean?"
    return json.dumps(r)


# ------------------------------------------------------------------ grounding
_NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def _norm(t: str) -> str:
    t = t.replace(",", "").lstrip("-")
    return t.rstrip("0").rstrip(".") if "." in t else t


def _numbers(obj) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out |= _numbers(v) | _numbers(k)
    elif isinstance(obj, list):
        for v in obj:
            out |= _numbers(v)
    elif isinstance(obj, bool) or obj is None:
        pass
    elif isinstance(obj, (int, float)):
        x = float(obj)
        for s in (f"{x:g}", f"{x:.1f}", f"{x:.0f}", f"{x:.2f}", f"{x:.3f}"):
            out.add(_norm(s))
    elif isinstance(obj, str):
        out |= {_norm(mm.group(0)) for mm in _NUM.finditer(obj)}
    return out


ALLOWED_CONSTANTS = {"2", "2013", "2015"}  # "2 t or more" size band; the 2013-2015 window named in route_comparison


def check_grounding(text: str, results: list[dict]) -> list[str]:
    allowed = set().union(*[_numbers(r) for r in results]) if results else set()
    return [mm.group(0) for mm in _NUM.finditer(text) if _norm(mm.group(0)) not in allowed | ALLOWED_CONSTANTS]


# ------------------------------------------------------------------ entry points
def run(calls: list[dict]) -> list[dict]:
    return [TOOLS[c["tool"]](**c["args"]) for c in calls]


SYSTEM = ("You are a supply-chain analyst assistant for USAID SCMS health-commodity shipments (2006-2015). Use the tools to get facts, "
          "then answer in 2-6 sentences or bullets. Use ONLY numbers returned by the tools, copied exactly; do not compute new numbers. "
          "'Late' means delivered after the scheduled delivery date; money is in millions of US dollars (musd).")


def ask(question: str) -> Answer:
    if not llm.enabled():
        calls = plan(question)
        results = run(calls)
        text = "\n\n".join(_render(c, r) for c, r in zip(calls, results))
        return Answer(question, text, calls, results, "offline", not check_grounding(text, results))
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    calls, results, msg = [], [], {}
    for _ in range(4):
        msg = llm.chat(msgs, tools=TOOL_SPECS)
        msgs.append(msg)
        if not msg.get("tool_calls"):
            break
        for tc in msg["tool_calls"]:
            name, args = tc["function"]["name"], json.loads(tc["function"].get("arguments") or "{}")
            res = TOOLS[name](**args) if name in TOOLS else {"error": f"unknown tool {name}"}
            calls.append({"tool": name, "args": args})
            results.append(res)
            msgs.append({"role": "tool", "tool_call_id": tc.get("id", name), "content": json.dumps(res)})
    text = (msg.get("content") or "").strip()
    bad = check_grounding(text, results)
    if text and results and not bad:
        return Answer(question, text, calls, results, "llm")
    calls = calls or plan(question)
    results = results or run(calls)
    fallback = "\n\n".join(_render(c, r) for c, r in zip(calls, results))
    return Answer(question, fallback, calls, results, "llm-fallback", True, bad)


def country_brief(country: str) -> str:
    """One-page delivery and freight brief for a country supply planner, built only from tool results."""
    p = TOOLS["country_profile"](country)
    if "error" in p:
        return p["error"]
    w = TOOLS["worklist"](country=country, n=5)
    out = [f"### Delivery and freight brief: {p['country']}",
           f"{p['line_items']:,} line items · {p['shipments']:,} shipments · {_money(p['commodity_value_musd'])} of commodities", "",
           f"**On time:** {p['on_time_pct']}% of lines; {_money(p['late_value_musd'])} of stock arrived late "
           f"(rank {p['late_rank'] or 'n/a'} of {p['countries_ranked']} for late rate).", "",
           "| Lane | Lines | Late | Value late | Median days late |", "|---|---|---|---|---|"]
    out += [f"| {x['route']} | {x['lines']:,} | {x['late_pct']}% | {_money(x['late_value_musd'])} | {x['median_days_late']} |" for x in w["items"]]
    if p["freight_by_mode"]:
        out += ["", "| Mode | Priced shipments | Freight |", "|---|---|---|"]
        out += [f"| {x['mode']} | {x['shipments']:,} | {_money(x['freight_musd'])} |" for x in p["freight_by_mode"]]
        out += ["", f"**Freight:** {_money(p['freight_musd'])} at ${p['freight_usd_per_kg']}/kg; {p['air_share_of_shipments_pct']}% of priced shipments by air."]
    top = w["items"][0] if w["items"] else None
    wh_worse = p["warehouse_late_pct"] is not None and p["direct_late_pct"] is not None and p["warehouse_late_pct"] > p["direct_late_pct"]
    if top and top["route"].startswith("From regional") and (wh_worse or p["direct_late_pct"] is None):
        action = ("Start with warehouse replenishment and dispatch for this country: the warehouse lane holds the most stock delivered late"
                  + (" and runs late more often than direct shipments." if wh_worse else "."))
    elif top:
        action = "Start with the direct-from-vendor lane: review promised dates and vendor dispatch with the largest late vendors."
    else:
        action = "No late deliveries recorded."
    out += ["", f"**Recommended focus:** {action}", "",
            "_Late = delivered after the scheduled delivery date. Freight from shipments with a recorded cost and weight._"]
    return "\n".join(out)
