# Phase 8 — Deployment Reliability

Phase 8 turns the Phase 7 hardened service into a deployable reliability baseline while preserving the existing evidence, retrieval, and Agent Context Pack contracts.

## Deployment flow

```text
Client / MCP host
  -> TLS or mTLS
  -> rotating API-key authentication
  -> tenant binding and RBAC
  -> local or SQLite-coordinated rate limiting
  -> tenant-specific database
  -> idempotent job submission / worker registry
  -> lexical + learned embedding + Qdrant + graph retrieval
  -> Context Pack and evidence judgement
  -> audit + metrics + OTLP traces
```

## Secret management and key rotation

Phase 8 defines a provider-neutral secret contract:

```text
SecretProvider
  |- EnvironmentSecretProvider
  |- JSONFileSecretProvider
  |- HTTPSecretProvider
  `- CompositeSecretProvider
```

`RotatingAPIKeyAuthenticator` reloads API-key mappings on a bounded cadence. Existing keys can be removed and replacement keys introduced without restarting the service. Raw API keys are converted to digests by the existing authenticator and are not emitted in service results or provider representations.

The HTTP secret provider is a generic adapter for services exposing:

```text
GET /secrets/{name}
Authorization: Bearer <manager-token>
```

It is not tied to a specific commercial secret manager.

## Distributed coordination baseline

`SQLiteDistributedRateLimiter` coordinates a fixed-window limit across processes sharing the same tenant database. `SQLiteWorkerRegistry` persists worker heartbeats, capabilities, status, and lease expiry.

Background jobs now support:

- tenant-scoped claims;
- job-type capability filtering;
- idempotency keys;
- leases and stale-worker recovery;
- bounded retries;
- worker heartbeat visibility.

This is a SQLite-coordinated deployment baseline. Large horizontally scaled deployments should replace it with Redis, a transactional queue, or another shared coordination system while retaining the same contracts.

## Managed vector backend

`QdrantVectorBackend` implements the existing `ExternalVectorBackend` contract using Qdrant REST operations for upsert, query, and delete.

The target collection must already exist and its vector dimensions must match the selected embedding provider. Collection provisioning and cluster administration remain deployment responsibilities.

When a document is purged directly or through a retention policy, the hardened service now removes the corresponding evidence, fact, retrieval-card, and object vectors from the configured external backend.

## TLS and mTLS

`TLSConfig` and `enable_tls` wrap the standard-library HTTP server with a server-side SSL context. The profile supports:

- certificate and private-key validation;
- TLS 1.2 minimum by default;
- optional CA trust bundle;
- optional mandatory client certificates;
- disabled TLS compression.

TLS termination can therefore occur inside the service or at an external reverse proxy.

## MCP and generated clients

`MCPJSONRPCServer` provides a line-delimited JSON-RPC 2.0 stdio transport over the existing MCP tool adapter. It supports initialization, ping, tool listing, and tool calls.

`generate_python_client` emits a dependency-free Python client for health, document listing, query, index, and feedback operations.

These are compact transport and client baselines rather than a complete gateway product.

## Observability

Phase 8 adds:

- trace spans around application-service operations;
- in-memory exporter for validation;
- minimal OTLP/HTTP JSON exporter for traces and metrics;
- exporter-failure isolation so telemetry outages do not replace business results;
- process counters and latency summaries from Phase 7.

The OTLP adapter is intentionally dependency-free. Deployments requiring full OpenTelemetry context propagation, sampling, batching, and resource detectors should replace it with the official SDK adapter.

## Backup, replication, and recovery drills

The backup path now supports:

```text
online SQLite backup
  -> integrity check
  -> SHA-256
  -> filesystem or HTTP replication
  -> retention pruning
  -> isolated recovery drill
```

`run_recovery_drill` restores a selected backup into an isolated workspace, executes SQLite integrity verification, checks required schema surfaces, reads table counts, and reports the restored schema version. The live database is never modified.

CLI:

```bash
agent-kb-recovery \
  --backup ./backups/tenant-a-backup_x.sqlite3
```

Use `--keep-restored-copy` when manual inspection is required.

## Retention and legal hold

`LegalHoldStore` prevents direct purge and retention-based purge while a hold is active.

Retention is split into explicit stages:

```text
plan
  -> eligible documents
  -> held documents
  -> purgeable documents
  -> local and external cleanup
  -> immutable retention-run record
```

This separation allows the hardened service to synchronize local knowledge removal with external-vector cleanup before recording the final run.

## Reliability validation

The Phase 8 test harness includes:

- concurrent load execution and latency/RPS reports;
- deterministic chaos delay and failure injection;
- composable security probes;
- rotating-secret tests;
- distributed limit and worker-registry tests;
- idempotent-job tests;
- legal-hold and retention tests;
- backup replication and recovery-drill tests;
- mocked Qdrant contract tests;
- MCP transport and generated-client tests;
- telemetry failure-isolation tests;
- TLS profile validation.

## Schema

```text
1 document lifecycle
2 vector index
3 graph index
4 jobs / audit / backup history
5 graph extraction governance
6 distributed rate limits / worker heartbeats
7 legal holds / retention runs
8 job idempotency / backup replication records
```

## Remaining boundaries

Phase 8 is a deployable baseline, not a claim of unlimited scale:

- SQLite coordination is not equivalent to Redis or a distributed transaction coordinator;
- Qdrant collection provisioning is external;
- the OTLP exporter is minimal rather than a full OpenTelemetry SDK;
- the MCP transport is stdio JSON-RPC and does not include every optional MCP capability;
- HTTP backup replication reads the backup payload into memory;
- certificate issuance, renewal, and trust-policy governance remain operational responsibilities;
- legal-hold authorization policy is role-based and should be integrated with enterprise policy systems where required.
