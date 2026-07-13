"""Phase 2 schema migration tests.

Verifies that the requirement subsystem schema is managed via the KB1
migration framework (PRAGMA user_version + migrations/NNN_*.sql) rather
than the legacy inline SCHEMA_SQL executescript path.

Covers:
  - migration file 002_requirement_program.sql exists and declares all tables
  - initialize_schema() applies migrations and bumps user_version to >= 2
  - idempotency: re-running init-schema is a safe no-op
  - upgrade path: a DB at user_version=1 (production-like) gets requirement tables
  - fallback: SCHEMA_SQL constant still mirrors the migration for legacy paths
"""
from __future__ import annotations

import re
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from enterprise_agent_kb.migrations import apply_pending_migrations, current_version
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.schema import SCHEMA_SQL

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _REPO_ROOT / "src" / "enterprise_agent_kb" / "migrations"
_MIGRATION_FILE = _MIGRATIONS_DIR / "002_requirement_program.sql"

_EXPECTED_TABLES = [
    "customers",
    "customer_projects",
    "requirement_atoms",
    "requirement_profiles",
    "requirement_profile_inheritance",
    "requirement_variants",
    "requirement_overrides",
    "effective_requirements",
    "requirement_evidence_bindings",
    "requirement_test_methods",
    "requirement_test_cases",
    "requirement_test_results",
    "requirement_approvals",
    "requirement_approval_events",
    "requirement_candidate_batches",
    "requirement_candidates",
    "requirement_candidate_events",
    "requirement_import_packages",
    "requirement_import_events",
    "requirement_resolution_runs",
    "requirement_baselines",
    "requirement_baseline_items",
    "requirement_baseline_events",
    "requirement_release_gate_runs",
    "requirement_release_gate_findings",
    "requirement_eco_orders",
    "requirement_eco_actions",
    "requirement_eco_events",
]


class TestMigrationFile(unittest.TestCase):
    """Verify the 002 migration file exists and is well-formed."""

    def test_migration_file_exists(self):
        self.assertTrue(_MIGRATION_FILE.exists(), f"{_MIGRATION_FILE} should exist")

    def test_migration_file_declares_all_expected_tables(self):
        text = _MIGRATION_FILE.read_text(encoding="utf-8")
        found = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)", text))
        for table in _EXPECTED_TABLES:
            self.assertIn(table, found, f"{table} missing from 002 migration")

    def test_migration_file_has_indexes(self):
        text = _MIGRATION_FILE.read_text(encoding="utf-8")
        indexes = re.findall(r"CREATE INDEX IF NOT EXISTS\s+([a-zA-Z0-9_]+)", text)
        self.assertGreater(len(indexes), 0, "migration should declare indexes")

    def test_migration_file_is_idempotent(self):
        """All CREATE statements use IF NOT EXISTS (safe to re-run)."""
        text = _MIGRATION_FILE.read_text(encoding="utf-8")
        bare_creates = re.findall(r"CREATE TABLE\s+(?!IF NOT EXISTS)", text)
        self.assertEqual(bare_creates, [], "all CREATE TABLE must use IF NOT EXISTS")


class TestSchemaSqlMirror(unittest.TestCase):
    """The legacy SCHEMA_SQL constant should mirror the migration file so the
    fallback path produces the same schema."""

    def test_schema_sql_declares_all_expected_tables(self):
        found = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)", SCHEMA_SQL))
        for table in _EXPECTED_TABLES:
            self.assertIn(table, found, f"{table} missing from SCHEMA_SQL fallback")

    def test_schema_sql_and_migration_declare_same_tables(self):
        migration_text = _MIGRATION_FILE.read_text(encoding="utf-8")
        migration_tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)", migration_text))
        schema_tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)", SCHEMA_SQL))
        self.assertEqual(migration_tables, schema_tables,
                         "SCHEMA_SQL fallback and 002 migration must declare identical table sets")


class TestInitializeSchemaViaMigrations(unittest.TestCase):
    """Verify initialize_schema() uses the migration framework."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except OSError:
            pass

    def _db(self):
        return self.root / "db" / "knowledge.db"

    def test_fresh_workspace_gets_requirement_tables_and_user_version(self):
        repo = RequirementRepository(self.root)
        tables = repo.initialize_schema()
        self.assertGreaterEqual(len(tables), 28)
        with sqlite3.connect(self._db()) as conn:
            v = current_version(conn)
        self.assertGreaterEqual(v, 2, "user_version should be >= 2 after requirement init-schema")

    def test_init_schema_is_idempotent(self):
        repo = RequirementRepository(self.root)
        repo.initialize_schema()
        # Second run must not raise.
        repo.initialize_schema()
        with sqlite3.connect(self._db()) as conn:
            v = current_version(conn)
        self.assertGreaterEqual(v, 2)

    def test_upgrade_from_user_version_1(self):
        """Simulate a production DB at user_version=1 with KB1 base tables."""
        self.root.joinpath("db").mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db()) as conn:
            conn.execute("CREATE TABLE documents (doc_id TEXT)")
            conn.execute("PRAGMA user_version = 1")
            conn.commit()
        repo = RequirementRepository(self.root)
        tables = repo.initialize_schema()
        self.assertGreaterEqual(len(tables), 28)
        with sqlite3.connect(self._db()) as conn:
            v = current_version(conn)
            docs = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='documents'").fetchone()[0]
        self.assertGreaterEqual(v, 2)
        self.assertEqual(docs, 1, "pre-existing KB1 documents table must be preserved")

    def test_apply_pending_migrations_directly_creates_tables(self):
        """Directly applying migrations (without RequirementRepository) works."""
        self.root.joinpath("db").mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db()) as conn:
            applied = apply_pending_migrations(conn, _MIGRATIONS_DIR)
        self.assertIn(2, applied, "002 migration should be applied")
        with sqlite3.connect(self._db()) as conn:
            count = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name LIKE 'requirement_%'"
            ).fetchone()[0]
        self.assertGreaterEqual(count, 25)


if __name__ == "__main__":
    unittest.main()
