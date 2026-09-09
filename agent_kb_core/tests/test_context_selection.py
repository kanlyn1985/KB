# -*- coding: utf-8 -*-
"""P1/P2 回归测试：候选多样性封顶 + 卡选择 + 形态补槽行为契约。"""
from __future__ import annotations

from dataclasses import replace

from agent_kb.context.builder import fill_missing_shapes, select_retrieval_cards
from agent_kb.context.context_pack import ContextEvidence, ContextFact
from agent_kb.query.query_frame import QueryFrame, TargetObject
from agent_kb.retrieval.cards import RetrievalCard
from agent_kb.retrieval.hybrid import _enforce_diversity
from agent_kb.retrieval.models import RetrievalCandidate


# ---------------- P1: 候选多样性封顶 ----------------

def _cand(sid: str, stype: str = "fact", score: float = 1.0,
          subject: str | None = None) -> RetrievalCandidate:
    # 真实候选的分块信息在 source_id（如 fact:node:P-HW-OBC:table_row），
    # 归属对象在 payload.subject / object_id，是干净的节点 ID。
    owner = subject if subject is not None else sid.split(":")[0]
    return RetrievalCandidate(
        candidate_id=f"{stype}:{sid}",
        source_type=stype,
        source_id=sid,
        channel="test",
        score=score,
        matched_terms=[],
        reasons=[],
        payload={"subject": owner, "object_id": owner},
    )


def test_diversity_caps_same_object_shadows() -> None:
    cands = [
        _cand("fact:node:X", score=3.0, subject="X"),
        _cand("fact:node:X:procedure", score=2.9, subject="X"),
        _cand("fact:node:X:table_row", score=2.8, subject="X"),   # 同对象第 3 条
        _cand("Y:p", score=1.0),
        _cand("Z:q", score=0.9),
    ]
    kept = _enforce_diversity(cands, max_per_object=2)
    ids = [item.source_id for item in kept]
    assert "fact:node:X" in ids and "fact:node:X:procedure" in ids
    assert "fact:node:X:table_row" not in ids                      # 被封顶挤出
    assert "Y:p" in ids and "Z:q" in ids                           # 让位给后续对象


def test_diversity_keeps_unattributed_evidence() -> None:
    evd = RetrievalCandidate(
        candidate_id="evidence:e1", source_type="evidence", source_id="e1",
        channel="test", score=5.0, matched_terms=[], reasons=[], payload={},
    )
    kept = _enforce_diversity([evd], max_per_object=1)
    assert len(kept) == 1


# ---------------- P1b: ContextPack 卡选择 ----------------

def _card(cid: str, oid: str, chunk_of: str | None = None) -> RetrievalCard:
    return RetrievalCard(
        card_id=cid, domain="obc_dcdc", object_id=oid, card_type="P",
        title=cid, search_text=cid, aliases=[], related_object_ids=[chunk_of] if chunk_of else [],
        evidence_ids=[], answer_shapes=["general_search"],
        structured_payload={"chunk_of": chunk_of} if chunk_of else {},
        confidence=1.0,
    )


def test_select_cards_caps_and_backfills() -> None:
    cards = [
        _card("card:X#0", "X", chunk_of="X"),
        _card("card:X#1", "X", chunk_of="X"),
        _card("card:X#2", "X", chunk_of="X"),   # 同对象第 3 张被截
        _card("card:Y", "Y"),
        _card("card:W", "W"),
    ]
    picked = select_retrieval_cards(
        selected_card_ids=["card:X#0", "card:X#1", "card:X#2"],
        selected_object_ids=["Y", "W"],
        all_cards=cards,
        max_per_object=2,
    )
    ids = [c.card_id for c in picked]
    assert sum(1 for c in picked if c.object_id == "X") == 2
    assert "card:Y" in ids and "card:W" in ids and "card:X#2" not in ids


def test_select_cards_prefers_parent_over_chunk_for_fallback() -> None:
    cards = [
        _card("card:P#0", "P", chunk_of="P"),
        _card("card:P", "P"),
    ]
    picked = select_retrieval_cards(
        selected_card_ids=[],
        selected_object_ids=["P"],
        all_cards=cards,
    )
    assert [c.card_id for c in picked] == ["card:P"]


# ---------------- P2: 形态补槽 ----------------

def _frame(intent: str, query: str = "测试查询",
           targets: tuple[str, ...] = ("G-PROD-POTTING",)) -> QueryFrame:
    return QueryFrame(
        original_query=query,
        domain="obc_dcdc",
        intent=intent,
        intent_confidence=0.9,
        normalized_query=query,
        target_topic="",
        target_objects=[
            TargetObject(object_id=t, object_type="Process", canonical_name=t,
                         matched_text=t.split("-")[0], confidence=0.88)
            for t in targets
        ],
    )


def _fact(fid: str, ftype: str, subject: str, value: str, evds=None) -> ContextFact:
    return ContextFact(
        fact_id=fid, fact_type=ftype, subject=subject,
        predicate="describes", object_value=value,
        qualifiers={}, evidence_ids=list(evds or []), confidence=0.9,
    )


