# ADR-002: Graph is a Projection of Canonical Assertions

- Status: Proposed
- Date: 2026-09-01
- Decision Owners: Architecture Owner (Human Reviewer)
- Related Requirements: SYS-008
- Related Data Model: DM-005 (source), DM-006/007 (projected Entity/Relation); DM-005 9.2 assertion_id
- Related ICD: SemanticGraph (5.6) consumes AssertionStore (5.5)
- Related V&V: V&V Plan section 7 INV-T03 (graph projection integrity), INV-T05 (index rebuild); RTM T-GRAPH-001

## Context

Graph traversal is a first-class retrieval channel in AKB (production weight 0.85, confidence-gated). Current production DB stores graph_edges sourced from skeleton relations and card aggregation. The Canonical Data Model positions Entity/Relation as projections of Assertions. Golden Dataset relations carry assertion_id refs expecting edge-to-assertion traceability (INV-003).

## Problem

In the current schema, graph_edges has no assertion_ref column: an edge cannot be traced back to the canonical proposition justifying it. If the graph is mutated directly (agent, bug, partial transaction), canonical truth and graph silently diverge, with no guaranteed rebuild to restore identity.

## Decision

1. Data flow frozen as: Canonical Assertion -> Semantic Projection -> Graph.
2. The Graph is rebuildable, deletable, regenerable at any time from the Canonical Store; it is never the source of truth.
3. Graph Edges MUST carry assertion_ref pointing at the justifying assertion (INV-003).
4. Writing to the graph MUST NOT modify canonical truth; projection failure must not alter assertions.
5. Recovery order: Canonical Restore -> Projection Rebuild -> Cache Warmup (see ADR-005).

## Alternatives Considered

- A. Graph as primary store (Neo4j-style, assertions derived from edges): rejected - inverts evidence governance; edge deletion would destroy knowledge.
- B. Dual-primary with sync jobs: rejected - two sources of truth guarantee divergence and make INV-T05 unrecoverable.
- C. Hybrid regimes (edges canonical for skeleton imports, projected elsewhere): rejected - doubles the governance surface; Golden relations already carry assertion-level expectations.

## Rationale

The 467 skeleton-imported edges already carry origin/confidence metadata and Golden relations reference assertion-shaped ids; pure-projection edges is the only model where INV-T03/T05 are provable rather than aspirational. It also lets the graph channel be rebuilt after any retrieval experiment without audit risk.

## Consequences

- graph_edges requires an additive assertion_ref column (nullable during migration, NOT NULL after backfill).
- Import paths (skeleton relations, card aggregation, future extraction) must create an assertion row first, then project the edge.
- Direct graph writes from agents are forbidden (aligns with INV-008 Agent Write Boundary).

## Rejected Alternatives

See Alternatives Considered.

## Verification Impact

INV-T03: every edge.assertion_ref resolves to an assertion; projection failure leaves assertions unchanged. INV-T05: delete graph_edges entirely, rebuild from assertions, identity/links/status comparable to baseline. Golden G007/G021/G022 multi-hop and reverse-graph expectations become executable against the projected graph.

## Change Impact

Additive migration on graph_edges (assertion_ref) + backfill script; new rebuild tool. No semantic change to retrieval; graph channel behavior preserved (confidence gate still applies per ablation baseline).

## References

- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md
