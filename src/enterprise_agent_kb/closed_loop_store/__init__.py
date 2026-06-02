"""Closed-loop store: source units, golden cases, eval/retrieval runs, repair tasks.

The public API is split across focused submodules: `_helpers` (pure utilities),
`_runtime` (version/runtime identifiers, ``utc_now``), `_source_units` (matrix
persistence), `_golden_cases` (golden case persistence, listing, activation,
drafting), `_retrieval_eval_runs` (eval/retrieval run persistence and analysis),
`_repair_tasks` (repair task persistence and resolution), and
`_failure_diagnostics` (failure root-cause analysis).
"""
from __future__ import annotations

from ._failure_diagnostics import (
    _failure_analysis_item,
    build_failure_analysis,
)
from ._golden_cases import (
    _draft_case_from_failure,
    activate_golden_case_draft,
    draft_golden_case_from_failure,
    draft_golden_cases_from_eval_failures,
    list_golden_cases,
    sync_golden_cases,
)
from ._helpers import re_sub_whitespace
from ._repair_tasks import (
    list_repair_tasks,
    update_repair_task_status,
)
from ._retrieval_eval_runs import (
    backfill_eval_run_scope_metadata,
    compare_eval_runs,
    get_eval_run_detail,
    get_retrieval_run_detail,
    list_eval_runs,
    list_retrieval_runs,
    load_golden_cases_from_file,
    record_eval_run,
    record_retrieval_run,
)
from ._runtime import (
    _runtime_code_version,
    _source_tree_content_hash,
    utc_now,
)
from ._source_units import (
    backfill_source_unit_mappings_from_metadata,
    ensure_source_unit_mapping_tables,
    sync_source_units_from_matrix,
)


__all__ = [
    "activate_golden_case_draft",
    "backfill_eval_run_scope_metadata",
    "backfill_source_unit_mappings_from_metadata",
    "build_failure_analysis",
    "compare_eval_runs",
    "draft_golden_case_from_failure",
    "draft_golden_cases_from_eval_failures",
    "ensure_source_unit_mapping_tables",
    "get_eval_run_detail",
    "get_retrieval_run_detail",
    "list_eval_runs",
    "list_golden_cases",
    "list_repair_tasks",
    "list_retrieval_runs",
    "load_golden_cases_from_file",
    "record_eval_run",
    "record_retrieval_run",
    "re_sub_whitespace",
    "sync_golden_cases",
    "sync_source_units_from_matrix",
    "update_repair_task_status",
    "utc_now",
]
