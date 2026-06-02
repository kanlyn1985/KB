"""Smoke tests for the generated_tests submodules.

Each submodule was extracted from the historical 3392-line monolith; these
tests verify the public surface and a few representative behaviors. They run
without requiring a built KB.
"""
from __future__ import annotations

import pytest

from enterprise_agent_kb.generated_tests import (
    _case_helpers,
    _case_builders,
    _context,
    _drafts,
    _lifecycle,
    _validators,
)


# ---- _case_helpers ------------------------------------------------------

def test_case_helpers_public_functions() -> None:
    for name in (
        "_safe_json", "_normalize_compare", "_strip_html", "_strip_markdown_bold",
        "_unique_matches", "_unique_values", "_safe_identifier", "_contains_locally",
        "_count_by_key",
    ):
        assert callable(getattr(_case_helpers, name)), f"missing: {name}"


def test_safe_identifier() -> None:
    assert _case_helpers._safe_identifier("hello world!") == "hello_world"
    assert _case_helpers._safe_identifier("a b c") == "a_b_c"


def test_safe_json_handles_invalid() -> None:
    assert _case_helpers._safe_json(None) is None
    assert _case_helpers._safe_json("") is None
    assert _case_helpers._safe_json('{"a": 1}') == {"a": 1}
    assert _case_helpers._safe_json([1, 2, 3]) == [1, 2, 3]


def test_strip_html() -> None:
    # The function strips tags but keeps the inner text (with surrounding whitespace)
    result = _case_helpers._strip_html("<a href='x'>y</a>")
    assert "y" in result
    assert "<a" not in result


def test_count_by_key() -> None:
    items = [{"status": "ready"}, {"status": "ready"}, {"status": "blocked"}]
    counts = _case_helpers._count_by_key(items, "status")
    assert counts == {"ready": 2, "blocked": 1}


# ---- _validators --------------------------------------------------------

def test_validators_public_functions() -> None:
    for name in (
        "_is_structured_clause_anchor", "_is_usable_golden_anchor",
        "_is_valid_standard_code", "_is_low_value_evidence_text",
        "_is_low_value_golden_text", "_looks_like_person_name",
        "_is_usable_parameter_label", "_matches_expected_anchor",
        "_validate_case", "_validate_draft_golden_case",
        "_validate_into", "_validate_page_coverage",
        "_validate_case_source_trace", "_validate_coverage_case",
        "_validate_coverage_case_trace", "_validate_coverage_matrix_row",
    ):
        assert callable(getattr(_validators, name)), f"missing: {name}"


def test_is_valid_standard_code() -> None:
    assert _validators._is_valid_standard_code("GB/T 1234-2020")
    assert not _validators._is_valid_standard_code("not a standard")


def test_is_low_value_evidence_text() -> None:
    # Short or empty text should be rejected
    assert _validators._is_low_value_evidence_text("")
    # Substantive text should be accepted
    assert not _validators._is_low_value_evidence_text("过压保护阈值为 100V")


# ---- _context -----------------------------------------------------------

def test_context_public_functions() -> None:
    for name in (
        "_active_document_ids", "_build_local_context", "_doc_scope_label",
        "_scope_query", "_target_case_count", "_network_cases_from_metadata",
    ):
        assert callable(getattr(_context, name)), f"missing: {name}"


def test_target_case_count_scaling() -> None:
    # Even with no pages/facts/evidence, returns at least MIN_CASE_COUNT
    empty = _context._target_case_count(0, 0, 0)
    assert empty >= 1
    small = _context._target_case_count(10, 5, 5)
    large = _context._target_case_count(100, 50, 50)
    assert small < large


def test_doc_scope_label() -> None:
    label = _context._doc_scope_label({"doc_id": "DOC-1", "facts": [1, 2, 3]})
    assert "DOC-1" in label


# ---- _case_builders -----------------------------------------------------

def test_case_builders_public_functions() -> None:
    for name in (
        "generate_golden_tests_for_document", "_build_local_cases",
        "_build_network_cases", "_build_answer_quality_cases",
        "_build_page_coverage_cases", "_build_retrieval_quality_cases",
        "_build_last_resort_cases", "_case", "_dedupe_cases",
        "_merge_case_constraints", "_prioritize_cases", "_case_priority",
        "_render_pytest_file", "_select_validated_cases",
        "_select_cases_without_validation", "_sample_headings",
        "_definition_anchor", "_query_anchor", "_extract_candidate_titles",
        "_extract_organizations", "_expected_evidence_shape_for_case_kind",
    ):
        assert callable(getattr(_case_builders, name)), f"missing: {name}"


def test_dedupe_cases() -> None:
    cases = [
        {"query": "q1", "must_include": "a", "assert_mode": "rich_answer"},
        {"query": "q1", "must_include": "a", "assert_mode": "rich_answer"},
        {"query": "q2", "must_include": "b", "assert_mode": "rich_answer"},
    ]
    deduped = _case_builders._dedupe_cases(cases)
    assert len(deduped) == 2


def test_extract_candidate_titles() -> None:
    # Function returns a list (may be empty for non-title-like text)
    titles = _case_builders._extract_candidate_titles("Title A. Title B. Title C.")
    assert isinstance(titles, list)


def test_query_anchor_truncation() -> None:
    long_query = "什么是过压保护阈值的具体数值要求及其在测试中的应用?"
    anchor = _case_builders._query_anchor(long_query, max_chars=20)
    # Truncates to max_chars + "..." (ellipsis added)
    assert len(anchor) <= 25
    assert "..." in anchor


