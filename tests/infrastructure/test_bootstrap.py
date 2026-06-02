"""Unit tests for workspace bootstrap and status reporting."""
from __future__ import annotations

from pathlib import Path

import pytest

from enterprise_agent_kb.bootstrap import initialize_workspace, workspace_status
from enterprise_agent_kb.migrations import current_version

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "src" / "enterprise_agent_kb" / "schema.sql"


def test_initialize_workspace_creates_dirs(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    assert paths.root.is_dir()
    assert paths.db_file.is_file()
    assert paths.db_dir.is_dir()


def test_initialize_workspace_records_schema_version(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    from enterprise_agent_kb.db import connect_context
    with connect_context(paths.db_file) as conn:
        # Just-applied schema: version should be 0 (we only set version when
        # migrations/*.sql files exist; this is a brand-new schema).
        assert current_version(conn) == 0


def test_workspace_status_reports_version_zero_for_fresh_db(tmp_path: Path) -> None:
    initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    status = workspace_status(tmp_path / "kb")
    assert status["db_exists"] is True
    assert status["workspace_exists"] is True
    assert status["schema_version"] == 0
    assert isinstance(status["tables"], list)
    assert len(status["tables"]) > 0  # schema.sql creates some tables


def test_workspace_status_handles_missing_db(tmp_path: Path) -> None:
    status = workspace_status(tmp_path / "kb")
    assert status["db_exists"] is False
    assert status["workspace_exists"] is False
    assert status["schema_version"] == 0
    assert status["tables"] == []
