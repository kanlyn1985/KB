"""Persistent storage adapters for Agent KB Core."""

from .sqlite_store import PersistentIndexView, SQLiteKnowledgeStore

__all__ = ["PersistentIndexView", "SQLiteKnowledgeStore"]
