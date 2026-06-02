"""Coverage tracking: document test coverage and gap candidate generation.

The functional code is split across focused submodules: `_gap_detection`
(source-unit construction, fact matching, gap-candidate evaluation),
`_report_rendering` (report rendering and shared utilities), and
`_orchestrator` (the public build_coverage_for_document / build_test_gap
entry points plus the CoverageBuildResult / TestGapCandidateBuildResult
dataclasses).
"""
from __future__ import annotations

from ._gap_detection import (
    SourceUnit,
    _clean_test_gap_label,
    _is_actionable_test_gap_row,
    _is_source_unit_inventory_noise,
    _looks_like_low_value_parameter_gap,
    _looks_like_test_gap_noise,
    _stable_fact_fallback_unit_id,
)
from ._orchestrator import (
    CoverageBuildResult,
    TestGapCandidateBuildResult,
    build_coverage_for_document,
    build_test_gap_candidates_for_document,
)
from ._report_rendering import _soft_contains

__all__ = [
    "CoverageBuildResult",
    "SourceUnit",
    "TestGapCandidateBuildResult",
    "build_coverage_for_document",
    "build_test_gap_candidates_for_document",
]
