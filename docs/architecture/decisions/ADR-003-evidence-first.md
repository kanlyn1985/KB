# ADR-003: Evidence First - No Evidence, No Asserted Knowledge

- Status: Proposed
- Date: 2026-09-01
- Decision Owners: Architecture Owner (Human Reviewer)
- Related Requirements: SYS-005, SYS-003, SYS-011, SYS-013
- Related Data Model: DM-003 Evidence; DM-005 9.3/9.4 assertion types and lifecycle
- Related ICD: AssertionValidator (5.4); EvidenceStore (5.3)
- Related V&V: V&V Plan section 7 INV-T01; section 8 EVD-001..006; section 14 (sufficiency/abstain); Golden G015/G027/G030

## Context

AKB serves an engineering team; an ungrounded confident answer is worse than no answer (answer-layer contract tests already enforce gap disclosure). Golden Dataset encodes negative expectations: no_evidence_no_assertion, no_deterministic_answer, no_hidden_gap.

## Problem

The rule no-evidence-no-asserted-knowledge can be misread as the system knowing nothing without evidence. That reading would forbid legitimate epistemic states - raw observations, extraction candidates, hypotheses - which ingestion pipelines and reasoning need. The boundary must be precise: evidence gates the governed statuses, not existence.

## Decision

1. Frozen rule: no valid Evidence implies no validated/asserted Knowledge (INV-001), enforced by AssertionValidator at status transition, not at object creation.
2. Epistemic boundary - the following exist and are queryable WITHOUT validated evidence:
   - extracted (DM-005 9.3): auto-extraction candidates, status=candidate;
   - observed: system/sensor/human observations, status=validated with observation-scope evidence semantics (weak signals allowed, confidence capped - e.g. filename-convention timestamps);
   - hypothesized: explicit what-if knowledge, status=candidate;
   - inferred: rule outputs (see ADR-004), status=candidate.
3. The ONLY statuses reachable without evidence_refs are candidate/rejected. validated/asserted/disputed require evidence binding.
4. Answer layer: insufficient evidence implies abstain or partial-with-disclosed-gaps - never a deterministic claim (SYS-013).

## Alternatives Considered

- A. Strict reading: no evidence means no object at all: rejected - loses observations/candidates, cripples ingestion and reasoning inputs; contradicts DM-005 9.3 which defines types beyond asserted.
- B. Evidence optional for everything, governance only at query time: rejected - pushes correctness burden to every consumer; the answer layer cannot reconstruct trust after the fact.
- C. Evidence required only for P0 domain: rejected - domain-scoped gating makes cross-domain queries untrustworthy.

## Rationale

Matches the Data Model lifecycle (candidate to validated to asserted; candidate to rejected) and keeps the system epistemically honest while still machine-useful. Golden exercises exactly this boundary: G015/G027 (insufficient implies abstain), G008 (weak-signal observed with confidence cap), G030 (forbidden direct knowledge write).

## Consequences

- AssertionValidator must implement transition rules with evidence checks (V0.1 scope).
- Answer pipeline already aligns (partial discloses gaps; sufficient requires evidence pack) - no change.
- Producers (importers, extraction) may create candidate objects freely; governance cost moves to promotion, where humans review.

## Rejected Alternatives

See Alternatives Considered.

## Verification Impact

INV-T01 automated at AssertionStore contract level; EVD-006 (malformed evidence cannot reach validated). Golden negative cases G015/G027/G030 plus answer-contract tests (partial discloses gaps) run offline today. Sufficient-case evidence binding is asserted by existing test_answer_contract.py.

## Change Impact

No change to existing tables; V0.1 adds validator logic. Documentation-only impact now; runtime gate lands with AssertionStore.

## References

- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md
