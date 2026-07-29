"""Judgement orchestrator: rules first, optional LLM semantic fallback."""

from __future__ import annotations

from kb_ontology.judgement.models import Judgement
from kb_ontology.judgement.rules import judge_rules
from kb_ontology.judgement.semantic import refine_with_llm
from kb_ontology.llm.llm_client import LLMChatClient
from kb_ontology.query.frame import QueryResult


def judge(
    result: QueryResult,
    *,
    client: LLMChatClient | None = None,
    use_llm: bool = False,
    force_semantic: bool = False,
) -> Judgement:
    """Assess a QueryResult.

    Args:
        result: Template engine output.
        client: Optional LLM client for semantic refinement.
        use_llm: When true and (needs_semantic or force_semantic), call LLM.
        force_semantic: Call LLM even if rules say sufficient (tests/debug).
    """
    base = judge_rules(result)
    should_call = use_llm and client is not None and (base.needs_semantic or force_semantic)
    if not should_call:
        return base
    return refine_with_llm(result, base, client)
