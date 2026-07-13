from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.answer import answer_requirement_query
from enterprise_agent_kb.requirements.api import handle_requirement_api_request
from enterprise_agent_kb.requirements.baseline import RequirementBaselineService
from enterprise_agent_kb.requirements.query import RequirementQueryPlanner
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementBaselineQueryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.baseline = RequirementBaselineService(self.repo).freeze_project_baseline("CUST-A-P1")

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_query_planner_detects_baseline_intent(self) -> None:
        plan = RequirementQueryPlanner(self.repo).plan("P1 项目有哪些需求基线版本？")
        self.assertEqual(plan.intent, "requirement_baseline")
        self.assertEqual(plan.project_id, "CUST-A-P1")
        answer = answer_requirement_query(self.root, "P1 项目有哪些需求基线版本？")
        self.assertEqual(answer["intent"], "requirement_baseline")
        self.assertIn("项目需求基线", answer["direct_answer"])

    def test_api_baseline_endpoints(self) -> None:
        listed = handle_requirement_api_request(self.root, "GET", "/requirements/baselines?project_id=CUST-A-P1")
        self.assertEqual(listed["status_code"], 200)
        self.assertEqual(listed["baseline_count"], 1)

        loaded = handle_requirement_api_request(self.root, "GET", f"/requirements/baselines/{self.baseline['baseline_id']}")
        self.assertEqual(loaded["status_code"], 200)
        self.assertEqual(loaded["baseline_id"], self.baseline["baseline_id"])

        drift = handle_requirement_api_request(self.root, "GET", f"/requirements/baselines/{self.baseline['baseline_id']}/drift")
        self.assertEqual(drift["status_code"], 200)
        self.assertEqual(drift["summary"]["drifted"], 0)

        rollback = handle_requirement_api_request(self.root, "POST", f"/requirements/baselines/{self.baseline['baseline_id']}/rollback-plan")
        self.assertEqual(rollback["status_code"], 200)
        self.assertEqual(rollback["mode"], "dry_run")

    def test_api_can_freeze_and_compare_baselines(self) -> None:
        created = handle_requirement_api_request(
            self.root,
            "POST",
            "/requirements/projects/CUST-A-P1/baselines",
            body={"version": "v2", "frozen_by": "api"},
        )
        self.assertEqual(created["status_code"], 201)
        compared = handle_requirement_api_request(
            self.root,
            "GET",
            f"/requirements/baselines/compare?base_baseline_id={self.baseline['baseline_id']}&head_baseline_id={created['baseline_id']}",
        )
        self.assertEqual(compared["status_code"], 200)
        self.assertEqual(compared["summary"]["changed"], 0)


if __name__ == "__main__":
    unittest.main()
