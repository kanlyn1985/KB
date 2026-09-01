# ADR-001: KnowledgeAssertion is the Canonical Knowledge Unit

- Status: Proposed
- Date: 2026-09-01
- Decision Owners: Architecture Owner (Human Reviewer)
- Related Requirements: SYS-004, SYS-005, SYS-006
- Related Data Model: DM-005 KnowledgeAssertion (primary); DM-003 Evidence; DM-004 SemanticUnit; DM-012 ReasoningTrace
- Related ICD: AssertionStore (5.5), AssertionValidator (5.4)
- Related V&V: V&V Plan section 9 (Assertion Tests), section 7 INV-T01/T02; RTM T-AST-001..006

## Context

The Agentic Knowledge Base needs a single canonical unit expressing a proposition the system holds. Current production code (agent_kb) has several knowledge-shaped objects - facts, retrieval cards, object projections, graph edges - but none is a governed proposition with epistemic status, evidence binding and lifecycle. Data Model V1.0 (DM-005) defines KnowledgeAssertion with subject/predicate/object, assertion_type, status, confidence, evidence_refs, temporal_scope and derivation. This ADR freezes that choice before V0.1 implementation.

## Problem

Without a frozen canonical knowledge unit, each subsystem invents its own knowledge shape: facts carry term definitions, cards carry aggregated content, graph edges carry pair relations. Downstream consumers (reasoning, answer contract, provenance, governance) cannot tell which object is authoritative, which is derived, which must carry evidence. Golden Dataset V1.0 already expresses expectations in assertion form; without this ADR those expectations have no guaranteed runtime counterpart.

## Decision

1. KnowledgeAssertion (DM-005) is THE Canonical Knowledge Unit of AKB.
2. The following are NOT canonical knowledge objects:
   - Fact (agent_kb facts table) - compilation-stage semantic unit at best (DM-004 territory), never the final canonical object;
   - Graph Edge - a projection artifact (see ADR-002);
   - Embedding / vector - an index artifact, not knowledge;
   - Chunk / SemanticUnit - intermediate IR between Evidence and Assertion (DM-004).
3. Core governance chain frozen as: Assertion -> Evidence -> Provenance:
   - every asserted/validated Assertion MUST reference at least 1 Evidence (DM-003);
   - every Evidence MUST be traceable to a Document and Source;
   - status transitions must record actor/timestamp/reason/policy_version/previous_status (DM-005 9.4).

## Alternatives Considered

- A. Keep facts as canonical unit: rejected - facts lack epistemic status, lifecycle and derivation; promoting them requires retrofitting all DM-005 fields anyway.
- B. Retrieval cards as canonical: rejected - cards are retrieval-optimized aggregates, not governed propositions.
- C. Multiple canonical units coexisting (fact for terms, edge for relations): rejected - destroys single-source-of-truth and makes governance predicates ambiguous.

## Rationale

DM-005 is the only candidate satisfying all seven system invariants simultaneously (INV-001..007): evidence gate, derived isolation, graph traceability, provenance completeness. Golden Dataset 30 cases already encode assertion-shaped expectations with derivation blocks - ADR-001 makes the data baseline and the future runtime speak the same language.

## Consequences

- agent_kb storage needs additive migrations (assertions table; graph_edges.assertion_ref column) - V0.1 scope, not this ADR.
- Existing facts/evidence remain valuable as compilation inputs; nothing is deleted.
- Answer/decision components will cite assertion_ids instead of fact_ids once AssertionStore lands.

## Rejected Alternatives

See Alternatives Considered (facts-as-canonical, cards-as-canonical, plural-canonical).

## Verification Impact

INV-T01 (evidence gate) and INV-T02 (derived isolation) become testable against AssertionStore contract (ICD 5.4/5.5). Golden reasoning cases R001..R006 carry expected_derived_assertions directly consumable by future ReasoningEngine regression. Golden validator + schema already enforce INV-001/INV-002 at data level.

## Change Impact

Additive: new assertions table, assertion_ref columns; no existing columns dropped (repo rule: additive migrations). Touch points: storage/migrations, graph/store.py, pipeline/production_context.py (V0.1 Evidence Core scope).

## References

- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md
