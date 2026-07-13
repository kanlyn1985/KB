from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.answer import answer_requirement_query
from enterprise_agent_kb.requirements.api import handle_requirement_api_request
from enterprise_agent_kb.requirements.query import plan_requirement_query
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementApprovalQueryApiTest(unittest.TestCase):
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

    def test_query_planner_detects_review_intent(self) -> None:
        plan = plan_requirement_query(self.root, "P2 项目有哪些需求需要审批？")
        self.assertEqual(plan["intent"], "requirement_review")
        self.assertEqual(plan["project_id"], "CUST-A-P2")

    def test_answer_review_query(self) -> None:
        payload = answer_requirement_query(self.root, "P2 项目有哪些需求需要审批？")
        self.assertEqual(payload["intent"], "requirement_review")
        self.assertIn("需求评审/审批报告", payload["direct_answer"])
        self.assertGreaterEqual(payload["review"]["summary"]["review_item_count"], 1)

    def test_review_api(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "GET",
            "/requirements/reviews?project_id=CUST-A-P2",
        )
        self.assertTrue(response["ok"])
        self.assertGreaterEqual(response["summary"]["review_item_count"], 1)

    def test_approval_api_create_and_approve(self) -> None:
        create_response = handle_requirement_api_request(
            self.root,
            "POST",
            "/requirements/approvals",
            body={
                "target_type": "override",
                "target_id": "OVR-P2-RIPPLE-LOOSEN",
                "project_id": "CUST-A-P2",
                "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE",
                "variant_id": "REQVAR-P2-RIPPLE",
                "override_id": "OVR-P2-RIPPLE-LOOSEN",
                "reason": "Sample API approval request.",
            },
        )
        self.assertEqual(create_response["status_code"], 201)
        approval_id = create_response["approval_id"]

        approve_response = handle_requirement_api_request(
            self.root,
            "POST",
            f"/requirements/approvals/{approval_id}/approve",
            body={"approver": "api-reviewer"},
        )
        self.assertTrue(approve_response["ok"])
        self.assertEqual(approve_response["approval_status"], "approved")


if __name__ == "__main__":
    unittest.main()
