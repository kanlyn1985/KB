# Phase 7 Status

## Completed

- Added environment-backed remote learned-embedding adapter contract.
- Added external vector backend protocol, HTTP adapter, and in-memory validation backend.
- Added deterministic explicit relation extraction and graph precision/recall/F1 evaluation.
- Added API-key authentication with constant-time digest comparison.
- Added role-based access control and permission enforcement.
- Added physical per-tenant SQLite database routing.
- Added token-bucket request rate limiting.
- Added persistent security audit events.
- Added persistent background jobs with leases, retries, cancellation, and worker execution.
- Added verified online SQLite backups and restore controls.
- Added transactional logical-document and derived-index purge.
- Added process metrics counters and latency summaries.
- Added hardened JSON HTTP endpoints.
- Added OpenAPI 3.1 and MCP-compatible adapter contracts.
- Added Phase 7 CLI commands and regression tests.

## Schema version

```text
1 document lifecycle
2 vector index
3 graph index
4 jobs / audit / backup history
5 graph extraction governance
```

## Security boundary

`secure-serve` provides authentication, RBAC, rate limiting, audit, and physical tenant isolation. It does not provide native TLS. Deploy behind a TLS-terminating reverse proxy for network exposure.

## Validation

The dedicated GitHub Actions workflow installs the editable package, runs `compileall`, and executes the full test suite on Python 3.11, 3.12, and 3.13.

## Remaining Phase 8 work

- distributed rate-limit backend and horizontally coordinated jobs;
- production secret manager adapters and key rotation;
- concrete managed vector-database connectors;
- TLS/mTLS deployment profiles;
- full MCP transport server and generated OpenAPI client SDKs;
- backup retention, object-storage replication, and recovery drills;
- OpenTelemetry metrics/traces and external log sinks;
- load, concurrency, chaos, and security testing;
- transactional cleanup for external vector backends;
- policy-driven data retention and legal hold.
