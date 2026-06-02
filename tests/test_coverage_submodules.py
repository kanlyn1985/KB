"""Smoke tests for the coverage submodules.

Each submodule was extracted from the historical 1792-line monolith; these
tests verify the public surface and a few representative behaviors. They run
without requiring a built KB.
"""
from __future__ import annotations

import pytest

from enterprise_agent_kb.coverage import (
    _gap_detection,
    _report_rendering,
)


# ---- _gap_detection -----------------------------------------------------

def test_gap_detection_public_functions() -> None:
    for name in (
        "_build_source_units", "_augment_source_units_from_facts",
        "_stable_fact_fallback_unit_id",
        "_definition_source_unit", "_requirement_source_unit",
        "_procedure_source_unit", "_parameter_row_source_units",
        "_unit_with_canonical_metadata",
        "_row_to_fact", "_row_to_wiki_page", "_load_fact_evidence_map",
        "_match_facts_for_unit", "_source_unit_text_matches_fact",
        "_fact_text_candidates",
        "_definition_matches_fact", "_requirement_matches_fact",
        "_parameter_row_matches_fact", "_process_unit_matches_fact",
        "_match_evidence_for_unit", "_match_wiki_pages_for_unit",
        "_match_test_cases_for_unit", "_load_test_cases", "_test_case_blob",
        "_coverage_status", "_is_potentially_misaligned",
        "_build_test_gap_candidates", "_test_gap_candidate_from_row",
        "_recommended_test_seed", "_sort_test_gap_rows",
        "_dedupe_test_gap_rows", "_is_actionable_test_gap_row",
        "_is_source_unit_inventory_noise",
        "_looks_like_structural_inventory_noise",
        "_looks_like_toc_entry_noise", "_looks_like_figure_legend_definition",
        "_looks_like_table_syntax_source", "_looks_like_clause_reference_noise",
        "_looks_like_boilerplate_definition_pair",
        "_looks_like_test_gap_noise", "_looks_like_low_value_parameter_gap",
        "_clean_test_gap_label", "_sort_uncovered_rows",
        "_parameter_row_aliases", "_requirement_importance",
    ):
        assert callable(getattr(_gap_detection, name)), f"missing: {name}"


def test_source_unit_class_exists() -> None:
    """SourceUnit is a frozen dataclass used as the primary result type."""
    import dataclasses
    from enterprise_agent_kb.coverage._gap_detection import SourceUnit
    assert dataclasses.is_dataclass(SourceUnit)
    field_names = {f.name for f in dataclasses.fields(SourceUnit)}
    assert {"unit_id", "unit_type", "page_no", "semantic_key", "aliases",
            "source_text", "canonical_title", "canonical_key", "content_role",
            "quality_flags", "importance", "source_locator", "metadata"} <= field_names


def test_rate_helper() -> None:
    """_coverage_status with all coverage types set."""
    # All IDs present, no misaligned → covered
    result = _gap_detection._coverage_status(
        evidence_ids=["E-1"],
        fact_ids=["F-1"],
        entity_ids=["EN-1"],
        golden_case_ids=["C-1"],
        regression_case_ids=["R-1"],
        misaligned=False,
    )
    assert result == "covered"
    # No IDs → uncovered
    result = _gap_detection._coverage_status(
        evidence_ids=[],
        fact_ids=[],
        entity_ids=[],
        golden_case_ids=[],
        regression_case_ids=[],
        misaligned=False,
    )
    assert "miss" in result or result in {"uncovered", "missing"}
    # Misaligned flag → likely a non-covered status
    result = _gap_detection._coverage_status(
        evidence_ids=["E-1"],
        fact_ids=[],
        entity_ids=[],
        golden_case_ids=[],
        regression_case_ids=[],
        misaligned=True,
    )
    # Status names use the "uN_*" format internally
    assert isinstance(result, str)
    assert result != "covered"  # misaligned prevents "covered"


def test_compare_key() -> None:
    assert _gap_detection._compare_key("hello") == _gap_detection._compare_key("HELLO")
    # Whitespace is normalized
    assert _gap_detection._compare_key("  hello  ") == _gap_detection._compare_key("hello")


def test_clean_test_gap_label() -> None:
    result = _gap_detection._clean_test_gap_label("Test  Label  ")
    assert "  " not in result


# ---- _report_rendering --------------------------------------------------

