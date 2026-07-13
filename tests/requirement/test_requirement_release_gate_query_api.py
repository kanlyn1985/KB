from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.api import handle_requirement_api_request
from enterprise_agent_kb.requirements.answer import answer_requirement_query
from enterprise_agent_kb.requirements.baseline import RequirementBaselineService
from enterprise_agent_kb.requirements.query import plan_requirement_query
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementReleaseGateQueryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "kb"
        seed_sample_data(self.root)
        RequirementBaselineService(RequirementRepository(self.root)).freeze_project_baseline("CUST-A-P1", frozen_by="tester")

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_query_planner_detects_release_gate(self) -> None:
        plan = plan_requirement_query(self.root, "客户A P1项目是否可以进入DV门禁？")
        self.assertEqual(plan["intent"], "requirement_release_gate")
        self.assertEqual(plan["project_id"], "CUST-A-P1")
        self.assertEqual(plan["release_stage"], "DV")

    def test_answer_renders_release_gate(self) -> None:
        payload = answer_requirement_query(self.root, "客户A P1项目是否可以进入DV门禁？")
        self.assertEqual(payload["intent"], "requirement_release_gate")
        self.assertIn("发布门禁", payload["direct_answer"])
        self.assertIn(payload["release_gate"]["readiness_status"], {"pass", "conditional_pass"})

    def test_api_evaluates_release_gate(self) -> None:
        response = handle_requirement_api_request(self.root, "GET", "/requirements/projects/CUST-A-P1/release-gate?stage=DV&persist=false")
        self.assertEqual(response["status_code"], 200)
        self.assertEqual(response["stage"], "DV")
        self.assertIn(response["readiness_status"], {"pass", "conditional_pass"})


if __name__ == "__main__":
    unittest.main()
