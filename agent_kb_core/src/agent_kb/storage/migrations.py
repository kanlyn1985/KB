from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


PHASE6_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="phase6_document_lifecycle",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS documents (
                logical_document_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_uri TEXT,
                active_version_id TEXT,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS document_versions (
                version_id TEXT PRIMARY KEY,
                logical_document_id TEXT NOT NULL,
                compiler_document_id TEXT NOT NULL,
                version_label TEXT,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (logical_document_id) REFERENCES documents(logical_document_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_document_versions_document ON document_versions(logical_document_id)",
            "CREATE INDEX IF NOT EXISTS idx_document_versions_status ON document_versions(status)",
        ),
    ),
    Migration(
        version=2,
        name="phase6_vector_index",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS embedding_vectors (
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                object_id TEXT,
                provider_id TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                vector_json TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (source_type, source_id, provider_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_embedding_object ON embedding_vectors(object_id)",
            "CREATE INDEX IF NOT EXISTS idx_embedding_provider ON embedding_vectors(provider_id)",
        ),
    ),
    Migration(
        version=3,
        name="phase6_graph_index",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS graph_edges (
                edge_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                source_object_id TEXT NOT NULL,
                target_object_id TEXT NOT NULL,
                properties_json TEXT NOT NULL,
                evidence_ids_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_graph_source ON graph_edges(source_object_id)",
            "CREATE INDEX IF NOT EXISTS idx_graph_target ON graph_edges(target_object_id)",
            "CREATE INDEX IF NOT EXISTS idx_graph_relation ON graph_edges(relation_type)",
        ),
    ),
)


PHASE7_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=4,
        name="phase7_jobs_audit_backups",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS background_jobs (
                job_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                available_at TEXT NOT NULL,
                locked_by TEXT,
                locked_at TEXT,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_jobs_claim ON background_jobs(status, available_at, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_jobs_tenant ON background_jobs(tenant_id, status)",
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT,
                outcome TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_audit_tenant_created ON audit_events(tenant_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_audit_principal ON audit_events(principal_id, created_at)",
            """
            CREATE TABLE IF NOT EXISTS backup_history (
                backup_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_backup_tenant_created ON backup_history(tenant_id, created_at)",
        ),
    ),
    Migration(
        version=5,
        name="phase7_graph_extraction_governance",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS graph_extraction_runs (
                run_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                extractor_id TEXT NOT NULL,
                candidate_count INTEGER NOT NULL,
                accepted_count INTEGER NOT NULL,
                metrics_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_graph_extraction_tenant ON graph_extraction_runs(tenant_id, created_at)",
        ),
    ),
)


PHASE8_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=6,
        name="phase8_distributed_coordination",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS distributed_rate_limits (
                bucket_key TEXT NOT NULL,
                window_start TEXT NOT NULL,
                count INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (bucket_key, window_start)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_distributed_rate_window ON distributed_rate_limits(window_start)",
            """
            CREATE TABLE IF NOT EXISTS worker_heartbeats (
                worker_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                status TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                heartbeat_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_worker_tenant_expiry ON worker_heartbeats(tenant_id, expires_at)",
        ),
    ),
    Migration(
        version=7,
        name="phase8_retention_and_legal_hold",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS legal_holds (
                hold_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                logical_document_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                released_at TEXT,
                metadata_json TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_legal_hold_document ON legal_holds(logical_document_id, status)",
            """
            CREATE TABLE IF NOT EXISTS retention_runs (
                run_id TEXT PRIMARY KEY,
                policy_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                evaluated_count INTEGER NOT NULL,
                eligible_json TEXT NOT NULL,
                held_json TEXT NOT NULL,
                purged_json TEXT NOT NULL,
                dry_run INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_retention_tenant_created ON retention_runs(tenant_id, created_at)",
        ),
    ),
    Migration(
        version=8,
        name="phase8_idempotency_and_replication",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS job_idempotency (
                tenant_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                job_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, idempotency_key)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_job_idempotency_job ON job_idempotency(job_id)",
            """
            CREATE TABLE IF NOT EXISTS backup_replications (
                replication_id TEXT PRIMARY KEY,
                backup_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                destination TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                verified INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_replication_backup ON backup_replications(backup_id, created_at)",
        ),
    ),
)


ALL_MIGRATIONS: tuple[Migration, ...] = PHASE6_MIGRATIONS + PHASE7_MIGRATIONS + PHASE8_MIGRATIONS


class SchemaMigrator:
    """Monotonic SQLite migration runner used by production adapters."""

    def __init__(self, connection: sqlite3.Connection, migrations: Iterable[Migration] = ALL_MIGRATIONS) -> None:
        self.connection = connection
        self.migrations = tuple(sorted(migrations, key=lambda item: item.version))

    def migrate(self) -> list[int]:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {int(row[0]) for row in self.connection.execute("SELECT version FROM schema_migrations")}
        completed: list[int] = []
        with self.connection:
            for migration in self.migrations:
                if migration.version in applied:
                    continue
                for statement in migration.statements:
                    self.connection.execute(statement)
                self.connection.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.name, _utc_now_iso()),
                )
                completed.append(migration.version)
        return completed

    def current_version(self) -> int:
        try:
            row = self.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        except sqlite3.OperationalError:
            return 0
        return int(row[0] or 0)