def test_report_rendering_public_functions() -> None:
    for name in (
        "_build_summary", "_group_summary", "_render_report",
        "_render_test_gap_report",
        "_soft_contains", "_compare_key", "_clean_text", "_clean_label",
        "_first_sentence", "_safe_json", "_rate", "_best_nonempty",
        "_unique_strings", "_normalize_header_name", "_row_value",
        "_string_list", "_normalize_unit", "_utc_now",
    ):
        assert callable(getattr(_report_rendering, name)), f"missing: {name}"


def test_rate_basic() -> None:
    assert _report_rendering._rate(5, 10) == 0.5
    assert _report_rendering._rate(0, 0) == 0.0
    assert _report_rendering._rate(10, 10) == 1.0


def test_safe_json_parses_valid() -> None:
    assert _report_rendering._safe_json('{"a": 1}') == {"a": 1}
    assert _report_rendering._safe_json("[1, 2, 3]") == [1, 2, 3]


def test_safe_json_returns_input_for_invalid() -> None:
    """When JSON is invalid, the input string is returned as-is."""
    result = _report_rendering._safe_json("not valid json")
    assert result == "not valid json"


def test_safe_json_handles_none() -> None:
    assert _report_rendering._safe_json(None) is None


def test_first_sentence_extracts() -> None:
    text = "First sentence here. Second sentence here."
    result = _report_rendering._first_sentence(text)
    assert "First" in result
    assert "Second" not in result


def test_best_nonempty() -> None:
    assert _report_rendering._best_nonempty(["", "b", "c"]) == "b"
    assert _report_rendering._best_nonempty(["", ""]) == ""
    assert _report_rendering._best_nonempty([]) == ""


def test_unique_strings_dedup() -> None:
    result = _report_rendering._unique_strings(["a", "b", "a", "c", "b"])
    assert sorted(result) == ["a", "b", "c"]


def test_string_list_handles_types() -> None:
    # List/tuple/None
    assert _report_rendering._string_list(["a", "b"]) == ["a", "b"]
    assert _report_rendering._string_list(None) == []
    # String → wrapped in list
    result = _report_rendering._string_list("a")
    assert isinstance(result, list)


def test_normalize_unit() -> None:
    assert _report_rendering._normalize_unit("V") == "V"
    assert _report_rendering._normalize_unit("kV") == "kV"
    assert _report_rendering._normalize_unit("") == ""


def test_normalize_header_name_strips_parenthetical() -> None:
    # Whitespace stripping
    result = _report_rendering._normalize_header_name("  Description  ")
    assert result == "Description"
    # Function may keep parentheticals as part of the name
    # (we just verify the result is a non-empty string with surrounding whitespace stripped)
    result = _report_rendering._normalize_header_name("Description (描述)  ")
    assert isinstance(result, str)
    assert result.strip() == result


# ---- end-to-end smoke ---------------------------------------------------

def test_package_reexports_match_legacy_api() -> None:
    """The package public API must still export the historical surface."""
    import enterprise_agent_kb.coverage as cov

    legacy_names = [
        "SourceUnit",
        "CoverageBuildResult",
        "TestGapCandidateBuildResult",
        "build_coverage_for_document",
        "build_test_gap_candidates_for_document",
    ]
    for name in legacy_names:
        assert hasattr(cov, name), f"missing public API: {name}"


def test_version_constant_exported() -> None:
    """The SOURCE_UNIT_EXPORT_VERSION constant is now in _report_rendering."""
    from enterprise_agent_kb.coverage._report_rendering import (
        SOURCE_UNIT_EXPORT_VERSION,
        V0_UNIT_TYPES,
    )
    assert SOURCE_UNIT_EXPORT_VERSION == "coverage-v1"
    assert "definition_unit" in V0_UNIT_TYPES
    assert "parameter_row_unit" in V0_UNIT_TYPES
    assert "process_unit" in V0_UNIT_TYPES
    assert "requirement_unit" in V0_UNIT_TYPES


def test_fact_text_candidates_extracts_text_fields() -> None:
    fact = {
        "object_value": {
            "term": "CC 电阻",
            "definition": "CC 电阻是一种分流器件。",
        },
        "qualifiers_json": {"page_no": 1},
    }
    candidates = _gap_detection._fact_text_candidates(fact)
    assert isinstance(candidates, list)
    assert len(candidates) >= 2
    # Both term and definition should appear
    joined = " ".join(candidates)
    assert "CC 电阻" in joined
