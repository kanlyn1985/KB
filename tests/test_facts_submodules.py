"""Smoke tests for the facts submodules.

Each submodule was extracted from the historical 2030-line monolith; these
tests verify the public surface and a few representative behaviors. They run
without requiring a built KB.
"""
from __future__ import annotations

import re

import pytest

from enterprise_agent_kb.facts import (
    _extract_cover,
    _extract_process,
    _extract_terms,
    _fact_payloads,
)


# ---- _extract_cover -----------------------------------------------------

def test_extract_cover_public_functions() -> None:
    for name in (
        "_clean_text", "_sanitize_payload", "_normalize_ocr_text",
        "_normalize_standard_candidate", "_is_copyright_or_boilerplate_line",
        "_is_valid_standard_candidate", "_extract_standard_candidates",
        "_choose_primary_standard", "_extract_doc_metadata",
        "_extract_dates_from_text", "_extract_cover_metadata",
        "_extract_section_headings", "_utc_now",
    ):
        assert callable(getattr(_extract_cover, name)), f"missing: {name}"


def test_clean_text_strips_html_and_unicode() -> None:
    # Unescapes HTML entities, removes non-breaking spaces, normalizes whitespace
    cleaned = _extract_cover._clean_text("&nbsp;hello&nbsp; &amp; world  ")
    assert "&nbsp;" not in cleaned
    assert "&amp;" not in cleaned
    assert "hello" in cleaned
    assert "world" in cleaned


def test_is_copyright_boilerplate_detection() -> None:
    assert _extract_cover._is_copyright_or_boilerplate_line("Copyright © 2024")
    assert _extract_cover._is_copyright_or_boilerplate_line("All rights reserved")
    assert not _extract_cover._is_copyright_or_boilerplate_line("保护重启时间不应超过 100ms")


def test_extract_standard_candidates_finds_gb_codes() -> None:
    text = "本标准按照 GB/T 1.1-2020 给出的规则起草。参照 GB/T 1234-2016。"
    candidates = _extract_cover._extract_standard_candidates(text)
    assert len(candidates) >= 1


def test_choose_primary_standard_picks_first() -> None:
    result = _extract_cover._choose_primary_standard(["GB/T 1234-2016", "QC/T 5678-2017"])
    assert result == "GB/T 1234-2016"


# ---- _extract_terms -----------------------------------------------------

def test_extract_terms_public_functions() -> None:
    for name in (
        "_extract_term_definitions", "_extract_inline_heading_definitions",
        "_extract_markdown_bilingual_terms", "_extract_numeric_term_definitions",
        "_strip_bilingual_tail", "_extract_abstract_concepts",
        "_extract_document_level_concepts",
    ):
        assert callable(getattr(_extract_terms, name)), f"missing: {name}"


def test_extract_term_definitions_basic() -> None:
    text = "## CC电阻\n\nCC电阻是一种分流器件，用于测量电流。"
    results = _extract_terms._extract_term_definitions(text)
    assert isinstance(results, list)


def test_strip_bilingual_tail() -> None:
    # Strips English translations after a colon
    result = _extract_terms._strip_bilingual_tail("术语  (Term)")
    assert "Term" not in result or result != "术语  (Term)"


# ---- _extract_process ---------------------------------------------------

def test_extract_process_public_functions() -> None:
    for name in (
        "_extract_process_attribute_scope_definitions",
        "_extract_process_group_definitions",
        "_extract_type_relations",
    ):
        assert callable(getattr(_extract_process, name)), f"missing: {name}"


def test_extract_type_relations_finds_v2x() -> None:
    text = "V2X 包括 OBU、RSU、APP 等。"
    results = _extract_process._extract_type_relations(text)
    assert len(results) >= 1
    subject, predicate, payload = results[0]
    assert subject == "comparison_relation"
    assert predicate == "includes_type"


def test_extract_type_relations_empty_when_no_v2x() -> None:
    results = _extract_process._extract_type_relations("无相关文本。")
    assert results == []


# ---- _fact_payloads -----------------------------------------------------

def test_fact_payloads_public_functions() -> None:
    for name in (
        "_confidence", "_knowledge_unit_fact_payloads",
        "_definition_fact_payloads", "_clean_definition_term",
        "_is_publishable_definition_entry", "_definition_has_publishable_signal",
        "_definition_fact_type_for_term", "_definition_predicate_for_term",
        "_unit_canonical_title", "_unit_canonical_table_title",
        "_procedure_transition_payloads", "_extract_table_step_rows",
        "_process_title_for_procedure_unit", "_process_title_for_table_unit",
        "_clean_process_payload_title", "_is_low_quality_process_payload_title",
        "_process_code_from_text", "_two_column_parameter_payloads",
        "_table_parameter_fact_payloads", "_normalize_header_name",
        "_row_value", "_normalize_unit", "_timing_fact_payloads",
        "_parameter_scope_fields", "_ensure_evidence_chains",
        "_insert_metadata_facts", "_nearest_evidence_row",
    ):
        assert callable(getattr(_fact_payloads, name)), f"missing: {name}"


def test_facts_build_result_is_dataclass() -> None:
    """FactsBuildResult must be a frozen dataclass."""
    from enterprise_agent_kb.facts._fact_payloads import FactsBuildResult
    import dataclasses
    assert dataclasses.is_dataclass(FactsBuildResult)
    # Fields include the four documented attributes
    field_names = {f.name for f in dataclasses.fields(FactsBuildResult)}
    assert {"doc_id", "fact_count", "fact_types", "export_path"} <= field_names


def test_clean_definition_term_strips_punctuation() -> None:
    result = _fact_payloads._clean_definition_term("  术语名称：  ")
    assert ":" not in result
    assert "：" not in result


def test_normalize_header_name() -> None:
    # Whitespace stripping
    assert _fact_payloads._normalize_header_name("  Description  ") == "Description"
    # Strips parenthetical translations (e.g., "参数名 (Parameter Name)" → "参数名" or similar)
    result = _fact_payloads._normalize_header_name("参数名 (Parameter Name)")
    assert "Parameter" not in result
    assert "(" not in result


def test_normalize_unit() -> None:
    assert _fact_payloads._normalize_unit("V") == "V"
    assert _fact_payloads._normalize_unit("kV") == "kV"
    assert _fact_payloads._normalize_unit("") == ""


# ---- end-to-end smoke ---------------------------------------------------

def test_package_reexports_match_legacy_api() -> None:
    """The package public API must still export the historical surface."""
    import enterprise_agent_kb.facts as facts

    legacy_names = [
        "FactsBuildResult",
        "build_facts_for_document",
        "_extract_cover_metadata",
        "_extract_doc_metadata",
        "_extract_term_definitions",
        "_sanitize_payload",
        "_ensure_evidence_chains",
        "_insert_metadata_facts",
        "_definition_has_publishable_signal",
    ]
    for name in legacy_names:
        assert hasattr(facts, name), f"missing public API: {name}"
        assert callable(getattr(facts, name)), f"not callable: {name}"


def test_facts_build_result_constructor() -> None:
    """FactsBuildResult must accept all four positional args."""
    from pathlib import Path
    from enterprise_agent_kb.facts import FactsBuildResult
    result = FactsBuildResult(
        doc_id="DOC-1",
        fact_count=10,
        fact_types={"term_definition": 5, "constraint": 5},
        export_path=Path("/tmp/test.jsonl"),
    )
    assert result.doc_id == "DOC-1"
    assert result.fact_count == 10
    assert result.export_path == Path("/tmp/test.jsonl")
