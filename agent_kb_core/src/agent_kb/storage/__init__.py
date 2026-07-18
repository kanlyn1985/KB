"""Persistent storage, migrations, lifecycle, backup, retention, and maintenance adapters."""

from .backup import BackupRecord, SQLiteBackupManager
from .lifecycle import DocumentLifecycleRecord, DocumentLifecycleStore, DocumentVersion
from .maintenance import KnowledgeMaintenance, PurgeReport
from .migrations import (
    ALL_MIGRATIONS,
    PHASE6_MIGRATIONS,
    PHASE7_MIGRATIONS,
    PHASE8_MIGRATIONS,
    Migration,
    SchemaMigrator,
)
from .replication import (
    BackupReplicator,
    BackupRetentionPolicy,
    FilesystemBackupReplicator,
    HTTPBackupReplicator,
    ReplicationResult,
)
from .retention import (
    LegalHold,
    LegalHoldStore,
    RetentionManager,
    RetentionPolicy,
    RetentionRun,
)
from .sqlite_store import PersistentIndexView, SQLiteKnowledgeStore

__all__ = [
    "ALL_MIGRATIONS",
    "BackupRecord",
    "BackupReplicator",
    "BackupRetentionPolicy",
    "DocumentLifecycleRecord",
    "DocumentLifecycleStore",
    "DocumentVersion",
    "FilesystemBackupReplicator",
    "HTTPBackupReplicator",
    "KnowledgeMaintenance",
    "LegalHold",
    "LegalHoldStore",
    "Migration",
    "PHASE6_MIGRATIONS",
    "PHASE7_MIGRATIONS",
    "PHASE8_MIGRATIONS",
    "PersistentIndexView",
    "PurgeReport",
    "ReplicationResult",
    "RetentionManager",
    "RetentionPolicy",
    "RetentionRun",
    "SQLiteBackupManager",
    "SQLiteKnowledgeStore",
    "SchemaMigrator",
]
