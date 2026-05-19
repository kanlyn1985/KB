---
doc_type: issue-fix
issue: 2026-05-10-remove-dead-must-hit-helper
status: fixed
severity: P2
source_audit: 2026-05-10-four-loop-integration
source_finding: F03
tags:
  - regression
  - golden
  - maintainability
---

# Remove Dead Must-Hit Helper Fix Note

## Problem

`closed_loop_store.py` still contained `_must_hit_from_retrieved_items()`, a helper that derived golden `must_hit` anchors from actual retrieved result IDs.

The helper was no longer called, and its behavior conflicted with the current safety rule: failed retrieval results must not be promoted into golden expectations.

## Root Cause

The golden draft logic was updated to require expected contract signals (`must_hit` or `expected_evidence_shape`) and to block drafts without them. The old helper remained after that behavior change.

## Fix

Removed `_must_hit_from_retrieved_items()` from `closed_loop_store.py`.

No runtime behavior changed because the helper had no remaining callers.

## Verification

Command:

`rg -n "_must_hit_from_retrieved_items" src tests -S`

Result:

No matches.

Command:

`C:\Python314\python.exe -m pytest tests/test_closed_loop_schema.py -q -k "batch_drafts_all_eval_failures or golden_draft_activation_blocks_missing_assertion or failure_can_be_drafted"`

Result:

`3 passed, 16 deselected`

Command:

`C:\Python314\python.exe -m pytest tests/test_api_server.py -q -k "golden_draft"`

Result:

`1 passed, 10 deselected`
