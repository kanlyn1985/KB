"""Generated test pipeline (coverage drafts, golden cases, lifecycle management).

The public surface is split across focused submodules:
- `_network_search`: web search / page fetch / metadata extraction
- `_case_helpers`: pure utility functions
- `_validators`: anchor/quality/case-validation predicates
- `_context`: per-document context assembly
- `_case_builders`: per-kind test-case construction
- `_drafts`: coverage test draft generation, validation, readiness, promotion
- `_lifecycle`: run/evaluate/activate/detect-stale/revalidate orchestration
"""
from __future__ import annotations

from ._case_builders import (
    _case,
    generate_golden_tests_for_document,
)
from ._drafts import (
    assess_all_coverage_test_draft_readiness,
    assess_coverage_test_draft_readiness_for_document,
    close_coverage_test_gaps,
    generate_coverage_test_drafts_for_document,
    promote_coverage_test_drafts_for_document,
    validate_coverage_test_drafts_for_document,
)
from ._lifecycle import (
    _build_golden_case_summary,
    _trace_metrics_from_context,
    auto_activate_golden_cases,
    detect_stale_golden_cases,
    revalidate_stale_golden_cases,
    run_coverage_promoted_pytest_for_document,
    run_coverage_promoted_tests_for_document,
    run_golden_source_trace_for_document,
    run_golden_tests_for_document,
    run_query_repair_smoke_eval,
)
from ._validators import (
    _is_low_value_evidence_text,
    _is_usable_golden_anchor,
    _is_valid_standard_code,
)

__all__ = [
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
