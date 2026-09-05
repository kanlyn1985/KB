"""Persistent storage, migrations, lifecycle, backup, retention, recovery, and maintenance adapters."""

from .backup import BackupRecord, SQLiteBackupManager
from .lifecycle import DocumentLifecycleRecord, DocumentLifecycleStore, DocumentVersion
from .maintenance import KnowledgeMaintenance, PurgeReport
from .migrations import (
    ALL_MIGRATIONS,
    CORE_MIGRATIONS,
    PHASE6_MIGRATIONS,
    PHASE7_MIGRATIONS,
    PHASE8_MIGRATIONS,
    PHASE9_MIGRATIONS,
    PLATFORM_MIGRATIONS,
    Migration,
    SchemaMigrator,
)
from .recovery import DEFAULT_REQUIRED_TABLES, RecoveryDrillReport, run_recovery_drill
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
    RetentionPlan,
    RetentionPolicy,
    RetentionRun,
)
from .sqlite_store import PersistentIndexView, SQLiteKnowledgeStore

__all__ = [
    "ALL_MIGRATIONS",
    "BackupRecord",
    "BackupReplicator",
    "BackupRetentionPolicy",
    "CORE_MIGRATIONS",
    "DEFAULT_REQUIRED_TABLES",
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
    "PHASE9_MIGRATIONS",
    "PLATFORM_MIGRATIONS",
    "PersistentIndexView",
    "PurgeReport",
    "RecoveryDrillReport",
    "ReplicationResult",
    "RetentionManager",
    "RetentionPlan",
    "RetentionPolicy",
    "RetentionRun",
    "SQLiteBackupManager",
    "SQLiteKnowledgeStore",
    "SchemaMigrator",
    "run_recovery_drill",
]