# ---- _drafts ------------------------------------------------------------

def test_drafts_public_functions() -> None:
    for name in (
        "generate_coverage_test_drafts_for_document",
        "validate_coverage_test_drafts_for_document",
        "assess_coverage_test_draft_readiness_for_document",
        "assess_all_coverage_test_draft_readiness",
        "close_coverage_test_gaps",
        "promote_coverage_test_drafts_for_document",
        "_draft_case_from_gap_candidate", "_draft_kind_for_unit",
        "_draft_expected_shape_for_unit", "_draft_case_name",
        "_assess_draft_case_readiness", "_readiness_status",
        "_promotable_draft_cases", "_prune_obsolete_coverage_cases",
    ):
        assert callable(getattr(_drafts, name)), f"missing: {name}"


def test_draft_kind_for_unit() -> None:
    assert _drafts._draft_kind_for_unit("definition_unit") == "coverage_definition"
    assert _drafts._draft_kind_for_unit("requirement_unit") == "coverage_requirement"
    assert _drafts._draft_kind_for_unit("parameter_row_unit") == "coverage_parameter_value"
    assert _drafts._draft_kind_for_unit("unknown") == "coverage_gap"


def test_draft_expected_shape_for_unit() -> None:
    assert _drafts._draft_expected_shape_for_unit("definition_unit") == "term_definition"
    assert _drafts._draft_expected_shape_for_unit("requirement_unit") == "requirement"
    assert _drafts._draft_expected_shape_for_unit("parameter_row_unit") == "parameter_definition"
    assert _drafts._draft_expected_shape_for_unit("unknown") == ""


def test_readiness_status_thresholds() -> None:
    # High score + no flags = ready
    result = _drafts._readiness_status(95, [], "validated")
    assert result in {"ready", "ready_for_validation"}
    # Hard flag = blocked or reject
    result = _drafts._readiness_status(20, ["validation_failed"], "pending")
    assert result in {"blocked", "reject"}
    # Low score = blocked or reject
    result = _drafts._readiness_status(20, [], "pending")
    assert result in {"blocked", "reject"}


# ---- _lifecycle ---------------------------------------------------------

def test_lifecycle_public_functions() -> None:
    for name in (
        "run_golden_source_trace_for_document",
        "run_golden_tests_for_document",
        "run_query_repair_smoke_eval",
        "auto_activate_golden_cases",
        "detect_stale_golden_cases",
        "revalidate_stale_golden_cases",
        "run_coverage_promoted_tests_for_document",
        "run_coverage_promoted_pytest_for_document",
        "_evaluate_single_golden_case", "_build_golden_case_summary",
        "_iso_to_timestamp", "_parse_pytest_counts",
        "_case_string_list", "_page_coverage_summary",
    ):
        assert callable(getattr(_lifecycle, name)), f"missing: {name}"


def test_iso_to_timestamp() -> None:
    ts = _lifecycle._iso_to_timestamp("2026-06-01T10:00:00+00:00")
    assert ts > 0


def test_parse_pytest_counts() -> None:
    output = "5 passed, 2 failed in 1.5s"
    passed, failed = _lifecycle._parse_pytest_counts(output)
    assert passed == 5
    assert failed == 2


def test_case_string_list() -> None:
    assert _lifecycle._case_string_list(["a", "b"]) == ["a", "b"]
    assert _lifecycle._case_string_list("a") == ["a"]
    assert _lifecycle._case_string_list(None) == []


# ---- end-to-end smoke ---------------------------------------------------

def test_package_reexports_match_legacy_api() -> None:
    """The package public API must still export the historical surface."""
    import enterprise_agent_kb.generated_tests as gt

    legacy_names = [
        "assess_all_coverage_test_draft_readiness",
        "assess_coverage_test_draft_readiness_for_document",
        "auto_activate_golden_cases",
        "close_coverage_test_gaps",
        "detect_stale_golden_cases",
        "generate_coverage_test_drafts_for_document",
        "generate_golden_tests_for_document",
        "promote_coverage_test_drafts_for_document",
        "revalidate_stale_golden_cases",
        "run_coverage_promoted_pytest_for_document",
        "run_coverage_promoted_tests_for_document",
        "run_golden_source_trace_for_document",
        "run_golden_tests_for_document",
        "run_query_repair_smoke_eval",
        "validate_coverage_test_drafts_for_document",
    ]
    for name in legacy_names:
        assert hasattr(gt, name), f"missing public API: {name}"
        assert callable(getattr(gt, name)), f"not callable: {name}"


def test_query_repair_smoke_cases_is_in_lifecycle() -> None:
    """The QUERY_REPAIR_SMOKE_CASES constant now lives in _lifecycle."""
    from enterprise_agent_kb.generated_tests._lifecycle import QUERY_REPAIR_SMOKE_CASES
    assert isinstance(QUERY_REPAIR_SMOKE_CASES, list)
    assert len(QUERY_REPAIR_SMOKE_CASES) > 0
    for case in QUERY_REPAIR_SMOKE_CASES:
        assert "query" in case
        assert "assert_mode" in case


def test_min_max_case_count_in_case_builders() -> None:
    from enterprise_agent_kb.generated_tests._case_builders import MIN_CASE_COUNT, MAX_CASE_COUNT
    assert MIN_CASE_COUNT < MAX_CASE_COUNT
    assert MIN_CASE_COUNT > 0