def test_fill_recovers_existing_shape_with_relevance() -> None:
    frame = _frame("procedure")
    all_facts = [
        _fact("f1", "term_definition", "G-PROD-POTTING", "灌封工艺流程说明"),
        _fact("f2", "procedure", "OTHER-NODE", "无关节点的过程描述"),
        _fact("f3", "procedure", "G-PROD-POTTING", "灌封工艺步骤描述"),
        _fact("f4", "procedure", "G-PROD-POTTING", "灌封注意事项A"),
        _fact("f5", "procedure", "G-PROD-POTTING", "灌封注意事项B"),  # 第 3 条被限流
    ]
    fill = fill_missing_shapes(frame, all_facts, [], selected_fact_ids={"f1"})
    assert set(fill.fact_ids) == {"f3", "f4"}
    assert fill.filled_shapes == ("procedure",)


def test_fill_refuses_offtopic_fill() -> None:
    frame = _frame("procedure")
    all_facts = [
        _fact("f1", "term_definition", "G-PROD-POTTING", "灌封工艺流程说明"),
        _fact("f2", "procedure", "UNRELATED-X", "无关节点的过程描述"),
    ]
    fill = fill_missing_shapes(frame, all_facts, [], selected_fact_ids={"f1"})
    assert fill.fact_ids == () and fill.evidence_ids == ()


def test_fill_skips_when_group_already_covered() -> None:
    frame = _frame("procedure")
    all_facts = [_fact("f1", "procedure", "G-PROD-POTTING", "灌封工艺步骤")]
    fill = fill_missing_shapes(frame, all_facts, [], selected_fact_ids={"f1"})
    assert not fill.fact_ids and not fill.evidence_ids


def test_fill_binds_evidence_but_not_duplicates() -> None:
    frame = _frame("constraint_lookup", targets=("R-PERF",))
    facts = [
        _fact("keep", "term_definition", "R-PERF", "纹波要求条目", ["evd-kept"]),
        _fact("row", "requirement_constraint", "R-PERF", "输出纹波要求不超过30mVpp", ["evd-9"]),
    ]
    all_evidence = [
        ContextEvidence(evidence_id="evd-9", document_id="doc-1", page_no=None, snippet="≤30mVpp"),
        ContextEvidence(evidence_id="evd-kept", document_id="doc-1", page_no=None, snippet="已选证据"),
    ]
    fill = fill_missing_shapes(
        frame, facts, all_evidence,
        selected_fact_ids={"keep"}, selected_evidence_ids={"evd-kept"},
    )
    assert fill.fact_ids == ("row",)
    assert fill.evidence_ids == ("evd-9",)


def test_fill_cjk_query_matches_chinese_content() -> None:
    frame = _frame("constraint_lookup", query="标定参数范围", targets=("L-CAL",))
    facts = [
        _fact("def1", "term_definition", "L-CAL", "标定参数管理逻辑说明"),
        _fact("c1", "parameter_constraint", "L-CAL", "标定参数降额曲线阈值范围定义"),
    ]
    fill = fill_missing_shapes(frame, facts, [], selected_fact_ids={"def1"})
    assert fill.fact_ids == ("c1",)
def test_graph_gate_opens_only_on_weak_strong_channels() -> None:
    """图通道门控：词法/向量双强时图不执行；双弱时放行（expAB 依据）。"""
    from agent_kb.retrieval.production import ProductionCandidateProvider

    class FakeProvider:
        def __init__(self, top_score: float, tag: str):
            self.top_score = top_score
            self.tag = tag
            self.calls = 0

        def search(self, query_frame, *, limit: int = 32):
            self.calls += 1
            return [
                RetrievalCandidate(
                    candidate_id=f"{self.tag}:hit", source_type="object",
                    source_id=f"{self.tag}_HIT", channel=self.tag,
                    score=self.top_score, matched_terms=[], reasons=[],
                    payload={"object_id": f"{self.tag}_HIT"},
                )
            ]

    frame = QueryFrame(
        original_query="q", domain="obc_dcdc", intent="general_search",
        intent_confidence=0.9, normalized_query="q", target_topic="",
        target_objects=[TargetObject(object_id="T", object_type="P",
                                     canonical_name="T", matched_text="t", confidence=0.9)],
    )

    # 双强：词法 2.5 / 向量 0.8 -> 门关，图不执行
    lex, vec, graph = FakeProvider(2.5, "lex"), FakeProvider(0.8, "vec"), FakeProvider(1.0, "graph")
    provider = ProductionCandidateProvider(lexical=lex, vector=vec, graph=graph)
    out = provider.search(frame, limit=5)
    assert graph.calls == 0
    ids = {c.source_id for c in out}
    assert "lex_HIT" in ids and "graph_HIT" not in ids

    # 双弱：词法 0.9 / 向量 0.3 -> 门开，图参与
    lex2, vec2, graph2 = FakeProvider(0.9, "lex"), FakeProvider(0.3, "vec"), FakeProvider(1.0, "graph")
    provider2 = ProductionCandidateProvider(lexical=lex2, vector=vec2, graph=graph2)
    out2 = provider2.search(frame, limit=5)
    assert graph2.calls == 1
    ids2 = {c.source_id for c in out2}
    assert "graph_HIT" in ids2

    # graph_gate=False 恢复裸三通道
    lex3, vec3, graph3 = FakeProvider(2.5, "lex"), FakeProvider(0.8, "vec"), FakeProvider(1.0, "graph")
    provider3 = ProductionCandidateProvider(lexical=lex3, vector=vec3, graph=graph3, graph_gate=False)
    provider3.search(frame, limit=5)
    assert graph3.calls == 1