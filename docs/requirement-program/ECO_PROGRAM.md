# Engineering Change Order / ECO Program

## Objective

This program turns the requirement subsystem into an engineering change workflow.
It coordinates deterministic services that already exist in the package:

1. Requirement impact analysis.
2. Approval governance.
3. Controlled requirement variant update.
4. Effective requirement refresh.
5. Post-change project baseline freeze.
6. Release gate re-evaluation.
7. ECO audit trail and action list.

## Core flow

```text
create ECO
  -> impact analysis
  -> generated ECO actions
  -> submit approval
  -> approve ECO
  -> apply approved requirement change
  -> refresh effective requirements
  -> freeze post-change baseline
  -> rerun release gate
  -> close or gate_blocked
```

## Status model

| Status | Meaning |
|---|---|
| draft | ECO was created but not analyzed/submitted. |
| impact_analyzed | Dry-run impact analysis has produced project/test/review actions. |
| approval_pending | ECO has been submitted to the approval layer. |
| approved | ECO approval request was approved. |
| applied | Approved change has been written to the target requirement variant. |
| gate_blocked | Post-change release gate was blocked. |
| closed | Post-change baseline and release gate passed or conditionally passed. |

## Tables

```text
requirement_eco_orders
requirement_eco_actions
requirement_eco_events
```

## Determinism boundary

ECO does not use LLM judgment. It only coordinates existing deterministic subsystems:

```text
RequirementImpactAnalyzer
RequirementApprovalService
RequirementResolver
RequirementBaselineService
RequirementReleaseGateService
```

## Safety boundary

The only state-changing step that modifies requirement semantics is `apply_change`.
It is blocked unless the ECO status is `approved`.
