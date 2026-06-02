"""Shared pytest fixtures and configuration for the KB1 test suite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# ── Constants ──────────────────────────────────────────────────────────────

WORKSPACE = Path("knowledge_base")
DOC_ID_QCT1036 = "DOC-000001"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def workspace() -> Path:
    """Root path of the knowledge base workspace."""
    return WORKSPACE


@pytest.fixture(scope="session")
def qct1036_doc_id() -> str:
    """Doc ID for the QC/T 1036-2016 standard (always present in KB)."""
    return DOC_ID_QCT1036


@pytest.fixture()
def db_connection(workspace: Path):
    """Open a read-only connection to the KB facts database.

    Automatically closes after the test. Skips the test if the DB is absent.
    """
    db_path = workspace / "facts.db"
    if not db_path.exists():
        # Fallback to knowledge.db if facts.db not yet built
        db_path = workspace / "db" / "knowledge.db"
    if not db_path.exists():
        pytest.skip("No KB database found")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _has_doc(filename_stem: str) -> bool:
    """Check whether a document with the given filename stem exists in the KB."""
    try:
        from test_helpers import resolve_doc_id_by_filename  # type: ignore[import-untyped]
        return bool(resolve_doc_id_by_filename(filename_stem, ".pdf"))
    except Exception:
        return False


def requires_doc(filename_stem: str):
    """Decorator to skip a test if a required document is not in the KB."""
    return pytest.mark.skipif(
        not _has_doc(filename_stem),
        reason=f"{filename_stem}.pdf not in current knowledge_base",
    )


@pytest.fixture(autouse=True)
def _reset_query_caches():
    """Clear module-level query caches between tests.

    Several production modules memoize their work via @lru_cache and a
    mutable failure-tracking dict. Without this fixture, cache state leaks
    across tests and causes intermittent failures in regression suites
    (notably test_query_repair_regression and test_user_style_query_regression).
    """
    yield
    try:
        from enterprise_agent_kb.query_semantic_parser import (  # type: ignore[import-untyped]
            parse_semantic_query,
            _PROVIDER_FAILURE_UNTIL,
        )
        from enterprise_agent_kb.query_expansion import expand_query  # type: ignore[import-untyped]
        from enterprise_agent_kb.advanced_query_planner import plan_advanced_query  # type: ignore[import-untyped]
        from enterprise_agent_kb.closed_loop_store._runtime import (  # type: ignore[import-untyped]
            _runtime_code_version,
        )

        parse_semantic_query.cache_clear()
        expand_query.cache_clear()
        plan_advanced_query.cache_clear()
        _runtime_code_version.cache_clear()
        _PROVIDER_FAILURE_UNTIL.clear()
    except ImportError:
        # Modules not importable in minimal test contexts; nothing to reset.
        pass