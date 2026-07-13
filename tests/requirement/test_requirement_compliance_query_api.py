from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.api import handle_requirement_api_request
from enterprise_agent_kb.requirements.answer import answer_requirement_query
from enterprise_agent_kb.requirements.query import plan_requirement_query
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementComplianceQueryApiTest(unittest.TestCase):
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

    def test_plan_compliance_query(self) -> None:
        plan = plan_requirement_query(self.root, "客户A P1项目是否满足DCDC输出纹波要求？")
        self.assertEqual(plan["intent"], "requirement_compliance")
        self.assertEqual(plan["project_id"], "CUST-A-P1")
        self.assertEqual(plan["atom_id"], "REQATOM-DCDC-OUTPUT-RIPPLE")

    def test_answer_compliance_query(self) -> None:
        answer = answer_requirement_query(self.root, "客户A P1项目是否满足DCDC输出纹波要求？")
        self.assertEqual(answer["intent"], "requirement_compliance")
        self.assertIn("总体状态", answer["direct_answer"])
        self.assertIn("pass", answer["direct_answer"])

    def test_api_project_compliance(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "GET",
            "/requirements/projects/CUST-A-P1/compliance",
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["summary"]["overall_status"], "pass")

    def test_api_atom_compliance(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "GET",
            "/requirements/projects/CUST-A-P2/compliance/REQATOM-DCDC-OUTPUT-RIPPLE",
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["row"]["compliance_status"], "fail")


if __name__ == "__main__":
    unittest.main()
