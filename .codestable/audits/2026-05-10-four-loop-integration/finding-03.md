---
doc_type: audit-finding
audit: 2026-05-10-four-loop-integration
finding_id: F03
severity: P2
type:
  - maintainability
confidence: high
suggested_workflow: cs-refactor
status: fixed
---

# F03 Dead Helper Conflicts With Golden Draft Safety Rule

## Evidence

`src/enterprise_agent_kb/closed_loop_store.py:2041` still defines:

```python
def _must_hit_from_retrieved_items(retrieved_items: list[object]) -> list[str]:
    values: list[str] = []
    for item in retrieved_items[:5]:
        ...
```

`rg "_must_hit_from_retrieved_items" src tests` finds only the definition. The helper is no longer used after the golden draft safety fix.

## Why It Matters

The helper encodes the old behavior of deriving `must_hit` from actual retrieved items. That behavior is now intentionally avoided because a failed retrieval may contain wrong top hits, and turning them into `must_hit` would freeze an error into the regression suite.

Keeping the unused helper creates a future footgun: a later change may reuse it because it appears to solve missing anchors.

## Suggested Fix Direction

Remove `_must_hit_from_retrieved_items()` and keep the regression test that proves missing assertion signals remain blocked.

This is a small refactor, not a behavior change.
