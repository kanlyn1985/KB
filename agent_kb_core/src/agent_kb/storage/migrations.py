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


class SchemaMigrator:
    """Monotonic SQLite migration runner used by production adapters."""

    def __init__(self, connection: sqlite3.Connection, migrations: Iterable[Migration] = PHASE6_MIGRATIONS) -> None:
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
