"""Test fixtures for the KB1 ontology system.

Each test gets a fresh temporary directory so the database lives
somewhere outside KB1's real workspace. The test never touches
``<KB1>/knowledge_base/db/knowledge.db``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src/ is on the import path regardless of how pytest is invoked.
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """A scratch directory used as the workspace root for the test."""
    return tmp_path


@pytest.fixture
def ontology_db_path(tmp_workspace: Path) -> Path:
    """The database file the test should use."""
    return tmp_workspace / "ontology" / "ontology.db"
