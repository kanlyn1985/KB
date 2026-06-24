"""Database connection for the KB1 ontology system.

Phase 0 scope: a single helper that opens a connection to the
ontology SQLite database at a configurable path. The DB file lives
under ``knowledge_base/ontology/`` so it is naturally co-located
with KB1's main database but does not collide with it.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_FILENAME = "ontology.db"


def default_db_path(workspace_root: Path) -> Path:
    """Return the canonical path for the ontology SQLite file.

    Phase 0 places the file under ``<workspace>/ontology/`` so it
    is fully separate from ``<workspace>/db/knowledge.db``.
    """
    ontology_dir = workspace_root / "ontology"
    ontology_dir.mkdir(parents=True, exist_ok=True)
    return ontology_dir / DEFAULT_DB_FILENAME


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with sane defaults."""
    # Ensure parent directory exists so SQLite can create the file.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
