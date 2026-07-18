# Phase 6 — Production Adapters

## Goal

Phase 6 turns the Phase 5 persistent runtime into a replaceable production-adapter architecture without changing the existing `RetrievalCandidate`, `RetrievalResult`, `AgentContextPack`, evidence-judgement, and evaluation contracts.

```text
Document
  -> compiler
  -> SQLite relational/FTS surfaces
  -> embedding provider + vector adapter
  -> graph persistence/traversal
  -> production candidate provider
  -> hybrid retrieval + reranker
  -> Context Pack + evidence judgement
  -> retrieval audit + feedback evaluation
```

## Embedding and vector boundary

`EmbeddingProvider` defines the provider-neutral contract:

```python
provider_id: str
dimensions: int
embed(texts: Sequence[str]) -> list[list[float]]
```

`HashEmbeddingProvider` is a deterministic, dependency-free baseline used to validate vector persistence and fusion. It is not described as a learned semantic model. Deployments can replace it with a local or remote embedding model.

`SQLiteVectorIndex` stores vectors and emits normal `RetrievalCandidate` objects. Its Python cosine scan is a baseline adapter, not the final large-scale backend.

## Graph boundary

`SQLiteGraphStore` persists ontology-lite edges and supports bounded breadth-first traversal. Graph hits are emitted as normal object candidates with path and edge diagnostics.

Current graph materialization uses `RetrievalCard.related_object_ids` and explicit `ObjectRelation`/`GraphEdge` inputs. Future domain packs may provide richer relation extraction.

## Schema migration and lifecycle

`SchemaMigrator` applies monotonic migrations recorded in `schema_migrations`.

Phase 6 schema version 3 adds:

1. logical documents and document versions;
2. embedding vectors;
3. graph edges.

`DocumentLifecycleStore` supports active, deprecated, and deleted logical documents, version activation, and version history.

## Production retrieval

`ProductionCandidateProvider` combines:

- SQLite FTS/LIKE lexical candidates;
- vector candidates;
- graph traversal candidates.

The provider is passed into the existing Phase 5 `hybrid_retrieve()` path. Therefore the retrieval result and golden-evaluation contracts remain compatible.

## Service API

`AgentKBService` is the application service boundary. `create_http_server()` exposes dependency-free JSON endpoints:

```text
GET  /v1/health
GET  /v1/documents
POST /v1/index
POST /v1/query
POST /v1/feedback
POST /v1/documents/{logical_document_id}/status
```

The standard-library HTTP adapter is intentionally small. A FastAPI, Flask, gRPC, MCP, or enterprise gateway adapter can call the same application service.

## Feedback-driven evaluation

`evaluate_feedback()` joins explicit feedback with retrieval runs and reports:

- mean rating;
- positive/negative rate;
- slices by intent;
- slices by evidence status;
- executed-channel counts;
- recurring improvement candidates.

## CLI

```bash
agent-kb migrate-db --db ./agent-kb.sqlite3

agent-kb index-production \
  --text-file ./sample.txt \
  --db ./agent-kb.sqlite3 \
  --domain-dir ./domains/obc_dcdc \
  --logical-document-id ldoc_ripple \
  --version-label v1

agent-kb query-production \
  --db ./agent-kb.sqlite3 \
  --query "输出纹波要求是多少？" \
  --domain-dir ./domains/obc_dcdc

agent-kb documents --db ./agent-kb.sqlite3
agent-kb eval-feedback --db ./agent-kb.sqlite3
agent-kb serve --db ./agent-kb.sqlite3 --port 8080
```

## Explicit limits

- hash embeddings are a contract-validation baseline, not a learned model;
- SQLite vector scanning is not intended for high-volume production traffic;
- graph materialization is currently conservative;
- the HTTP adapter has no authentication, tenant isolation, rate limiting, or TLS;
- document deprecation currently governs lifecycle metadata and does not yet cascade-delete every indexed surface.

These limits define Phase 7 work rather than being hidden behind production claims.
