from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.answer import answer_requirement_query
from enterprise_agent_kb.requirements.query import RequirementQueryPlanner
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementQueryAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.planner = RequirementQueryPlanner(self.repo)

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_effective_requirement_query_is_planned(self) -> None:
        plan = self.planner.plan("客户A P1项目 DCDC 输出纹波要求是多少？")
        self.assertEqual(plan.intent, "requirement_effective")
        self.assertEqual(plan.project_id, "CUST-A-P1")
        self.assertEqual(plan.atom_id, "REQATOM-DCDC-OUTPUT-RIPPLE")

    def test_effective_requirement_answer_contains_resolution_path(self) -> None:
        payload = answer_requirement_query(self.root, "客户A P1项目 DCDC 输出纹波要求是多少？")
        self.assertEqual(payload["intent"], "requirement_effective")
        self.assertIn("≤ 30mV", payload["direct_answer"])
        self.assertIn("解析路径", payload["direct_answer"])

    def test_diff_query_uses_customer_common_profile(self) -> None:
        plan = self.planner.plan("P1 项目相对客户A通用需求改了哪些？")
        self.assertEqual(plan.intent, "requirement_diff")
        self.assertEqual(plan.project_id, "CUST-A-P1")
        self.assertEqual(plan.base_profile_id, "PROFILE-CUST-A-DCDC-COMMON")

    def test_ambiguous_missing_project_returns_clarification(self) -> None:
        plan = self.planner.plan("输出纹波要求是多少？")
        self.assertEqual(plan.intent, "clarification_required")
        self.assertIn("project", plan.clarification_reason.lower())


if __name__ == "__main__":
    unittest.main()
