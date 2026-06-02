from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb import answer_api
from enterprise_agent_kb.answer_definition import _select_definition_answer_facts, _definition_answer_needs_section_fallback
from enterprise_agent_kb.facts import _extract_cover_metadata, _extract_doc_metadata
from enterprise_agent_kb.generated_tests import (
    _case,
    _is_low_value_evidence_text,
    _is_usable_golden_anchor,
    _is_valid_standard_code,
)
from enterprise_agent_kb.query_rewrite import rewrite_query


def test_rewrite_keeps_iso_part_number_as_standard_lookup() -> None:
    rewritten = rewrite_query("ISO 14229-1是什么标准")

    assert rewritten.query_type == "standard_lookup"
    assert rewritten.normalized_query == "ISO14229—1"
    assert "ISO 14229-1" in rewritten.must_terms


def test_rewrite_keeps_lowercase_english_term_phrase() -> None:
    rewritten = rewrite_query("diagnostic data是什么")

    assert rewritten.query_type == "definition"
    assert rewritten.normalized_query == "diagnostic data"
    assert rewritten.target_topic == "diagnostic data"
    assert "iagnostic" not in rewritten.protected_anchor_terms


def test_rewrite_removes_standard_scope_for_english_term_definition() -> None:
    rewritten = rewrite_query("ISO 14229-1里的 diagnostic service 是什么")

    assert rewritten.query_type == "definition"
    assert rewritten.normalized_query == "diagnostic service"
    assert rewritten.target_topic == "diagnostic service"
    assert "diagnostic service" in rewritten.must_terms


def test_definition_fact_selection_prefers_exact_definition_shape_over_section_heading() -> None:
    facts = [
        {
            "fact_id": "FACT-SECTION",
            "fact_type": "section_heading",
            "confidence": 0.99,
            "_subgraph_bonus": 10.0,
            "object_value": {"title": "diagnostic data"},
        },
        {
            "fact_id": "FACT-TERM",
            "fact_type": "term_definition",
            "confidence": 0.77,
            "object_value": {
                "term": "diagnostic data",
                "definition": "data that is located in the memory of an electronic control unit",
            },
        },
    ]

    selected = _select_definition_answer_facts(
        facts,
        knowledge_subgraph={},
        query="diagnostic data是什么",
        rewritten_payload={"target_topic": "diagnostic data", "must_terms": ["diagnostic data"]},
    )

    assert selected[0]["fact_id"] == "FACT-TERM"


def test_generated_local_cases_carry_contract_evidence_shapes() -> None:
    standard = _case("standard", "ISO 14229-1是什么标准", "ISO 14229-1", source="local", assert_mode="context_contains")
    definition = _case("definition", "什么是diagnostic data", "diagnostic data", source="local", assert_mode="context_contains")
    requirement = _case("coverage_requirement", "有哪些要求", "shall", source="coverage", assert_mode="context_contains")

    assert standard["expected_evidence_shape"] == "standard_metadata"
    assert definition["expected_evidence_shape"] == "term_definition"
    assert requirement["expected_evidence_shape"] == "requirement"


def test_standard_metadata_uses_filename_and_ignores_copyright_year() -> None:
    filename = (
        "182-ISO 14229-1-2013 Road vehicles -- Unified diagnostic services "
        "(UDS) -- Part 1 Specification and requirements.pdf"
    )
    cover_text = (
        "Second edition 2013-03-15\n\n"
        "Road vehicles -- Unified diagnostic services (UDS) --\n\n"
        "Part 1: Specification and requirements"
    )
    copyright_text = "## COPYRIGHT PROTECTED DOCUMENT\n\n## © ISO 2013\n\nAll rights reserved."

    cover_metadata = _extract_cover_metadata(cover_text, filename)
    copyright_metadata = _extract_doc_metadata(copyright_text, filename)

    assert ("document_standard", "standard_code", {"value": "ISO 14229-1—2013"}) in cover_metadata
    assert ("document_standard", "standard_code", {"value": "ISO 14229-1—2013"}) in copyright_metadata
    assert all(item[2].get("value") != "ISO 2013" for item in [*cover_metadata, *copyright_metadata])


def test_golden_generation_rejects_standard_boilerplate() -> None:
    assert _is_valid_standard_code("ISO 14229-1—2013")
    assert not _is_valid_standard_code("ISO 2013")
    assert _is_low_value_evidence_text("## COPYRIGHT PROTECTED DOCUMENT\n## © ISO 2013\nAll rights reserved.")
    assert not _is_usable_golden_anchor("1 2 Normative references .....")
    assert not _is_usable_golden_anchor("International Standards are drafted in accordance with ISO rules")


