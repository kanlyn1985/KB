# Baseline Validation Gates

| Gate | Validation | Failure Meaning |
|---|---|---|
| baseline.schema | baseline tables exist | schema migration failed |
| baseline.freeze | resolved effective requirements can be frozen | resolver or DB persistence failed |
| baseline.snapshot | baseline items preserve requirement values | snapshot serialization failed |
| baseline.compare | v1/v2 changes are detected by atom | diff logic failed |
| baseline.drift | current resolver output can be compared with frozen baseline | current-vs-snapshot comparison failed |
| baseline.rollback_plan | dry-run rollback actions are generated for drift | rollback analysis failed |
| baseline.query | natural-language baseline listing intent works | query planner/answer adapter failed |
| baseline.api | framework-neutral API endpoints work | HTTP adapter contract failed |
| baseline.runner | orchestrator executes baseline gate | full program gate wiring failed |

A release-quality baseline should not rely only on technical gates. Business acceptance gates should check approvals, verification gaps, compliance, and customer sign-off.
