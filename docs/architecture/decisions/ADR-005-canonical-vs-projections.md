# ADR-005: Canonical Store vs Projections - Projections are Rebuildable

- Status: Proposed
- Date: 2026-09-01
- Decision Owners: Architecture Owner (Human Reviewer)
- Related Requirements: SYS-019, SYS-012, SYS-002
- Related Data Model: Canonical: DM-001/002/003/005/010/011/016/018; Projections: graph, vector, lexical index, cache, derived context
- Related ICD: AssertionStore (5.5) as canonical owner; RetrievalEngine (5.7) consumes projections
- Related V&V: V&V Plan section 7 INV-T05 (index rebuild), section 21 (failure/recovery); RTM T-MIG-001

## Context

AKB uses three retrieval channels (lexical trigram FTS, vector, confidence-gated graph - see production health gate) plus caches. All are derived views. Current node-index.sqlite3 already practices this informally: search_fts is rebuilt from search_documents; vector index writes are atomic per-provider; graph edges were re-imported from skeleton. V&V 21 requires recovery semantics made explicit before V0.1.

## Problem

Without a frozen canonical/projection split, recovery is ad-hoc: which table is truth after a crash? Can the vector index be dropped and rebuilt without audit implications? What happens when projections and canonical disagree? The embedding-backend experiments (fastembed vs Ollama) made this concrete - vector data changed wholesale while knowledge did not.

## Decision

1. Canonical (source of truth, governed, audit-required): Source, Document, Evidence, Assertion, Ontology, Rule, Decision, Observation.
2. Derived (rebuildable projections): Graph, Vector, Lexical Index, Cache, Derived Context.
3. Canonical can always rebuild projections; projections can never replace or overwrite canonical truth.
4. Frozen recovery order: Canonical Restore -> Projection Rebuild -> Cache Warmup.
5. Projection rebuild must preserve identity and link semantics (INV-T05): post-rebuild edges/vectors/index entries resolve to the same canonical ids and provenance as baseline.

## Alternatives Considered

- A. Vector store as co-primary knowledge: rejected - embedding spaces are provider-dependent (measured: fastembed vs Ollama cosine 0.63-0.91 on the same model); they are search artifacts.
- B. Lexical FTS as authoritative for terminology: rejected - trigram index is lossy and tokenizer-bound.
- C. No explicit split, recover by full re-ingest: rejected - re-ingest is not idempotent across parser versions; violates INV-T06 (historical integrity).

## Rationale

Directly evidenced by project history: the vector channel was re-derived across embedding backends with zero canonical impact; graph edges were rebuilt from skeleton with metadata intact. Making the informal practice explicit costs nothing and unlocks safe provider swaps (ADR-009).

## Consequences

- Recovery tooling becomes a V0.1 requirement (rebuild command per projection).
- Provider changes (embedding model swap) are projection-level operations, no canonical migration.
- Backup policy simplifies: canonical tables are the backup scope; projections are reproducible.

## Rejected Alternatives

See Alternatives Considered.

## Verification Impact

INV-T05 test: drop graph/vector/fts, rebuild, compare identity/links/status against frozen baseline. Failure/recovery suite (V&V 21): database restore, canonical restore, projection rebuild, cache warmup with integrity assertions at each stage. Existing practice partially covered: FTS rebuild function, atomic vector upserts; gaps formalized as tests.

## Change Impact

V0.1: add rebuild CLI + INV-T05 test; document per-table classification in schema registry (SYS-019). No immediate production code change required; the split matches current behavior.

## References

- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md
