from __future__ import annotations

from enterprise_agent_kb.query_rewrite import RewrittenQuery
from enterprise_agent_kb.retrieval_router import _structured_search_seeds


def test_constraint_search_seeds_skip_generic_requirement_terms() -> None:
    rewritten = RewrittenQuery(
        original_query="UDS on CAN services overview有哪些要求？",
        normalized_query="UDS on CAN services overview",
        query_type="constraint",
        target_topic="UDS on CAN services overview",
        aliases=[],
        must_terms=["UDS", "CAN", "UDS on CAN services overview"],
        should_terms=["要求", "requirement", "requirements", "shall"],
        negative_terms=[],
        protected_anchor_terms=["UDS", "CAN"],
        rewrite_override_applied=False,
        semantic_quality_flags=[],
    )

    assert _structured_search_seeds(rewritten) == ["UDS on CAN services overview", "UDS", "CAN"]
