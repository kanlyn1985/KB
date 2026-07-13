# Release Readiness Gate Program

## Goal

Combine requirement baselines, effective requirement resolution, evidence status, approvals, and test compliance into deterministic DV/PV/SOP readiness gates.

## Gate inputs

- Frozen project requirement baseline
- Current effective requirements
- Baseline drift report
- Compliance matrix
- Approval/review report
- Evidence/verification status

## Gate outcomes

- `pass`: no blockers or warnings
- `conditional_pass`: no blockers, but warnings remain
- `blocked`: at least one blocker remains

## Stage policy

| Stage | Evidence gaps | Incomplete tests | Compliance failures | Pending approvals | Baseline drift |
|---|---|---|---|---|---|
| DV | warning | warning | blocker | blocker | blocker |
| PV | blocker | blocker | blocker | blocker | blocker |
| SOP | blocker | blocker | blocker | blocker | blocker |

## CLI

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement release-gate \
  --project-id CUST-A-P1 \
  --stage DV \
  --evaluated-by chief-engineer
```

## API

```text
GET /requirements/projects/{project_id}/release-gate?stage=DV
GET /requirements/release-gates?project_id=...
GET /requirements/release-gates/{run_id}
```

## Validation gate

The orchestrator now includes `smoke.release_gate`, which validates baseline existence, release readiness evaluation, and persisted run lookup.
