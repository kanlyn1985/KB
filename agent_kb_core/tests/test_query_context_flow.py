from __future__ import annotations

from pathlib import Path

from agent_kb.context import build_context_pack
from agent_kb.domains import load_domain_pack
from agent_kb.projection import build_terminology_projections
from agent_kb.query import understand_query
from agent_kb.retrieval import build_retrieval_cards


ROOT = Path(__file__).resolve().parents[1]


def _obc_dcdc_pack():
    return load_domain_pack(ROOT / "domains" / "obc_dcdc")


def test_domain_aware_query_understanding_links_parameter_alias() -> None:
    pack = _obc_dcdc_pack()

    frame = understand_query("输出纹波怎么确认？", pack)

    assert frame.domain == "obc_dcdc"
    assert frame.intent == "test_method"
    assert frame.target_objects
    assert frame.target_objects[0].object_id == "DCDC_OUTPUT_RIPPLE"
    assert frame.answer_contract == "test_method"
    assert "test_method" in frame.preferred_fact_types
    assert "object_card" in frame.retrieval_channels


def test_constraint_query_surfaces_missing_project_and_condition_slots() -> None:
    pack = _obc_dcdc_pack()

    frame = understand_query("输出纹波要求是多少？", pack)

    assert frame.intent == "constraint_lookup"
    assert frame.target_objects[0].object_id == "DCDC_OUTPUT_RIPPLE"
    assert "project_or_customer" in frame.missing_slots
    assert "operating_condition" in frame.missing_slots
    assert frame.answer_strategy == "provide_general_context_and_ask_clarification"


def test_context_pack_injects_hidden_context_and_selects_card() -> None:
    pack = _obc_dcdc_pack()
    frame = understand_query("LV ripple 怎么测试？", pack)
    objects = build_terminology_projections(pack)
    cards = build_retrieval_cards(objects)

    context_pack = build_context_pack(
        query_frame=frame,
        domain_pack=pack,
        objects=objects,
        retrieval_cards=cards,
    )

    payload = context_pack.to_dict()
    assert payload["query_frame"]["target_objects"][0]["object_id"] == "DCDC_OUTPUT_RIPPLE"
    assert payload["target_objects"][0]["object_id"] == "DCDC_OUTPUT_RIPPLE"
    assert payload["retrieval_cards"][0]["object_id"] == "DCDC_OUTPUT_RIPPLE"
    assert any("示波器带宽" in line for line in payload["hidden_context"])
    assert "missing_slot" not in " ".join(payload["knowledge_gaps"])
