# Phase 8 R2 — Release Reliability Gates

Phase 8 R2 converts the existing reliability primitives into executable release gates. It does not add a new knowledge abstraction; it verifies that the deployed knowledge store can be released and recovered safely.

## Gate model

```text
unit and integration tests
  -> operational fixture build
  -> production index and query smoke
  -> verified backup
  -> isolated recovery drill
  -> read-only readiness evaluation
  -> generated client compilation
  -> operational evidence artifact
```

## Readiness evaluator

`agent-kb-ops readiness` opens the SQLite database in read-only mode and evaluates:

- database existence and non-zero size;
- `PRAGMA integrity_check`;
- required schema tables;
- minimum schema version;
- active logical-document count;
- evidence, fact, and retrieval-card population when documents are required;
- failed background-job count;
- stale running-job count;
- accessible verified backup when backup is required;
- active legal-hold count as an informational signal.

Only failed checks with severity `error` block release. Informational checks remain visible in the report without changing readiness.

Example:

```bash
agent-kb-ops readiness \
  --db ./agent-kb.sqlite3 \
  --min-schema-version 8 \
  --require-documents \
  --require-backup \
  --max-failed-jobs 0 \
  --max-stale-running-jobs 0 \
  --output ./readiness.json
```

The command exits with status `1` when the database is not ready.

## Recovery drill

`agent-kb-ops recovery-drill` restores a backup into an isolated workspace. It never overwrites the live database.

The drill verifies:

- backup SQLite integrity;
- successful isolated restore;
- required table presence;
- readable table counts;
- restored schema version.

The restored copy is deleted by default. It can be retained explicitly for forensic inspection.

```bash
agent-kb-ops recovery-drill \
  --backup-path ./backups/tenant-backup.sqlite3 \
  --output ./recovery.json
```

## GitHub Actions operational gate

The dedicated `Agent KB Core CI` workflow now contains two layers:

1. Python 3.11, 3.12, and 3.13 test matrix;
2. a Python 3.12 operational smoke job that runs only after the matrix succeeds.

The operational job:

1. compiles and indexes an OBC/DCDC fixture;
2. executes a production query;
3. creates a verified backup;
4. performs an isolated recovery drill;
5. executes the release-readiness gate;
6. generates and compiles the dependency-free Python API client;
7. uploads index, query, backup, recovery, readiness, and generated-client evidence.

Artifact name:

```text
agent-kb-operational-evidence
```

Retention period:

```text
14 days
```

## Release decision

A Phase 8 R2 build is releasable only when:

```text
all test-matrix jobs pass
AND operational recovery and readiness gate passes
```

This gate verifies the embedded SQLite deployment profile. Redis coordination, managed queue infrastructure, Kubernetes, cloud secret managers, and full OpenTelemetry SDK integration remain Phase 9 platform work.
