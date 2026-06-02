"""Unit tests for the schema migration framework."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from enterprise_agent_kb.db import connect_context
from enterprise_agent_kb.migrations import (
    apply_pending_migrations,
    current_version,
    migration_status,
    set_version,
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Create a fresh workspace dir with a migrations subdir."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    return tmp_path


def test_current_version_defaults_to_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    with connect_context(db_path) as conn:
        assert current_version(conn) == 0


def test_set_version_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "v.db"
    with connect_context(db_path) as conn:
        set_version(conn, 7)
        assert current_version(conn) == 7


def test_set_version_rejects_negative(tmp_path: Path) -> None:
    db_path = tmp_path / "v.db"
    with connect_context(db_path) as conn:
        with pytest.raises(ValueError, match="non-negative"):
            set_version(conn, -1)


def test_apply_pending_migrations_runs_in_order(workspace: Path) -> None:
    (workspace / "migrations" / "001_init.sql").write_text(
        "CREATE TABLE t1 (x INTEGER);", encoding="utf-8"
    )
    (workspace / "migrations" / "002_add_column.sql").write_text(
        "ALTER TABLE t1 ADD COLUMN y TEXT;", encoding="utf-8"
    )
    (workspace / "migrations" / "003_seed.sql").write_text(
        "INSERT INTO t1 (x, y) VALUES (1, 'a');", encoding="utf-8"
    )
    db_path = workspace / "ws.db"
    with connect_context(db_path) as conn:
        applied = apply_pending_migrations(conn, workspace / "migrations")
        assert applied == [1, 2, 3]
        assert current_version(conn) == 3
        row = conn.execute("SELECT x, y FROM t1").fetchone()
        assert (row[0], row[1]) == (1, "a")


def test_apply_pending_migrations_skips_already_applied(workspace: Path) -> None:
    (workspace / "migrations" / "001_init.sql").write_text(
        "CREATE TABLE t1 (x INTEGER);", encoding="utf-8"
    )
    (workspace / "migrations" / "002_more.sql").write_text(
        "CREATE TABLE t2 (y TEXT);", encoding="utf-8"
    )
    db_path = workspace / "ws.db"
    with connect_context(db_path) as conn:
        first = apply_pending_migrations(conn, workspace / "migrations")
        assert first == [1, 2]
        # Running again should be a no-op
        second = apply_pending_migrations(conn, workspace / "migrations")
        assert second == []


def test_migration_status_lists_files_in_order(workspace: Path) -> None:
    (workspace / "migrations" / "001_first.sql").write_text("--", encoding="utf-8")
    (workspace / "migrations" / "010_tenth.sql").write_text("--", encoding="utf-8")
    (workspace / "migrations" / "002_second.sql").write_text("--", encoding="utf-8")
    status = migration_status(workspace / "migrations")
    versions = [m["version"] for m in status["migrations"]]  # type: ignore[index]
    assert versions == [1, 2, 10]


def test_ignores_non_matching_filenames(workspace: Path) -> None:
    (workspace / "migrations" / "001_init.sql").write_text("--", encoding="utf-8")
    (workspace / "migrations" / "README.md").write_text("# docs", encoding="utf-8")
    (workspace / "migrations" / "_draft.sql").write_text("--", encoding="utf-8")
    status = migration_status(workspace / "migrations")
    assert len(status["migrations"]) == 1  # type: ignore[arg-type]
    assert status["migrations"][0]["filename"] == "001_init.sql"  # type: ignore[index]


def test_empty_migrations_dir_is_noop(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    db_path = tmp_path / "ws.db"
    with connect_context(db_path) as conn:
        assert apply_pending_migrations(conn, migrations) == []
