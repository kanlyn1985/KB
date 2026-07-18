from __future__ import annotations

from pathlib import Path

from agent_kb.core.compiler import compile_text_document
from agent_kb.domains.loader import load_domain_pack
from agent_kb.evaluation import RetrievalGoldenCase, evaluate_retrieval
from agent_kb.pipeline import build_compiled_knowledge_index, compile_text_to_context_pack
from agent_kb.query.understanding import understand_query
from agent_kb.retrieval import retrieve


ROOT = Path(__file__).resolve().parents[1]


def _compiled_index():
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    text = (
        "DCDC 输出纹波在额定负载下应不大于 30mVpp。该限值用于低压输出质量判定。\n\n"
        "DCDC 转换效率在额定输入和额定输出条件下应不小于 94%。该指标需保留测试工况。"
    )
    compilation = compile_text_document(
        text,
        title="DCDC retrieval sample",
        domain_pack=pack,
        max_evidence_chars=90,
    )
    return pack, build_compiled_knowledge_index(compilation, domain_pack=pack)


def test_multichannel_retrieval_prioritizes_linked_object() -> None:
    pack, index = _compiled_index()
    frame = understand_query("输出纹波要求是多少？", domain_pack=pack)
    result = retrieve(frame, index, top_k=8)

    assert result.candidates
    assert "DCDC_OUTPUT_RIPPLE" in result.selected_object_ids
    assert any(candidate.payload.get("object_id") == "DCDC_OUTPUT_RIPPLE" for candidate in result.candidates[:3])
    assert result.selected_fact_ids
    assert result.selected_evidence_ids
    assert "object_card" in result.diagnostics.executed_channels
    assert result.diagnostics.skipped_channels.get("graph") == "channel_not_materialized_in_phase4_index"


def test_document_context_uses_retrieval_subset() -> None:
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    result = compile_text_to_context_pack(
        "DCDC 输出纹波在额定负载下应不大于 30mVpp。\n\nDCDC 转换效率应不小于 94%。",
        query="输出纹波限值是多少？",
        title="DCDC subset sample",
        domain_pack=pack,
        max_evidence_chars=70,
        retrieval_top_k=6,
    )

    assert result.retrieval_result.candidates
    assert result.context_pack.target_objects
    assert result.context_pack.target_objects[0].object_id == "DCDC_OUTPUT_RIPPLE"
    assert any(fact.subject == "DCDC_OUTPUT_RIPPLE" for fact in result.context_pack.facts)
    assert all("输出纹波" in evidence.snippet for evidence in result.context_pack.evidence)


def test_golden_retrieval_evaluation_reports_hit_and_recall() -> None:
    pack, index = _compiled_index()
    ripple_fact = next(fact for fact in index.context_facts if fact.subject == "DCDC_OUTPUT_RIPPLE")
    ripple_evidence_id = ripple_fact.evidence_ids[0]
    case = RetrievalGoldenCase(
        case_id="ripple-constraint",
        query="LV ripple limit?",
        expected_object_ids=["DCDC_OUTPUT_RIPPLE"],
        expected_fact_ids=[ripple_fact.fact_id],
        expected_evidence_ids=[ripple_evidence_id],
        top_k=6,
    )

    report = evaluate_retrieval([case], index, domain_pack=pack)

    assert report.case_count == 1
    assert report.hit_at_k == 1.0
    assert report.mean_reciprocal_rank > 0.0
    assert report.mean_object_recall == 1.0
    assert report.mean_fact_recall == 1.0
    assert report.mean_evidence_recall == 1.0
