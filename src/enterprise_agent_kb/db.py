from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = OFF;")
    return connection


@contextmanager
def connect_context(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a connection that is automatically closed on context exit.

    Prefer this over `connect()` in new code; it ensures the underlying
    file handle is released even if the caller raises. Existing call sites
    that already manage the connection lifecycle (e.g. via `try/finally`)
    can continue to use `connect()`.
    """
    connection = connect(db_path)
    try:
        yield connection
    finally:
        connection.close()


def apply_schema(connection: sqlite3.Connection, schema_path: Path) -> None:
    schema_sql = schema_path.read_text(encoding="utf-8")
    connection.executescript(schema_sql)
    connection.commit()


def list_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [row["name"] for row in rows]

