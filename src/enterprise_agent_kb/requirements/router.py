from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .answer import answer_requirement_query
from .query import RequirementQueryPlanner

SUPPORTED_ROUTED_INTENTS = {
    "requirement_effective",
    "requirement_diff",
    "requirement_conflict_scan",
}


def requirement_router_enabled() -> bool:
    """Return whether the experimental requirement router is enabled.

    The router is deliberately opt-in. This prevents requirement MVP behavior from
    changing the existing answer chain until the resolver has been validated with
    project data and golden cases.
    """
    return os.getenv("EAKB_ENABLE_REQUIREMENT_ROUTER", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def try_answer_requirement_query(
    root: Path,
    query: str,
    *,
    min_confidence: float = 0.75,
) -> dict[str, Any] | None:
    """Soft-route a query to the requirement resolver when safe.

    Returns None when the router is disabled, the requirement schema is missing,
    the intent is not one of the deterministic MVP intents, or the planner is not
    confident enough. This is designed to be called at the beginning of
    answer_api.answer_query without disturbing non-requirement questions.
    """
    if not requirement_router_enabled():
        return None

    planner = RequirementQueryPlanner.from_root(root)
    plan = planner.plan(query)
    if plan.intent not in SUPPORTED_ROUTED_INTENTS:
        return None
    if plan.confidence < min_confidence:
        return None

    payload = answer_requirement_query(root, query)
    return {
        "answer_mode": plan.intent,
        "direct_answer": payload.get("direct_answer", ""),
        "requirement_answer": payload,
        "supporting_facts": [],
        "supporting_evidence": [],
        "related_graph_edges": [],
        "related_wiki_pages": [],
        "warnings": [
            "requirement_router_mvp: answered by deterministic Requirement Resolver; "
            "existing generic answer chain was bypassed for this query only."
        ],
        "context": {
            "requirement_router": {
                "enabled": True,
                "intent": plan.intent,
                "confidence": plan.confidence,
                "project_id": plan.project_id,
                "atom_id": plan.atom_id,
                "base_profile_id": plan.base_profile_id,
            }
        },
    }
