---
doc_type: audit-finding
audit: 2026-05-10-four-loop-integration
finding_id: F02
severity: P1
type:
  - arch-drift
confidence: high
suggested_workflow: cs-issue
status: fixed
---

# F02 Coverage Dashboard Metrics Do Not Match Architecture Semantics

## Evidence

The architecture defines ingestion coverage as:

```text
document -> pages -> blocks -> evidence -> facts
blocks -> source_units -> coverage report
```

and names metrics including evidence and fact coverage.

But `src/enterprise_agent_kb/api_server.py:1417` computes dashboard coverage only from `source_units.status`:

```python
SELECT
    sum(CASE WHEN status IN ('covered', 'tested', 'partial') THEN 1 ELSE 0 END) AS covered,
    sum(CASE WHEN status = 'tested' THEN 1 ELSE 0 END) AS tested
FROM source_units
```

The returned payload labels this as evidence coverage and leaves fact coverage empty:

```python
"evidence_coverage_rate": round(covered / source_units, 6),
"fact_coverage_rate": None,
"tested_rate": round(tested / source_units, 6),
```

Local data shows the dashboard is mostly reflecting `source_units.status`, not actual evidence/fact mapping:

```text
source_units.status:
covered: 1308
u3_not_tested: 944
u1_text_only: 1
```

## Why It Matters

The Workbench dashboard is used to decide whether the入库闭环 is healthy. If `evidence_coverage_rate` is really a source-unit status rate, users may believe document content reached evidence/facts when only coverage classification exists.

This creates architecture drift between the documented closed loop and the observable metric contract.

## Suggested Fix Direction

Split the metric names and calculations:

- `source_unit_coverage_rate`: based on `source_units.status`
- `evidence_coverage_rate`: based on source unit to evidence availability or coverage metadata
- `fact_coverage_rate`: based on source unit to fact availability or expected knowledge type
- `tested_rate`: based on golden/coverage linkage

If evidence/fact linkage is not yet available at source-unit granularity, dashboard should say `null` with a risk reason, not reuse source-unit status under the evidence label.
