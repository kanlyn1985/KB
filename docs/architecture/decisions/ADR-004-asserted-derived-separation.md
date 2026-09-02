# ADR-004: Asserted and Derived Knowledge are Distinct Epistemic Classes

- Status: Accepted
- Date: 2026-09-01
- Decision Owners: Architecture Owner (Human Reviewer)
- Related Requirements: SYS-006, SYS-010
- Related Data Model: DM-005 9.3 (assertion_type), DM-011 Rule, DM-012 ReasoningTrace
- Related ICD: ReasoningEngine (5.8), AssertionStore (5.5), AssertionValidator (5.4)
- Related V&V: V&V Plan section 7 INV-T02; section 15.1 Golden Rule Tests; Golden G007/G019/G020/G021 reasoning cases
- Acceptance Reference: docs/architecture/reviews/ARCHITECTURE_ACCEPTANCE_V1.0.md (AR-V1.0 Gate: APPROVED, 2026-09-01)

## Context

Reasoning over the knowledge graph (multi-hop chains, rule application, conflict resolution) produces new propositions. Golden reasoning cases (R001..R006) expect derived assertions carrying rule/parent/reasoner provenance and status=candidate. The system must never let reasoning output silently become authoritative - a bug or bad rule would rewrite truth.

## Problem

If derived assertions share the same table/status space as asserted ones without enforced separation, one UPDATE collapses the epistemic boundary. Hallucinated facts stored as verified is a known real-world RAG failure mode, not hypothetical.

## Decision

1. Asserted and Derived are distinct epistemic classes, enforced by assertion_type (DM-005 9.3) AND status (9.4) - two independent axes, both must agree.
2. Every derived assertion MUST carry a non-null derivation block: rule_ref, rule_version, parent_assertions, reasoner_id, reasoner_version, reasoning_trace (Golden schema already requires rule_ref/parent_assertions/reasoner_id; version fields added at runtime).
3. Derived assertions cannot auto-promote to asserted. Promotion requires an explicit governed transition (human review or an approved promotion policy), recorded per DM-005 9.4 (actor/timestamp/reason/policy_version/previous_status).
4. The MemoryStore-to-Knowledge path is equally gated: memory objects are never authoritative without the promotion pipeline (INV-009 Memory Promotion Gate, see ADR-008).

## Alternatives Considered

- A. Single type field with trust scores: rejected - a number is not governance; consumers cannot filter authoritative-only reliably.
- B. Separate tables for derived vs asserted: rejected - breaks the single lifecycle model, makes cross-class queries (conflict detection G016) awkward; type/status axes already encode the distinction.
- C. Auto-promotion on confidence threshold: rejected - confidence measures extraction quality, not governance acceptance; a threshold would be a hidden policy.

## Rationale

Two-axis separation (type + status) matches DM-005 exactly, is enforceable by schema checks (Golden validator already fails inferred-without-derivation), and keeps rule versioning auditable - required for V&V 15.1 (rule version pinning) and 12 (provenance of derived knowledge).

## Consequences

- ReasoningEngine contract (ICD 5.8) must return assertions with derivation blocks; the store must reject inferred rows without them.
- Promotions become explicit auditable events - good for architecture review, adds one workflow step for knowledge stewards.
- Conflict scenarios (G016) can only produce dispute/candidate rows, never silent overwrites.

## Rejected Alternatives

See Alternatives Considered.

## Verification Impact

INV-T02 test: reasoning output rows must be assertion_type=inferred, status=candidate, with complete derivation. Golden reasoning cases R001..R006 define expected_derived_assertions and expected_trace - directly consumable once the ReasoningEngine lands (V0.1+). Golden validator enforces the data-level half today (fails inferred-without-derivation).

## Change Impact

Runtime gate lands with AssertionStore/ReasoningEngine (V0.1+). No change to current retrieval behavior; graph/channel weights unaffected.

## References

- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md
