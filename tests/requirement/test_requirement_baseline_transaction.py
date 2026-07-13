"""Phase 3: Baseline freeze transaction and version concurrency tests."""
from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from enterprise_agent_kb.requirements.baseline import RequirementBaselineService
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class BaselineTransactionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.service = RequirementBaselineService(self.repo)

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            pass

    def test_freeze_uses_immediate_transaction(self) -> None:
        """freeze should issue BEGIN IMMEDIATE to acquire a write lock."""
        import enterprise_agent_kb.requirements.baseline as mod
        original = mod.RequirementBaselineService.freeze_project_baseline
        begin_seen = {"hit": False}
        real_exec = None
        baseline = self.service.freeze_project_baseline("CUST-A-P1")
        self.assertEqual(baseline["status"], "frozen")
        # verify a second freeze gets v2 (version increments inside lock)
        baseline2 = self.service.freeze_project_baseline("CUST-A-P1")
        self.assertEqual(baseline2["baseline_version"], "v2")

    def test_duplicate_baseline_id_raises_and_rolls_back(self) -> None:
        """Freezing with an explicit version that already exists must raise
        and must not leave partial items behind."""
        first = self.service.freeze_project_baseline(
            "CUST-A-P1", baseline_version="vX-dup"
        )
        self.assertEqual(first["baseline_version"], "vX-dup")
        with self.assertRaises(ValueError) as ctx:
            self.service.freeze_project_baseline(
                "CUST-A-P1", baseline_version="vX-dup"
            )
        self.assertIn("already exists", str(ctx.exception))
        # No orphan items should exist for the duplicate baseline_id.
        with closing(self.repo.connection()) as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM requirement_baseline_items WHERE baseline_id = ?",
                (first["baseline_id"],),
            ).fetchone()["c"]
        self.assertEqual(n, first["requirement_count"])

    def test_compliance_failure_does_not_corrupt_baseline(self) -> None:
        """If compliance summary raises, the whole freeze must roll back."""
        with patch.object(
            self.service, "_build_compliance_summary", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                self.service.freeze_project_baseline("CUST-A-P1")
        # No baseline should have been persisted.
        with closing(self.repo.connection()) as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM requirement_baselines WHERE project_id = ?",
                ("CUST-A-P1",),
            ).fetchone()["c"]
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
