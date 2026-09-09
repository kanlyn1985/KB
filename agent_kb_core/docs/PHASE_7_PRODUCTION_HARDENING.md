# Phase 7 — Production Hardening

Phase 7 hardens the Phase 6 production adapters without changing the evidence, retrieval, or Context Pack contracts.

## Runtime architecture

```text
Client
  -> Bearer API-key authentication
  -> Principal + tenant binding
  -> RBAC permission check
  -> token-bucket rate limit
  -> physical tenant database router
  -> AgentKBService
  -> lexical / vector / graph retrieval
  -> Context Pack / evidence judgement
  -> audit event / metrics
```

Each tenant is routed to an independent SQLite database. This avoids relying on application-level `WHERE tenant_id = ?` filters for the current embedded deployment model. A shared-database adapter can be added later, but it must preserve the same tenant boundary contract.

## Security

`AGENT_KB_API_KEYS` contains a JSON object keyed by API token. Example shape:

```json
{
  "replace-with-a-long-random-token": {
    "principal_id": "operator-1",
    "tenant_id": "tenant-a",
    "roles": ["admin"]
  }
}
```

Raw keys are converted to SHA-256 digests when the authenticator is built. Authentication comparisons use constant-time digest comparison. Roles are mapped to explicit permissions; only `admin` has wildcard access.

The standard-library server is still plain HTTP. TLS termination must be provided by a reverse proxy or a later transport adapter. `secure-serve` means authenticated/RBAC/tenant-isolated, not built-in TLS.

## Embeddings and vector backends

Phase 7 adds:

- `RemoteJSONEmbeddingProvider`, configured through environment variables;
- `ExternalVectorBackend` protocol;
- `HTTPVectorBackend` JSON adapter;
- `InMemoryVectorBackend` for tests and embedded validation;
- provider-neutral `VectorRecord` materialization.

The remote embedding provider accepts a `{model, input}` request contract and parses either `data[].embedding` or `embeddings[]`. API keys are not emitted in `repr` or result payloads.

## Relation extraction and graph evaluation

`RelationExtractor` is provider-neutral. `DeterministicRelationExtractor` only materializes explicit references already present in cards, object properties, or facts. It does not invent latent causal relationships.

Graph quality is evaluated with:

```text
precision
recall
F1
true positives
false positives
false negatives
```

`related_to` is treated as undirected by default; other relation types remain directed.

## Operational controls

Schema versions added in Phase 7:

```text
4 background jobs, audit events, backup history
5 graph extraction governance
```

Operational components:

- transactional SQLite background job queue with leases and retries;
- persistent security audit events;
- online SQLite backup with SHA-256 and `PRAGMA integrity_check`;
- transactional logical-document purge across evidence, facts, cards, objects, FTS, vectors, graph, and lifecycle rows;
- in-process token-bucket rate limiter;
- thread-safe counters and latency summaries;
- OpenAPI 3.1 contract generator;
- MCP-compatible tool adapter.

## Hardened service endpoints

```text
GET  /v1/health
GET  /v1/documents
GET  /v1/jobs/{job_id}
GET  /v1/metrics
GET  /v1/audit
GET  /v1/openapi.json
POST /v1/query
POST /v1/index
POST /v1/feedback
POST /v1/jobs/index
POST /v1/admin/worker-once
POST /v1/admin/backup
POST /v1/admin/purge
```

Requests use:

```text
Authorization: Bearer <api-key>
X-Tenant-ID: <tenant-id>
```

`X-Tenant-ID` is optional, but when supplied it must match the tenant bound to the authenticated principal.

## Remaining boundaries

The following remain replaceable production adapters rather than hidden claims of completeness:

- the in-process rate limiter is not distributed;
- the standard-library server does not terminate TLS;
- the persistent job queue executes one job per worker iteration and has no scheduler daemon;
- the generic remote embedding/vector contracts require compatible external services;
- backup rotation and remote object-storage upload remain deployment concerns;
- OpenAPI and MCP transport integration are contracts, not a full gateway product.
