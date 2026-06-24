"""Router: classify a query and extract entity/target.

Pure function — no side effects, no DB access.
"""
from __future__ import annotations

import json
import re

from .types import RouteResult


# Only patterns that are 100% unambiguous
_FAST_PATH: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"0x[0-9A-Fa-f]{2}"), "service"),
    (re.compile(r"\b\d+(?:\.\d+)?\s*(ms|V|A|kV|mA|Hz|kHz|MHz|s|min|h|°C)\b"), "parameter"),
)

_ROUTER_PROMPT = """\
Classify this query about automotive engineering standards.

Return JSON: {"category": "...", "entity": "...", "target": "..."}

Categories:
- parameter: asks for a numeric value, OR asks to list attributes (有哪些/哪些/所有)
- definition: asks what an abbreviation or standard means
- reference: asks which standards a standard references or is referenced by
- traversal: asks about multi-hop relationships (N-hop, N 跳)
- service: asks about UDS diagnostic services (0xNN hex codes)
- free_form: open-ended questions needing prose context

Entity: the standard number, abbreviation, or name being asked about (null if none).
Target: the specific parameter, attribute, or service being asked about (null if none).

Return ONLY the JSON object."""


def route(query: str) -> RouteResult:
    """Classify a query and extract entity/target.

    Fast-path regex handles only unambiguous patterns. Everything
    else goes through LLM routing.
    """
    for pattern, category in _FAST_PATH:
        if pattern.search(query):
            # Fast-path only gives category — need LLM for entity/target
            llm = _llm_route(query)
            return RouteResult(
                category=category,
                entity=llm.get("entity") if isinstance(llm, dict) else None,
                target=llm.get("target") if isinstance(llm, dict) else None,
            )

    llm = _llm_route(query)
    if not isinstance(llm, dict):
        return RouteResult(category="free_form", entity=None, target=None)

    category = llm.get("category", "free_form")
    if category not in ("parameter", "definition", "reference", "traversal", "service", "free_form"):
        category = "free_form"

    return RouteResult(
        category=category,
        entity=llm.get("entity"),
        target=llm.get("target"),
    )


def _llm_route(query: str) -> dict | None:
    """Call LLM for routing. Returns None on failure (caller handles)."""
    from .legacy_bridge import llm_chat

    try:
        result = llm_chat(query, _ROUTER_PROMPT, max_tokens=1024)
    except Exception:
        return None

    result = result.strip()
    if result.startswith("```"):
        result = re.sub(r"^```(?:json)?\s*", "", result)
        result = re.sub(r"\s*```$", "", result)

    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return None