def test_answer_query_keeps_standard_answer_when_document_standard_fact_present(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """When a document_standard fact exists, the system should still answer
    with the standard code even if evidence_judgement says insufficient,
    because the standard code itself is the core answer for a standard_lookup query."""
    def fake_context(*args, **kwargs):
        return {
            "query": "ISO 14229-1是什么标准",
            "rewrite": {
                "original_query": "ISO 14229-1是什么标准",
                "normalized_query": "ISO14229—1",
                "query_type": "standard_lookup",
                "target_topic": "ISO14229—1",
                "aliases": ["ISO 14229-1"],
                "must_terms": ["ISO14229—1", "ISO", "ISO 14229-1"],
                "should_terms": [],
                "negative_terms": [],
                "protected_anchor_terms": [],
                "rewrite_override_applied": False,
                "semantic_quality_flags": [],
            },
            "hit_count": 1,
            "documents": [],
            "hits": [],
            "evidence": [],
            "facts": [
                {
                    "fact_id": "FACT-STANDARD",
                    "fact_type": "document_standard",
                    "predicate": "standard_code",
                    "object_value": {"value": "ISO 14229-1—2013"},
                    "confidence": 0.9,
                    "source_doc_id": "DOC-TEST",
                    "qualifiers_json": {"page_no": 1},
                }
            ],
            "entities": [],
            "graph_edges": [],
            "wiki_pages": [],
            "knowledge_subgraph": {},
            "evidence_judgement": {
                "sufficient": False,
                "rejected_reasons": ["缺少标准用途、适用范围和完整标题证据。"],
                "shape_diagnostics": {
                    "shape_contract": {
                        "allowed_shapes": ["term_definition"],
                    }
                },
            },
        }

    monkeypatch.setattr(answer_api, "build_query_context", fake_context)
    monkeypatch.setattr(answer_api, "_select_supporting_evidence", lambda *args, **kwargs: [])

    answer = answer_api.answer_query(tmp_path, "ISO 14229-1是什么标准", limit=4)

    # With document_standard fact present, the system keeps the answer
    assert answer["fallback_reason"] != "insufficient_evidence"
    assert "ISO 14229-1" in answer["direct_answer"]


def test_answer_query_downgrades_standard_answer_when_no_document_standard_fact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """When no document_standard fact exists and evidence_judgement says
    insufficient, the system should downgrade to insufficient_evidence."""
    def fake_context(*args, **kwargs):
        return {
            "query": "ISO 14229-1是什么标准",
            "rewrite": {
                "original_query": "ISO 14229-1是什么标准",
                "normalized_query": "ISO14229—1",
                "query_type": "standard_lookup",
                "target_topic": "ISO14229—1",
                "aliases": ["ISO 14229-1"],
                "must_terms": ["ISO14229—1", "ISO", "ISO 14229-1"],
                "should_terms": [],
                "negative_terms": [],
                "protected_anchor_terms": [],
                "rewrite_override_applied": False,
                "semantic_quality_flags": [],
            },
            "hit_count": 0,
            "documents": [],
            "hits": [],
            "evidence": [],
            "facts": [],
            "entities": [],
            "graph_edges": [],
            "wiki_pages": [],
            "knowledge_subgraph": {},
            "evidence_judgement": {
                "sufficient": False,
                "rejected_reasons": ["缺少标准用途、适用范围和完整标题证据。"],
                "shape_diagnostics": {
                    "shape_contract": {
                        "allowed_shapes": ["term_definition"],
                    }
                },
            },
        }

    monkeypatch.setattr(answer_api, "build_query_context", fake_context)
    monkeypatch.setattr(answer_api, "_select_supporting_evidence", lambda *args, **kwargs: [])

    answer = answer_api.answer_query(tmp_path, "ISO 14229-1是什么标准", limit=4)

    assert answer["fallback_reason"] == "insufficient_evidence"
    assert "当前候选证据不足以给出确定性答案" in answer["direct_answer"]
    assert answer["supporting_facts"] == []


def test_definition_selection_matches_english_term_case_insensitively() -> None:
    facts = [
        {
            "fact_id": "F-LOCAL",
            "fact_type": "term_definition",
            "predicate": "defines_term",
            "object_value": {"term": "local client", "definition": "nearby definition"},
            "confidence": 0.8,
            "source_doc_id": "DOC-TEST",
        },
        {
            "fact_id": "F-CLIENT",
            "fact_type": "term_definition",
            "predicate": "defines_term",
            "object_value": {"term": "client", "definition": "function that is part of the tester"},
            "confidence": 0.8,
            "source_doc_id": "DOC-TEST",
        },
    ]

    selected = _select_definition_answer_facts(
        facts,
        {},
        "client是什么",
        {"target_topic": "CLIENT", "must_terms": ["CLIENT", "client"], "aliases": []},
    )

    assert selected[0]["fact_id"] == "F-CLIENT"


def test_definition_selection_ignores_markdown_wrapping_on_terms() -> None:
    facts = [
        {
            "fact_id": "F-SECTION",
            "fact_type": "section_heading",
            "predicate": "has_section",
            "object_value": {"title": "vehicle connector"},
            "confidence": 0.99,
            "source_doc_id": "DOC-TEST",
        },
        {
            "fact_id": "F-TERM",
            "fact_type": "term_definition",
            "predicate": "defines_term",
            "object_value": {
                "term": "**vehicle connector**",
                "definition": "**electric vehicle connector** part of a vehicle coupler",
            },
            "confidence": 0.77,
            "source_doc_id": "DOC-TEST",
        },
    ]

    selected = _select_definition_answer_facts(
        facts,
        {},
        "什么是vehicle connector？",
        {"target_topic": "vehicle connector", "must_terms": ["vehicle connector"], "aliases": []},
    )

    assert selected[0]["fact_id"] == "F-TERM"
    assert not _definition_answer_needs_section_fallback(
        selected,
        {"target_topic": "vehicle connector"},
    )
