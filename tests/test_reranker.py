from __future__ import annotations

from pathlib import Path

import pytest

from enterprise_agent_kb.query_rewrite import rewrite_query
from enterprise_agent_kb.reranker import rerank_candidates
from enterprise_agent_kb.retrieval_router import route_retrieval
from test_helpers import resolve_doc_id_by_filename


WORKSPACE = Path("knowledge_base")


def test_reranker_keeps_document_high_for_standard_lookup() -> None:
    doc_id = resolve_doc_id_by_filename("QC_T 1036", "逆变器")
    rewritten = rewrite_query("QC/T 1036—2016 的实施日期是什么？")
    routed = route_retrieval(WORKSPACE, rewritten, limit=12)
    reranked = rerank_candidates(WORKSPACE, rewritten, routed["hits"], limit=12)

    assert reranked
    assert reranked[0]["doc_id"] == doc_id
    assert "rerank" in reranked[0]
    assert "final_score" in reranked[0]["rerank"]


def _has_doc(filename_stem: str) -> bool:
    """Check whether a document with the given filename stem exists in the KB."""
    try:
        return bool(resolve_doc_id_by_filename(filename_stem, ".pdf"))
    except Exception:
        return False


@pytest.mark.skipif(
    not (_has_doc("V2G") and _has_doc("18487.1")),
    reason="V2G.pdf or 18487.1.pdf not in current knowledge_base",
)
def test_reranker_exposes_explanations_for_definition_query() -> None:
    doc_ids = {
        resolve_doc_id_by_filename("V2G", ".pdf"),
        resolve_doc_id_by_filename("18487.1", ".pdf"),
    }
    rewritten = rewrite_query("什么是V2G")
    routed = route_retrieval(WORKSPACE, rewritten, limit=12)
    reranked = rerank_candidates(WORKSPACE, rewritten, routed["hits"], limit=12)

    assert any(item["doc_id"] in doc_ids for item in reranked[:6])
    assert all("rerank" in item for item in reranked[:6])
