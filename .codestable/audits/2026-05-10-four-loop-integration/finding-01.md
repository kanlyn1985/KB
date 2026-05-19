---
doc_type: audit-finding
audit: 2026-05-10-four-loop-integration
finding_id: F01
severity: P1
type:
  - bug
  - arch-drift
confidence: high
suggested_workflow: cs-issue
status: fixed
---

# F01 Retrieval Run Evidence Count Underreports Linked Evidence

## Evidence

`src/enterprise_agent_kb/query_api.py:453` only records evidence IDs when the final top hits are direct evidence hits:

```python
direct_evidence_hit_ids = [
    hit["result_id"]
    for hit in hits
    if hit.get("result_type") == "evidence" and hit.get("result_id")
]
...
retrieved_evidence_ids=direct_evidence_hit_ids,
```

The same function computes fact-linked evidence separately and stores it only inside metadata:

```python
"linked_evidence_ids": linked_evidence_ids,
"linked_evidence_count": len(linked_evidence_ids),
```

`src/enterprise_agent_kb/closed_loop_store.py:951` then derives `evidence_hit_count` from `retrieved_evidence_ids_json` only:

```python
"evidence_hit_count": len(retrieved_evidence_ids) if isinstance(retrieved_evidence_ids, list) else 0,
```

Local data confirms this is not rare:

```text
retrieval_runs total: 1638
retrieved_evidence_ids_json=[] and linked_evidence_count>0: 1356
```

## Why It Matters

Many successful KB answers are fact-first: top hits are facts, and evidence is attached through `fact_evidence_map`. The current top-level `retrieved_evidence_ids` / `evidence_hit_count` makes those runs look evidence-empty even when linked evidence exists.

This directly weakens the recall closed loop and Workbench diagnostics. It also explains why Raw retrieval metadata can show `evidence_hit_count=0` while the answer layer still has evidence.

## Suggested Fix Direction

Define two explicit metrics:

- `direct_evidence_hit_count`
- `linked_evidence_hit_count`

Then either:

- keep `retrieved_evidence_ids` as direct-only but rename UI/API labels, or
- define `retrieved_evidence_ids` as direct plus linked evidence IDs with provenance metadata.

The fix should update `record_retrieval_run`, retrieval diagnostics, Workbench labels, and tests together.
