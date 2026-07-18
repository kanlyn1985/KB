# Phase 9 R1 Status

## Completed

- Added package version `0.5.0`.
- Added non-root multi-stage Docker image.
- Added Docker Compose API/worker topology and optional Qdrant profile.
- Added Kubernetes Namespace, ServiceAccount, ConfigMap, Secret template, PVC, StatefulSet, Service, NetworkPolicy, and Kustomization.
- Added continuous multi-tenant background worker.
- Added graceful SIGTERM/SIGINT draining behavior.
- Added worker heartbeat, capability registration, and readiness-file lifecycle.
- Added optional SQLite scheduler-leadership leases.
- Separated Core schema migration track from optional platform migrations.
- Added authenticated HTTP platform probe.
- Added Phase 9 platform and manifest tests.
- Added Docker build, non-root assertion, Compose render, and image-evidence CI gate.
- Extended operational CI to execute one queued job through the continuous worker.

## Version boundaries

```text
package version: 0.5.0
Core schema version: 8
platform coordination schema version: 9 when leader leases are enabled
```

## Deployment boundary

The Kubernetes baseline is deliberately:

```text
one StatefulSet replica
one Pod
API + worker sidecars
one ReadWriteOnce volume
```

It must not be scaled horizontally while SQLite remains the authoritative relational and coordination backend.

## Validation gate

Phase 9 R1 is accepted only when the current PR head passes:

```text
Python 3.11 pytest
Python 3.12 pytest
Python 3.13 pytest
container and deployment gate
operational recovery and readiness gate
```

## Remaining Phase 9 work

- Redis rate-limit, leader-election, and queue adapters;
- continuous scheduler daemon;
- Kubernetes Lease-based leadership;
- Vault and cloud secret-manager adapters;
- image publication, signing, provenance, and SBOM policy;
- managed Qdrant collection provisioning;
- OpenTelemetry SDK and trace-context propagation;
- SLO dashboards and alert rules;
- staging backup/restore drills;
- enterprise retention and legal-hold authorization policies.
