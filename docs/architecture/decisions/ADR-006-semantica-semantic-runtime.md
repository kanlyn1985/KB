# ADR-006: Semantica as Semantic Runtime Foundation (Implementation Candidate)

- Status: Proposed
- Date: 2026-09-01
- Decision Owners: Architecture Owner (Human Reviewer)
- Related Requirements: SYS-007, SYS-009, SYS-010, SYS-020
- Related Data Model: DM-006/007/008/009/010 mapping targets; NOT a replacement for DM-005
- Related ICD: SemanticGraph (5.6), ReasoningEngine (5.8) - implementation candidates behind interfaces
- Related V&V: V&V Plan section 22 (provider-neutral performance), section 20 (security review of third-party runtime)

## Context

The Agentic KB needs semantic runtime capabilities: entity resolution, graph storage/traversal, temporal semantics, provenance recording, reasoning scaffolding. Building all from scratch duplicates mature open-source machinery. Semantica provides pipeline, ontology, entity-resolution, graph, temporal, reasoning and provenance mechanisms with storage abstraction. The Canonical Data Model is AKB-specific: DM-005 governance semantics do not exist in Semantica's KnowledgeGraph.

## Problem

Two failure modes: (a) rebuild everything and burn calendar time re-proving solved problems; (b) adopt Semantica wholesale and inherit its knowledge model as canonical - losing evidence governance, assertion lifecycle and the frozen invariants (INV-001..010, per INVARIANT_REGISTRY_V1.0) the whole V&V plan depends on.

## Decision

1. Semantica is adopted as Semantic Runtime Foundation / implementation candidate - a library of mechanisms behind AKB interfaces, NOT the system canonical knowledge model.
2. Suitable for reuse (behind ICD interfaces): ingestion Pipeline, Ontology handling, Entity Resolution, Graph storage/traversal, Temporal semantics, Reasoning scaffolding, Provenance mechanisms, Storage abstraction, Runtime mechanisms.
3. Not adoptable as-is: Semantica KnowledgeGraph MUST NOT become the Canonical Knowledge Model without an adaptation layer mapping its structures onto DM-005 (assertion_type/status/evidence_refs/derivation semantics).
4. The Unified Canonical Model (DM-001..018) remains the single source of truth; any Semantica-backed implementation must satisfy ICD contracts and pass the same invariant tests (INV-T01..T06) as a hand-written implementation.
5. Provider swap in/out must remain possible (ADR-009); Semantica is one candidate, not a commitment.

## Alternatives Considered

- A. Adopt Semantica wholesale as the system: rejected - its KnowledgeGraph lacks epistemic governance; adopting it would violate ADR-001/003/004 and force baseline changes (forbidden).
- B. Build all semantic runtime in-house: rejected - high cost, low differentiation; the differentiating value of AKB is governance (evidence/assertions), which is exactly the part built in-house.
- C. Evaluate other frameworks (LLDK, text-to-Cypher stacks): deferred - later candidates under the same interface contract; nothing here forecloses them.

## Rationale

The governance layer (evidence, assertion lifecycle, provenance) is AKB's core differentiator and must remain proprietary and canonical. The mechanical layer (graph storage, entity resolution) is commodity. This split maximizes reuse where risk is low and keeps control where correctness is critical. Interface isolation (ICD) plus invariant tests make the choice reversible.

## Consequences

- An adapter module (semantica adapter) will be needed for graph/ER features, mapping Semantica structures to DM-005/006/007.
- Invariant tests (INV-T01..T06) become the acceptance suite for the adapter.
- Semantica upgrade cycles are isolated behind the adapter; canonical schema is unaffected.

## Rejected Alternatives

See Alternatives Considered.

## Verification Impact

Same invariant suite as native implementation: INV-T01..T06 must pass with the adapter in place. ICD contract tests C-GRAPH-001/C-REA-001: adapter implements SemanticGraph/ReasoningEngine interfaces. Provider-swap test (SYS-020/V-SUB-001): Semantica-backed and fallback implementations interchangeable.

## Change Impact

New adapter package (V0.1+ scope, not this task); no canonical schema changes. Storage abstraction must support both Semantica-backed and plain-SQLite backends during evaluation.

## References

- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md
