"""Persistent storage, migrations, lifecycle, backup, and maintenance adapters."""

from .backup import BackupRecord, SQLiteBackupManager
from .lifecycle import DocumentLifecycleRecord, DocumentLifecycleStore, DocumentVersion
from .maintenance import KnowledgeMaintenance, PurgeReport
from .migrations import ALL_MIGRATIONS, PHASE6_MIGRATIONS, PHASE7_MIGRATIONS, Migration, SchemaMigrator
from .sqlite_store import PersistentIndexView, SQLiteKnowledgeStore

__all__ = [
    "ALL_MIGRATIONS",
    "BackupRecord",
    "DocumentLifecycleRecord",
    "DocumentLifecycleStore",
    "DocumentVersion",
    "KnowledgeMaintenance",
    "Migration",
    "PHASE6_MIGRATIONS",
    "PHASE7_MIGRATIONS",
    "PersistentIndexView",
    "PurgeReport",
    "SQLiteBackupManager",
    "SQLiteKnowledgeStore",
    "SchemaMigrator",
]
