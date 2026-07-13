from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.compliance import RequirementComplianceService
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementComplianceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.service = RequirementComplianceService(RequirementRepository(self.root))

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_p1_project_matrix_passes_all_seeded_results(self) -> None:
        matrix = self.service.build_project_matrix("CUST-A-P1")
        self.assertEqual(matrix["summary"]["overall_status"], "pass")
        self.assertEqual(matrix["summary"]["status_counts"].get("pass"), 3)

    def test_p2_ripple_fails_against_effective_requirement(self) -> None:
        payload = self.service.build_requirement_compliance(
            "CUST-A-P2",
            "REQATOM-DCDC-OUTPUT-RIPPLE",
        )
        row = payload["row"]
        self.assertEqual(row["compliance_status"], "fail")
        self.assertEqual(row["requirement_conflict_status"], "approval_required")

    def test_p2_project_matrix_is_incomplete_and_failing(self) -> None:
        matrix = self.service.build_project_matrix("CUST-A-P2")
        self.assertEqual(matrix["summary"]["overall_status"], "fail")
        self.assertIn("fail", matrix["summary"]["status_counts"])
        self.assertIn("missing_test_result", matrix["summary"]["status_counts"])


if __name__ == "__main__":
    unittest.main()
