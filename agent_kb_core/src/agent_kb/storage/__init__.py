"""Persistent storage, migrations, and document lifecycle adapters."""

from .migrations import Migration, PHASE6_MIGRATIONS, SchemaMigrator
from .lifecycle import DocumentLifecycleRecord, DocumentLifecycleStore, DocumentVersion
from .sqlite_store import PersistentIndexView, SQLiteKnowledgeStore

__all__ = [
    "DocumentLifecycleRecord",
    "DocumentLifecycleStore",
    "DocumentVersion",
    "Migration",
    "PHASE6_MIGRATIONS",
    "PersistentIndexView",
    "SQLiteKnowledgeStore",
    "SchemaMigrator",
]
