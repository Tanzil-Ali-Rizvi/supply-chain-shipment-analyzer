"""Minimal client for any OpenAI-compatible chat endpoint with tool calling.

Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL. With none set, the agent uses its offline planner.
"""
from __future__ import annotations

import json
import os
import urllib.request


def enabled() -> bool:
    return bool(os.getenv("LLM_BASE_URL") and os.getenv("LLM_MODEL"))


def chat(messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.0, timeout: int = 60) -> dict:
    """Return the assistant message dict (may contain `tool_calls`)."""
    body = {"model": os.environ["LLM_MODEL"], "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {os.getenv('LLM_API_KEY', 'none')}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)["choices"][0]["message"]
