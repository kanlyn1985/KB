"""Unit tests for db.connect_context — auto-closing connection helper."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from enterprise_agent_kb.db import connect, connect_context


def test_connect_context_closes_on_normal_exit(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    connect(db_path).close()  # initialize schema
    with connect_context(db_path) as conn:
        assert isinstance(conn, sqlite3.Connection)
        rows = conn.execute("SELECT 1 AS v").fetchall()
        assert rows[0]["v"] == 1
    # Connection should be closed; using it should raise ProgrammingError
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_connect_context_closes_on_exception(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    connect(db_path).close()
    captured_conn: list[sqlite3.Connection] = []
    with pytest.raises(RuntimeError, match="boom"):
        with connect_context(db_path) as conn:
            captured_conn.append(conn)
            raise RuntimeError("boom")
    assert len(captured_conn) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        captured_conn[0].execute("SELECT 1")


def test_connect_context_sets_row_factory(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    connect(db_path).close()
    with connect_context(db_path) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (42)")
        conn.commit()
        row = conn.execute("SELECT x FROM t").fetchone()
        assert row["x"] == 42
