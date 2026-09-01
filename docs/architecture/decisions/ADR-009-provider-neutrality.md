# ADR-009: Provider Neutrality for Parsers, Embeddings, Graph, Vector, Search, Reasoner, Connector

- Status: Proposed
- Date: 2026-09-01
- Decision Owners: Architecture Owner (Human Reviewer)
- Related Requirements: SYS-020, SYS-019, SYS-012
- Related Data Model: All Canonical objects (DM-001..018) must remain provider-agnostic; projections (ADR-005) are the provider-coupled layer
- Related ICD: SourceProvider (5.1), KnowledgeCompiler (5.2), SemanticGraph (5.6), RetrievalEngine (5.7), ReasoningEngine (5.8) - all behind interfaces
- Related V&V: V&V Plan section 22 (performance per provider recorded), 13.3 (ablation on channel/provider changes); RTM V-SUB-001

## Context

AKB already lived through a provider swap: the embedding backend moved from remote Ollama to local fastembed (ONNX) - same model name, cosine similarity between backends only 0.63-0.91 on identical texts. Retrieval baselines had to be re-anchored per backend (retrieval gate doc section 12). Graph channel experiments (ablation, confidence gating) changed behavior without touching knowledge. Conclusion: providers are variables; knowledge must not be.

## Problem

If canonical objects carry provider-specific fields (neo4j_node_id as the entity id, embedding vectors inside assertion rows, parser-specific offsets as canonical locations), swapping a provider becomes a data migration over governed knowledge - expensive, risky, audit-relevant. It also biases retrieval experiments: knowledge shape silently changes with provider tuning.

## Decision

1. Parser, Embedding, Graph, Vector, Search, Reasoner, Connector are each isolated behind an ICD interface.
2. Canonical Model must not contain provider-specific fields as core semantics. Concrete prohibitions:
   - no neo4j_node_id (or any driver id) as Canonical Entity ID - canonical ids are AKB-minted and stable;
   - no embedding vectors inside DM-005 assertion rows (vectors live in the vector projection, keyed by canonical id);
   - no parser-specific page/offset formats in canonical Evidence beyond the normalized location schema (DM-003 location: page/section/start/end);
   - no reasoner-specific trace formats in DM-012 - traces follow the canonical schema, provider payloads live in metadata.
3. Provider changes are projection-level events: re-embed, re-index, rebuild graph - canonical restore is never required (ADR-005 recovery order).
4. Every provider swap must re-run channel ablation and re-anchor baselines (evidence: retrieval gate doc section 12 backend-comparability finding).

## Alternatives Considered

- A. Standardize on one provider per layer (e.g. Neo4j everywhere): rejected - couples canonical truth to vendor data models and pricing; the project already benefited from swapping embedding providers.
- B. Provider fields allowed in metadata: partially rejected - metadata is acceptable for provenance recording (which provider produced this), never as join keys or identity.
- C. Canonical model versioned per provider: rejected - forks the data model and destroys single-source-of-truth.

## Rationale

The embedding-backend episode is empirical proof: provider identity leaked into retrieval baselines the moment vectors were compared across backends. Keeping canonical ids AKB-minted and vectors in projections turns provider swaps into routine auditable projection operations - exactly what happened with fastembed (zero canonical impact).

## Consequences

- ICD interfaces gain explicit provider-neutral data contracts (some already drafted).
- Migration discipline: any PR introducing a provider field into canonical tables is rejected at review (checklist item).
- Performance comparisons must record provider identity (V&V 22 environment baseline) - already practiced.

## Rejected Alternatives

See Alternatives Considered.

## Verification Impact

V-SUB-001 (provider substitution): swap implementation behind interface, all contract tests pass unchanged. Schema registry review (SYS-019): canonical tables lint-checked for provider-prefixed columns. Ablation protocol: any provider/channel change re-runs the production health gate with re-anchored baselines (existing tooling).

## Change Impact

Mostly policy + review checklist now; concrete guard = schema lint in CI (V0.1+). Existing code conforms: vector tables are keyed by canonical source ids; graph edges carry origin metadata (provenance), not provider identity.

## References

- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md
