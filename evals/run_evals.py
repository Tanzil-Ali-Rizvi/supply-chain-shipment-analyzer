"""Evaluate the supply-chain assistant and the key statistical claim. Gates CI.

1. tool selection   the offline planner makes exactly the expected tool calls with the expected arguments
                    (questions.yaml gated; held_out.yaml reported, never tuned on)
2. grounding        every offline answer and all 43 country briefs pass the grounding check
3. tamper           altering any number in an answer must be caught by the grounding check
4. claim            "warehouse lines run late more often than direct lines in the same country, year and mode"
                    holds: Mantel-Haenszel odds ratio > 1 with permutation p < 0.01
Writes evals/results.json and evals/results.md; exits 1 if a gate fails.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shipiq import agent, metrics  # noqa: E402
from shipiq.tools import COUNTRIES, country_profile, worklist  # noqa: E402


def _norm_args(calls: list[dict]) -> list[dict]:
    return [{"tool": x["tool"], "args": {k: (None if v is None else str(v)) for k, v in x["args"].items()}} for x in calls]


def score_tools(cases: list[dict], misses: list[str]) -> tuple[int, int]:
    ok = 0
    for c in cases:
        got, exp = _norm_args(agent.plan(c["q"])), _norm_args(c["calls"])
        if got == exp:
            ok += 1
        else:
            misses.append(f"{c['q']} -> expected {exp}, got {got}")
    return ok, len(cases)


def tamper(text: str) -> list[tuple[str, str]]:
    """Every number altered once; returns (tampered_text, inserted_value)."""
    out = []
    for m in re.finditer(r"(?<![\w.-])\d[\d,]*(?:\.\d+)?", text):
        raw = m.group(0).replace(",", "")
        dec = len(raw.split(".")[1]) if "." in raw else 0
        new = f"{float(raw) * 1.1 + 1:.{dec}f}"
        out.append((text[:m.start()] + new + text[m.end():], new))
    return out


def main() -> int:
    qs = yaml.safe_load((ROOT / "evals" / "questions.yaml").read_text())
    ho = yaml.safe_load((ROOT / "evals" / "held_out.yaml").read_text())
    misses, ho_misses = [], []
    t_ok, t_n = score_tools(qs, misses)
    h_ok, h_n = score_tools(ho, ho_misses)

    g_ok = g_n = c_ok = c_n = collisions = 0
    for c in qs + ho:
        a = agent.ask(c["q"])
        g_n += 1
        g_ok += int(a.grounded)
        if not a.grounded:
            misses.append(f"ungrounded answer: {c['q']} {agent.check_grounding(a.text, a.results)}")
        allowed = set().union(*[agent._numbers(r) for r in a.results]) | agent.ALLOWED_CONSTANTS
        for bad, new in tamper(a.text):
            if agent._norm(new) in allowed:
                collisions += 1           # swapped to another legitimate value: undetectable by number matching
                continue
            c_n += 1
            c_ok += int(bool(agent.check_grounding(bad, a.results)))
    for country in COUNTRIES:
        brief = agent.country_brief(country)
        bad = agent.check_grounding(brief, [country_profile(country), worklist(country=country, n=5)])
        g_n += 1
        g_ok += int(not bad)
        if bad:
            misses.append(f"ungrounded brief {country}: {bad}")

    s = metrics.route_effect()
    claim_ok = s["p_value"] < 0.01 and s["odds_ratio"] > 1
    res = {
        "tool_selection": {"passed": t_ok, "total": t_n, "score": t_ok / t_n, "gate": 0.95},
        "grounding": {"passed": g_ok, "total": g_n, "score": g_ok / g_n, "gate": 1.0},
        "tamper_caught": {"passed": c_ok, "total": c_n, "score": c_ok / c_n, "gate": 1.0},
        "route_claim": {"passed": int(claim_ok), "total": 1, "score": float(claim_ok), "gate": 1.0, **s},
    }
    held = {"passed": h_ok, "total": h_n, "score": h_ok / h_n}
    passed = all(v["score"] >= v["gate"] for v in res.values())
    (ROOT / "evals" / "results.json").write_text(json.dumps(
        {"results": res, "held_out_tool_selection": held, "misses": misses, "held_out_misses": ho_misses,
         "tamper_collisions_skipped": collisions, "passed": passed}, indent=2, default=float))
    md = ["| Check | Result | CI gate |", "| --- | --- | --- |",
          f"| Tool selection (build set) | {t_ok}/{t_n} | 95% |",
          f"| Tool selection (held-out, never tuned) | {h_ok}/{h_n} | reported |",
          f"| Answers and country briefs grounded in tool results | {g_ok}/{g_n} | 100% |",
          f"| Tampered answers caught | {c_ok}/{c_n} | 100% |",
          f"| Route claim: warehouse vs direct lateness, same country, year and mode | odds ratio {s['odds_ratio']:.1f} "
          f"across {s['strata']} groups ({s['lines']:,} lines), permutation p = {s['p_value']:.3f} | p < 0.01 |"]
    md.append(f"\n{collisions} alterations that produced another legitimate value from the tool results were skipped "
              "(a number-matching check cannot detect them).")
    (ROOT / "evals" / "results.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    for x in misses:
        print("  MISS", x)
    for x in ho_misses:
        print("  HELD-OUT MISS", x)
    print("PASSED" if passed else "FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
