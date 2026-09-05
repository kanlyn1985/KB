# Phase 9 R1 — Platform Deployment Baseline

Phase 9 R1 converts the Phase 8 release-gated application into a deployable single-node platform baseline.

## Scope

```text
non-root container image
  + Docker Compose topology
  + Kubernetes StatefulSet topology
  + continuous multi-tenant worker
  + graceful SIGTERM / SIGINT shutdown
  + worker heartbeat and readiness file
  + optional scheduler leader lease
  + container and manifest CI gate
```

This phase does not claim horizontally scalable SQLite operation. The Kubernetes baseline intentionally uses one StatefulSet replica with the API and worker in the same Pod, sharing one ReadWriteOnce volume.

## Container image

`agent_kb_core/Dockerfile` uses a multi-stage Python 3.12 build.

Runtime properties:

- UID/GID `10001`;
- no root process;
- no source tree required at runtime;
- Python bytecode writes disabled;
- `/data` is the persistent state boundary;
- Domain Packs are copied to `/app/domains`;
- API, worker, operations, recovery, and platform CLIs are installed from one wheel.

Build:

```bash
docker build -t agent-kb-core:0.5.0 agent_kb_core
```

## Docker Compose

The Compose topology contains:

```text
api
worker
optional qdrant profile
shared local Docker volume
```

Run the embedded baseline:

```bash
cd agent_kb_core
docker compose -f deploy/docker-compose.yml up --build
```

The API health check uses `agent-kb-platform http-probe` with an authenticated health principal. The committed key is development-only and must be replaced outside local validation.

## Continuous worker

The worker entrypoint is:

```bash
agent-kb-worker \
  --tenant-db-root /data/tenants \
  --domain-dir /app/domains/obc_dcdc \
  --worker-id worker-1 \
  --ready-file /tmp/agent-kb/worker.ready
```

Runtime behavior:

1. scan tenant SQLite databases;
2. register or refresh worker heartbeat per tenant;
3. claim only supported job types;
4. process one job at a time with at-least-once semantics;
5. finish the current job after SIGTERM/SIGINT;
6. publish `stopped` heartbeat and remove the readiness file.

The current built-in handler supports `index_text`. Additional job types must be registered explicitly rather than accepted dynamically.

## Scheduler leadership

`SQLiteLeaderLeaseStore` provides acquire, renew, release, current-state, and expired-lease pruning operations.

Core migrations remain at schema version 8. Instantiating the platform leadership adapter applies the optional platform migration track and advances that coordination database to schema version 9.

```text
Core schema:      8
Platform schema:  9 when leader leases are enabled
```

This adapter is valid for processes coordinating through one SQLite database on one node. Redis, etcd, Consul, or Kubernetes Lease objects remain required for multi-node production election.

## Kubernetes topology

Files are under:

```text
deploy/kubernetes/base/
```

The baseline contains:

- Namespace;
- ServiceAccount with token automount disabled;
- ConfigMap;
- Secret template;
- ReadWriteOnce PVC;
- one-replica StatefulSet;
- API and worker sidecars sharing the same volume;
- ClusterIP Service;
- NetworkPolicy;
- Kustomization.

Apply after replacing the secret and image reference:

```bash
kubectl apply -k agent_kb_core/deploy/kubernetes/base
```

Security controls:

```text
runAsNonRoot
UID/GID 10001
seccomp RuntimeDefault
readOnlyRootFilesystem
allowPrivilegeEscalation false
all Linux capabilities dropped
service-account token automount disabled
resource requests and limits
liveness/readiness probes
```

## Scaling boundary

Do not increase the StatefulSet replica count while using the embedded SQLite coordination/storage topology.

Scale-out requires at minimum:

```text
Redis or equivalent coordination
production queue backend
shared object storage for backups
managed vector service
tenant-aware durable relational storage
platform-native leader election
```

## CI gate

The `container and deployment gate` performs:

```text
Docker image build
API CLI validation
worker CLI validation
platform CLI validation
non-root UID assertion
Docker Compose render
image metadata capture
```

The operational gate additionally submits an index job and executes it through the continuous worker before backup, recovery, and readiness validation.
