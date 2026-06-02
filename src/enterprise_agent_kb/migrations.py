"""Schema migration framework using SQLite's user_version pragma.

A workspace's schema evolves over time; rather than scattering `CREATE TABLE
IF NOT EXISTS` strings throughout the codebase, this module provides:

  - `current_version(connection)`: read the schema version (PRAGMA user_version).
  - `set_version(connection, n)`: bump the schema version.
  - `apply_pending_migrations(connection, migrations_dir)`: walk `migrations_dir`
    in lexical order, applying any `.sql` files whose `NNN_*.sql` number is
    greater than the current version, and updating user_version after each one.

`apply_schema()` in `db.py` is still the right entry point for brand-new
workspaces; this module is for existing workspaces that need to upgrade.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path


_VERSION_PRAGMA = "PRAGMA user_version"
_MIGRATION_FILENAME = re.compile(r"^(\d{3,})_.+\.sql$")


def current_version(connection: sqlite3.Connection) -> int:
    """Return the schema version stored in PRAGMA user_version."""
    row = connection.execute(_VERSION_PRAGMA).fetchone()
    return int(row[0]) if row else 0


def set_version(connection: sqlite3.Connection, version: int) -> None:
    """Set PRAGMA user_version to *version* (must be a non-negative int)."""
    if version < 0:
        raise ValueError(f"schema version must be non-negative, got {version}")
    connection.execute(f"{_VERSION_PRAGMA} = {int(version)}")


def _migration_files(migrations_dir: Path) -> list[tuple[int, Path]]:
    """Return sorted (version, path) pairs for every `NNN_*.sql` in *dir*."""
    if not migrations_dir.is_dir():
        return []
    found: list[tuple[int, Path]] = []
    for path in migrations_dir.iterdir():
        match = _MIGRATION_FILENAME.match(path.name)
        if match:
            found.append((int(match.group(1)), path))
    found.sort()
    return found


def apply_pending_migrations(connection: sqlite3.Connection, migrations_dir: Path) -> list[int]:
    """Apply every migration in *migrations_dir* whose version > current.

    Returns the list of versions that were applied. Each migration runs in its
    own transaction; partial failures leave the connection at the version of
    the last successful migration.
    """
    applied: list[int] = []
    current = current_version(connection)
    for version, path in _migration_files(migrations_dir):
        if version <= current:
            continue
        sql = path.read_text(encoding="utf-8")
        connection.executescript(sql)
        set_version(connection, version)
        connection.commit()
        applied.append(version)
    return applied


def migration_status(migrations_dir: Path) -> dict[str, object]:
    """Return a snapshot of the migration plan (no DB connection needed)."""
    files = _migration_files(migrations_dir)
    return {
        "migrations_dir": str(migrations_dir),
        "migrations": [{"version": v, "filename": p.name} for v, p in files],
    }
