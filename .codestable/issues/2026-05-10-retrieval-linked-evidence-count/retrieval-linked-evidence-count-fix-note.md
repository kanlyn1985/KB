---
doc_type: issue-fix
issue: 2026-05-10-retrieval-linked-evidence-count
status: fixed
severity: P1
source_audit: 2026-05-10-four-loop-integration
source_finding: F01
tags:
  - retrieval
  - evidence
  - closed-loop
---

# Retrieval Linked Evidence Count Fix Note

## Problem

Retrieval run summaries reported `evidence_hit_count=0` for fact-first runs even when those facts had evidence through `fact_evidence_map`.

This made Raw retrieval metadata and Workbench diagnostics look evidence-empty while the answer layer could still cite supporting evidence.

## Root Cause

`query_api.build_query_context()` stores direct evidence hit IDs in `retrieved_evidence_ids_json`, while fact-linked evidence IDs are stored separately in metadata as `linked_evidence_ids`.

`closed_loop_store._retrieval_run_row()` used only `retrieved_evidence_ids_json` for `evidence_hit_count`, so linked evidence was ignored at the top-level API contract.

## Fix

- Keep `retrieved_evidence_ids` backward-compatible as direct evidence IDs.
- Add explicit count fields:
  - `direct_evidence_hit_count`
  - `linked_evidence_hit_count`
  - `evidence_hit_count = direct + linked`
- Update Workbench Retrieval Detail to display direct and linked evidence separately.
- Add regression coverage for linked evidence retrieval diagnostics and API detail output.

## Verification

Commands:

`C:\Python314\python.exe -m pytest tests/test_closed_loop_schema.py -q -k "retrieval_run_detail_derives_quality_diagnostics or retrieval_diagnostics_distinguish_linked_evidence"`

Result:

`2 passed, 17 deselected`

Command:

`C:\Python314\python.exe -m pytest tests/test_api_server.py::test_api_lists_retrieval_runs_and_details -q`

Result:

`1 passed`

Command:

`C:\Python314\python.exe -m pytest tests/test_delivery_assets.py -q`

Result:

`2 passed`

Real data check:

```json
{
  "run_id": "RET-90B2084799985835",
  "query": "充电接口里的CC是什么意思",
  "evidence_hit_count": 5,
  "direct_evidence_hit_count": 0,
  "linked_evidence_hit_count": 5,
  "evidence_status": "linked"
}
```
