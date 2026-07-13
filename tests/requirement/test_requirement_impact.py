from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.impact import RequirementImpactAnalyzer
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementImpactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.analyzer = RequirementImpactAnalyzer(RequirementRepository(self.root))

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_customer_ripple_tightening_impacts_p1_and_p2(self) -> None:
        report = self.analyzer.analyze_variant_change(
            "REQVAR-CUST-A-RIPPLE",
            {"value_numeric": 20, "unit": "mV"},
        )
        self.assertEqual(report["variant_id"], "REQVAR-CUST-A-RIPPLE")
        self.assertEqual(report["summary"]["affected_project_count"], 2)
        by_project = {item["project_id"]: item for item in report["affected_projects"]}
        self.assertEqual(by_project["CUST-A-P1"]["impact_type"], "downstream_override_looser_than_proposed")
        self.assertTrue(by_project["CUST-A-P1"]["regression_test_required"])
        self.assertEqual(by_project["CUST-A-P1"]["test_impact"]["estimated_status"], "fail_against_proposed")
        self.assertEqual(by_project["CUST-A-P2"]["impact_type"], "downstream_override_looser_than_proposed")
        self.assertTrue(by_project["CUST-A-P2"]["review_required"])

    def test_customer_ripple_relaxing_keeps_p1_stricter(self) -> None:
        report = self.analyzer.analyze_variant_change(
            "REQVAR-CUST-A-RIPPLE",
            {"value_numeric": 35, "unit": "mV"},
        )
        by_project = {item["project_id"]: item for item in report["affected_projects"]}
        self.assertEqual(by_project["CUST-A-P1"]["impact_type"], "downstream_override_already_stricter")
        self.assertFalse(by_project["CUST-A-P1"]["regression_test_required"])
        self.assertEqual(by_project["CUST-A-P2"]["impact_type"], "downstream_override_looser_than_proposed")


if __name__ == "__main__":
    unittest.main()
