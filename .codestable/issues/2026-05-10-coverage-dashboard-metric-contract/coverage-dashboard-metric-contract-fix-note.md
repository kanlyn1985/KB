---
doc_type: issue-fix
issue: 2026-05-10-coverage-dashboard-metric-contract
status: fixed
severity: P1
source_audit: 2026-05-10-four-loop-integration
source_finding: F02
tags:
  - coverage
  - dashboard
  - closed-loop
---

# Coverage Dashboard Metric Contract Fix Note

## Problem

The closed-loop dashboard exposed `evidence_coverage_rate`, but the value was actually computed from `source_units.status`. `fact_coverage_rate` was always `None`.

This made the ingestion loop appear to prove evidence/fact coverage when the dashboard only had source-unit coverage data.

## Root Cause

`api_server._workspace_coverage_snapshot()` counted source units with status `covered/tested/partial` and returned the ratio as `evidence_coverage_rate`.

The coverage build already calculated `covered_by.fact_ids` and `covered_by.evidence_ids`, but `sync_source_units_from_matrix()` only persisted those links inside `source_units.metadata_json`. There was no first-class relational mapping from `source_units` to `facts` or `evidence`, so the dashboard could not truthfully compute evidence/fact coverage.

## Fix

- Added `source_unit_coverage_rate` as the real metric for `source_units.status`.
- Added `source_unit_fact_map` and `source_unit_evidence_map` as additive schema tables.
- Updated `sync_source_units_from_matrix()` to persist source-unit-to-fact/evidence links from coverage matrix `covered_by`.
- Added an idempotent backfill from historical `source_units.metadata_json.covered_by`.
- Updated dashboard coverage to compute `evidence_coverage_rate` and `fact_coverage_rate` from distinct mapped `unit_id` values.
- Kept `legacy_evidence_coverage_rate` as a deprecated alias for compatibility.
- Added `metric_contract` to explain metric provenance.
- Kept ingestion health risks for truly unavailable coverage metrics, but current workspaces with mapping tables no longer show false `*_coverage_unlinked` warnings.

## Verification

Commands:

`C:\Python314\python.exe -m pytest tests\test_closed_loop_schema.py -q`

Result:

`20 passed`

Command:

`C:\Python314\python.exe -m pytest tests\test_api_server.py -q`

Result:

`18 passed`

Real workspace snapshot:

```json
{
  "source_unit_count": 2253,
  "source_unit_coverage_rate": 0.525965,
  "evidence_coverage_rate": 1.0,
  "fact_coverage_rate": 0.999556,
  "tested_rate": 0.0,
  "uncovered_units": 1068,
  "legacy_evidence_coverage_rate": 0.525965
}
```

Runtime dashboard check after API restart:

```text
ingestion_loop.status = warn
risk_codes = ["uncovered_source_units", "parse_risk_pages"]
```

The remaining warning is now about real uncovered/test coverage and parse-risk pages, not missing evidence/fact mapping.
