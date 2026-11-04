import json

from shipiq import agent, llm
from shipiq.tools import match_country, match_vendors


def test_country_aliases():
    assert match_country("Tell me about Ivory Coast") == "Côte d'Ivoire"
    assert match_country("deliveries in the DRC") == "Congo, DRC"
    assert match_country("How is it going?") is None


def test_vendor_prefers_the_scored_name():
    assert match_vendors("How does Aurobindo perform?") == ["Aurobindo Pharma Limited"]


def test_scenario_thresholds_are_parsed():
    assert agent.plan("What if air shipments over 3 t planned 120 days ahead went by sea?") == [
        {"tool": "mode_shift_scenario", "args": {"min_kg": 3000.0, "min_plan_days": 120.0}}]


def test_offline_answers_are_grounded():
    for qn in ["How did the supply chain perform overall?", "How is Zambia doing?", "Is the warehouse route slower?", "What does freight cost by mode?"]:
        a = agent.ask(qn)
        assert a.mode == "offline" and a.grounded, qn


def test_grounding_catches_an_invented_number():
    a = agent.ask("Is the warehouse route slower than direct shipping?")
    assert "17.2%" in a.text
    assert agent.check_grounding(a.text.replace("17.2%", "12.7%"), a.results) == ["12.7"]


def test_country_brief_recommends_warehouse_fix_where_it_dominates():
    assert "warehouse replenishment" in agent.country_brief("Mozambique")
    assert "direct-from-vendor lane" in agent.country_brief("South Africa")


def test_llm_hallucination_falls_back_to_template(monkeypatch):
    def fake(messages, tools=None, **kw):
        if not any(mm.get("role") == "tool" for mm in messages):
            return {"role": "assistant", "content": None, "tool_calls": [
                {"id": "1", "type": "function", "function": {"name": "network_summary", "arguments": "{}"}}]}
        return {"role": "assistant", "content": "On-time delivery improved to 96% last year."}

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "chat", fake)
    a = agent.ask("how are we doing overall?")
    assert a.mode == "llm-fallback" and "96" in a.ungrounded and "88.5%" in a.text


def test_llm_grounded_answer_is_kept(monkeypatch):
    def fake(messages, tools=None, **kw):
        tool_msgs = [mm for mm in messages if mm.get("role") == "tool"]
        if not tool_msgs:
            return {"role": "assistant", "content": None, "tool_calls": [
                {"id": "1", "type": "function", "function": {"name": "country_profile", "arguments": json.dumps({"country": "Haiti"})}}]}
        r = json.loads(tool_msgs[0]["content"])
        return {"role": "assistant", "content": f"Haiti: {r['late_pct']}% of lines arrived late."}

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "chat", fake)
    a = agent.ask("How is Haiti doing?")
    assert a.mode == "llm" and "9.5%" in a.text
