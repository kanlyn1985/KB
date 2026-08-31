# -*- coding: utf-8 -*-
"""答案层契约门 + 5 黄金问题事实锚点（确定性，零 LLM token）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "validation"))

from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.embeddings import HashEmbeddingProvider  # noqa: E402
from agent_kb.pipeline.production_context import query_production_store  # noqa: E402

DB = ROOT / "validation" / "node-index.sqlite3"
DOMAIN = ROOT / "domains" / "obc_dcdc"

# 生产库（318MB）不入 git，CI 沙箱没有 —— 无库则整组跳过（本地必跑）。
pytestmark = pytest.mark.skipif(
    not DB.exists(),
    reason="production node-index.sqlite3 not available (not in git)",
)

GOLDEN_ANCHORS = [
    ("DCDC保护功能有哪些", "sufficient", ["过压", "过温", "短路"], 2),
    ("输出纹波要求是多少", "partial", ["mV", "纹波"], 1),
    ("HARA分析怎么做", "sufficient", ["HARA", "功能安全", "严重度"], 1),
    ("OBC和DCDC的区别", "partial", ["DCDC", "OBC"], 1),  # comparison shape 组库内缺位（语料空洞，诚实 partial）
    ("灌封胶有什么要求", "partial", ["灌封", "三防"], 1),
]


def _production_pack(query: str):
    domain_pack = load_domain_pack(DOMAIN)
    return query_production_store(
        query, db_path=DB, domain_pack=domain_pack,
        embedding_provider=HashEmbeddingProvider(),
    )


@pytest.mark.parametrize("query,want_status,anchors,min_hits", GOLDEN_ANCHORS)
def test_answer_contract_and_fact_anchors(query, want_status, anchors, min_hits):
    result = _production_pack(query)
    pack = result.context_pack
    judgement = result.evidence_judgement

    assert judgement.status == want_status, (
        f"{query}: 判定 {judgement.status} != 预期 {want_status} (score={judgement.score})")

    if want_status == "sufficient":
        assert pack.evidence, f"{query}: sufficient 但证据包为空"
        assert all(e.evidence_id for e in pack.evidence), f"{query}: 存在无 evidence_id 的证据"

    if want_status == "partial":
        strategy = pack.recommended_answer_strategy
        assert ("caution" in strategy or "clarification" in strategy
                or pack.knowledge_gaps), (
            f"{query}: partial 但无缺口披露 (strategy={strategy}, gaps={pack.knowledge_gaps})")

    evidence_text = " ".join(item.snippet for item in pack.evidence)
    fact_text = " ".join(str(f.object_value) for f in pack.facts)
    card_text = " ".join(c.search_text for c in pack.retrieval_cards)
    blob = f"{evidence_text} {fact_text} {card_text}".lower()
    hits = sum(1 for a in anchors if a.lower() in blob)
    assert hits >= min_hits, (
        f"{query}: 事实锚点 {hits}/{min_hits} 未达标，需要 {anchors}")


def test_sufficient_never_abstains():
    result = _production_pack("HARA分析怎么做")
    strategy = result.context_pack.recommended_answer_strategy
    assert strategy not in {"ask_clarification_or_abstain",
                            "ask_clarification_with_candidate_interpretations"}, (
        f"sufficient 但策略为弃答类: {strategy}")


def test_partial_discloses_gaps():
    result = _production_pack("输出纹波要求是多少")
    pack = result.context_pack
    assert pack.warnings or pack.knowledge_gaps, "partial 但无任何披露信息"