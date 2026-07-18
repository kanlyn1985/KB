# Phase 8 Status

## Completed

- Added environment, JSON-file, HTTP, and composite secret-provider contracts.
- Added rotating API-key authentication without service restart.
- Added SQLite-coordinated fixed-window rate limiting.
- Added persistent worker heartbeats, capabilities, leases, and active-worker inspection.
- Added tenant-aware and job-type-aware job claiming.
- Added idempotent background-job submission.
- Added native TLS and optional mTLS server profiles.
- Added Qdrant REST vector-backend implementation.
- Added external-vector cleanup for direct and retention-driven document purge.
- Added MCP-compatible JSON-RPC stdio transport.
- Added dependency-free Python client generation.
- Added trace spans and a minimal OTLP/HTTP JSON exporter.
- Isolated telemetry-export failures from business operations.
- Added filesystem and HTTP backup replication.
- Added backup-retention pruning.
- Added isolated backup recovery drills.
- Added retention planning, legal holds, execution records, and external cleanup synchronization.
- Added load, chaos, and security validation harnesses.
- Added read-only release-readiness evaluation.
- Added `agent-kb-ops` readiness and recovery-drill commands.
- Added an operational GitHub Actions gate after the Python test matrix.
- Added operational evidence artifact generation.
- Added Phase 8 schema migrations, CLI integration, documentation, and regression tests.

## Package and schema

```text
package version: 0.4.0
schema version: 8
```

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

## Deployment capabilities

```text
rotating secrets
RBAC and tenant isolation
TLS / mTLS
SQLite-coordinated rate limiting
idempotent persistent jobs
worker registry
remote embedding adapter
Qdrant vector adapter
OpenAPI client generation
MCP stdio transport
OTLP traces and metrics
backup replication and pruning
isolated recovery drill
retention and legal hold
load / chaos / security tests
read-only release readiness gate
operational CI evidence artifact
```

## Validation

The `Agent KB Core CI` release gate has two levels.

### Test matrix

```text
Python 3.11  success
Python 3.12  success
Python 3.13  success
```

Each matrix job performed editable installation, `compileall`, and the complete pytest suite.

### Operational gate

```text
production indexing                 success
production query                    success
verified backup                     success
isolated recovery drill             success
read-only readiness evaluation      success
generated client compilation        success
operational evidence upload         success
```

Validated workflow run:

```text
Agent KB Core CI #271
head: c201677a8f05f8ac002771dad181c5b65f6c3a9a
```

Operational artifact:

```text
agent-kb-operational-evidence
retention: 14 days
```

Phase 8 R2 validation gate is satisfied.

## Remaining Phase 9 work

- replace SQLite coordination with production Redis/queue adapters where horizontal scale requires it;
- add Kubernetes and container deployment manifests;
- add certificate issuance and automated renewal profiles;
- add concrete Vault, AWS Secrets Manager, Azure Key Vault, and Google Secret Manager adapters;
- add managed Qdrant provisioning and additional vector-database connectors;
- add full OpenTelemetry SDK integration and trace-context propagation;
- add continuous worker daemons, scheduler leadership, and graceful shutdown;
- add SLO/error-budget dashboards and alert rules;
- add penetration-test automation and dependency/SBOM policy gates;
- execute documented backup recovery drills in staging environments;
- define enterprise authorization policies for legal hold and data retention.
