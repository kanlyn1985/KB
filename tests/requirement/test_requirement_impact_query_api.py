from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.api import handle_requirement_api_request
from enterprise_agent_kb.requirements.query import execute_requirement_query, plan_requirement_query
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementImpactQueryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_query_planner_detects_customer_change_impact(self) -> None:
        plan = plan_requirement_query(self.root, "如果客户A把输出纹波改成20mV，会影响哪些项目？")
        self.assertEqual(plan["intent"], "requirement_impact")
        self.assertEqual(plan["variant_id"], "REQVAR-CUST-A-RIPPLE")
        self.assertEqual(plan["proposed_change"]["value_numeric"], 20.0)

    def test_execute_requirement_impact_query(self) -> None:
        payload = execute_requirement_query(self.root, "如果客户A把输出纹波改成20mV，会影响哪些项目？")
        self.assertEqual(payload["intent"], "requirement_impact")
        self.assertEqual(payload["impact"]["summary"]["affected_project_count"], 2)

    def test_get_impact_api(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "GET",
            "/requirements/impact?variant_id=REQVAR-CUST-A-RIPPLE&new_value=20&unit=mV",
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["summary"]["affected_project_count"], 2)

    def test_post_impact_api(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "POST",
            "/requirements/impact-analysis",
            body={"variant_id": "REQVAR-CUST-A-RIPPLE", "new_value": 20, "unit": "mV"},
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["summary"]["regression_required_count"], 2)


if __name__ == "__main__":
    unittest.main()
