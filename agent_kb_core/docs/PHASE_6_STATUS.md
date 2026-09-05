# Phase 6 Status

## Completed

- Added provider-neutral `EmbeddingProvider` contract.
- Added deterministic `HashEmbeddingProvider` baseline.
- Added SQLite vector persistence and vector candidate retrieval.
- Added `ProductionCandidateProvider` for lexical/vector/graph fusion.
- Added monotonic `SchemaMigrator` with recorded schema versions.
- Added logical document and document-version lifecycle management.
- Added SQLite graph-edge persistence and bounded traversal.
- Added production indexing and query pipelines.
- Added versioned dependency-free JSON service endpoints.
- Added feedback-driven evaluation reports and tuning signals.
- Added CLI commands for migrations, production indexing/query, lifecycle, service, and feedback evaluation.
- Added Phase 6 regression tests.

## Schema version

```text
1 document lifecycle
2 vector index
3 graph index
```

## Validation

The dedicated GitHub Actions workflow runs editable installation, `compileall`, and the full `pytest` suite on Python 3.11, 3.12, and 3.13.

## Remaining production hardening

- learned embedding provider implementations and secret management;
- scalable external vector backend;
- relation extraction and graph quality evaluation;
- authentication, RBAC, tenant isolation, rate limiting, and TLS;
- transactional document deprecation with index cleanup;
- background compilation jobs and concurrency controls;
- OpenAPI/gRPC/MCP adapters;
- operational metrics, tracing, backups, and disaster recovery.
