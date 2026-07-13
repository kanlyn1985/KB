from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.baseline import RequirementBaselineService
from enterprise_agent_kb.requirements.release_gate import RequirementReleaseGateService
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementReleaseGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "kb"
        seed_sample_data(self.root)

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_gate_blocks_without_baseline(self) -> None:
        gate = RequirementReleaseGateService(RequirementRepository(self.root)).evaluate_project("CUST-A-P1", stage="DV", persist=False)
        self.assertEqual(gate["readiness_status"], "blocked")
        self.assertTrue(any(item["finding_type"] == "baseline_missing" for item in gate["findings"]))

    def test_dv_gate_passes_for_seeded_p1_after_baseline_freeze(self) -> None:
        baseline = RequirementBaselineService(RequirementRepository(self.root)).freeze_project_baseline("CUST-A-P1", frozen_by="tester")
        gate = RequirementReleaseGateService(RequirementRepository(self.root)).evaluate_project("CUST-A-P1", stage="DV", baseline_id=baseline["baseline_id"], persist=True)
        self.assertIn(gate["readiness_status"], {"pass", "conditional_pass"})
        self.assertEqual(gate["blocker_count"], 0)
        listed = RequirementReleaseGateService(RequirementRepository(self.root)).list_runs(project_id="CUST-A-P1", stage="DV")
        self.assertGreaterEqual(listed["run_count"], 1)
        loaded = RequirementReleaseGateService(RequirementRepository(self.root)).get_run(gate["run_id"])
        self.assertEqual(loaded["readiness_status"], gate["readiness_status"])

    def test_p2_gate_is_blocked_by_pending_approval_and_failure(self) -> None:
        baseline = RequirementBaselineService(RequirementRepository(self.root)).freeze_project_baseline("CUST-A-P2", frozen_by="tester")
        gate = RequirementReleaseGateService(RequirementRepository(self.root)).evaluate_project("CUST-A-P2", stage="PV", baseline_id=baseline["baseline_id"], persist=False)
        self.assertEqual(gate["readiness_status"], "blocked")
        finding_types = {item["finding_type"] for item in gate["findings"]}
        self.assertTrue({"requirement_conflict", "review_item"} & finding_types)


if __name__ == "__main__":
    unittest.main()
