# Phase 4 Status

## Completed

- Added `RetrievalCandidate`, `RetrievalDiagnostics`, and `RetrievalResult` contracts.
- Added deterministic multi-channel retrieval over cards, facts, tables, and evidence.
- Added keyword and domain-alias semantic fallback channels.
- Added weighted reciprocal-rank fusion with intent and evidence-shape boosts.
- Added explicit skipped-channel diagnostics for graph/wiki/source-unit/document surfaces not yet materialized.
- Routed `DocumentContextResult` through retrieval before Context Pack assembly.
- Added retrieval subset propagation for objects, cards, facts, and evidence.
- Added golden retrieval cases and evaluation report contracts.
- Added Hit@K, MRR, object/card/fact/evidence recall metrics.
- Added `agent-kb eval-retrieval` CLI command.
- Added Phase 4 regression tests.

## Current boundary

The retrieval subsystem is dependency-free and deterministic. It does not yet include:

- SQLite/FTS persistence adapter
- embedding provider
- vector index
- cross-encoder or LLM reranker
- graph materialization and graph traversal
- evidence sufficiency judge
- feedback persistence

Those are later adapters and services. Phase 4 establishes the contracts and measurable baseline they must improve without regressing.

## Validation command

```bash
cd agent_kb_core
python -m pytest
```

Tests were added but were not executed by the GitHub connector environment.
