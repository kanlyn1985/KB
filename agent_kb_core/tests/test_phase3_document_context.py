from __future__ import annotations

from pathlib import Path

from agent_kb.domains.loader import load_domain_pack
from agent_kb.pipeline import build_context_pack_from_compilation, compile_text_to_context_pack
from agent_kb.core.compiler import compile_text_document


ROOT = Path(__file__).resolve().parents[1]


def test_compile_text_to_context_pack_selects_object_card_and_evidence() -> None:
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    result = compile_text_to_context_pack(
        "DCDC 输出纹波在额定负载下应不大于 30mVpp。\n\n输出纹波测试应使用示波器在低压输出端测量。",
        query="输出纹波要求是多少？",
        title="DCDC requirement sample",
        domain_pack=pack,
    )

    assert result.query_frame.target_objects[0].object_id == "DCDC_OUTPUT_RIPPLE"
    assert result.context_pack.target_objects[0].object_id == "DCDC_OUTPUT_RIPPLE"
    assert any(card.object_id == "DCDC_OUTPUT_RIPPLE" for card in result.context_pack.retrieval_cards)
    assert any(fact.subject == "DCDC_OUTPUT_RIPPLE" for fact in result.context_pack.facts)
    assert result.context_pack.evidence
    assert any("输出纹波" in item.snippet for item in result.context_pack.evidence)
    assert result.context_pack.hidden_context
    assert "missing_slot:project_or_customer" in result.context_pack.knowledge_gaps


def test_context_pack_can_be_built_from_precompiled_document() -> None:
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    compilation = compile_text_document(
        "LV ripple shall not exceed 30 mVpp under rated load.",
        title="English ripple requirement",
        domain_pack=pack,
    )
    result = build_context_pack_from_compilation(
        "LV ripple limit?",
        compilation,
        domain_pack=pack,
    )

    assert result.compiled_index.summary["facts"] >= 1
    assert result.compiled_index.summary["retrieval_cards"] >= 1
    assert result.context_pack.retrieval_cards
    assert result.context_pack.query_frame.target_objects[0].object_id == "DCDC_OUTPUT_RIPPLE"


def test_generic_pipeline_produces_context_without_domain_pack() -> None:
    result = compile_text_to_context_pack(
        "系统启动流程应包括上电、自检和状态确认。",
        query="系统启动流程有哪些？",
        title="Generic process",
    )

    assert result.compiled_index.summary["documents"] == 1
    assert result.compiled_index.summary["evidence_blocks"] >= 1
    assert result.context_pack.query_frame.domain is None
    assert result.context_pack.to_dict()["query_frame"]["intent"] in {"procedure", "general_search"}
