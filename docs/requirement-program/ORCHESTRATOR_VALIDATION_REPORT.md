# Orchestrator Validation Report

Validation performed in a temporary runtime using the integrated requirement program plus Project Requirement Baseline Versioning.

## Results

- Unit tests: **61 passed**
- Smoke orchestrator gates: **15 passed**
- Baseline gates included: **freeze / list / drift**

## Smoke gates executed

| Gate | Status |
|---|---:|
| preflight | passed |
| unit.tests smoke subset | passed |
| smoke.workspace.reset | passed |
| smoke.schema | passed |
| smoke.seed | passed |
| smoke.resolver | passed |
| smoke.diff | passed |
| smoke.query_answer | passed |
| smoke.api_adapter | passed |
| smoke.compliance | passed |
| smoke.impact | passed |
| smoke.approval | passed |
| smoke.extraction | passed |
| smoke.package_import | passed |
| smoke.baseline | passed |

## Notes

The full unit suite was run directly and passed. The orchestrator smoke mode was run end-to-end and passed. This package remains designed for local application in the user's repository because the GitHub connector cannot currently create branches or write commits to the target repository.


## Added validation

- `smoke.release_gate`: release readiness evaluation and persisted run listing.
# Requirement Program Report

Status: **passed**

| Gate | Status | Duration |
|---|---:|---:|
| preflight | passed | 1.35s |
| unit.tests | passed | 3.21s |
| smoke.workspace.reset | passed | 0.00s |
| smoke.schema | passed | 1.37s |
| smoke.seed | passed | 1.47s |
| smoke.resolver | passed | 2.77s |
| smoke.diff | passed | 1.55s |
| smoke.query_answer | passed | 1.45s |
| smoke.api_adapter | passed | 1.46s |
| smoke.compliance | passed | 1.46s |
| smoke.impact | passed | 1.48s |
| smoke.approval | passed | 1.47s |
| smoke.extraction | passed | 1.38s |
| smoke.package_import | passed | 1.69s |
| smoke.baseline | passed | 0.19s |
| smoke.release_gate | passed | 0.21s |


## ECO validation result

Latest validation in the generated environment:

```text
72 unit tests passed
17 smoke gates passed
smoke.eco passed
```
