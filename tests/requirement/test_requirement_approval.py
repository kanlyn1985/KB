from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.approval import RequirementApprovalService
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.resolver import RequirementResolver
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementApprovalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.service = RequirementApprovalService(self.repo)

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_review_report_surfaces_unapproved_loosen_override(self) -> None:
        report = self.service.build_review_report(project_id="CUST-A-P2")
        self.assertGreaterEqual(report["summary"]["review_item_count"], 1)
        items = {item["source_id"]: item for item in report["review_items"]}
        self.assertIn("OVR-P2-RIPPLE-LOOSEN", items)
        self.assertTrue(items["OVR-P2-RIPPLE-LOOSEN"]["approval_required"])
        self.assertEqual(items["OVR-P2-RIPPLE-LOOSEN"]["review_type"], "risky_override")

    def test_approval_updates_override_and_clears_resolver_approval_conflict(self) -> None:
        before = RequirementResolver(self.repo).resolve_requirement("CUST-A-P2", "REQATOM-DCDC-OUTPUT-RIPPLE")
        self.assertEqual(before.conflict_status, "approval_required")

        approval = self.service.create_approval_request(
            target_type="override",
            target_id="OVR-P2-RIPPLE-LOOSEN",
            project_id="CUST-A-P2",
            atom_id="REQATOM-DCDC-OUTPUT-RIPPLE",
            variant_id="REQVAR-P2-RIPPLE",
            override_id="OVR-P2-RIPPLE-LOOSEN",
            risk_level="medium",
            reason="Customer accepted the P2 ripple relaxation for this sample stage.",
            requested_by="tester",
        )
        self.assertEqual(approval["approval_status"], "submitted")

        approved = self.service.approve(approval["approval_id"], approver="chief-engineer")
        self.assertEqual(approved["approval_status"], "approved")

        after = RequirementResolver(self.repo).resolve_requirement("CUST-A-P2", "REQATOM-DCDC-OUTPUT-RIPPLE")
        self.assertEqual(after.conflict_status, "none")
        self.assertEqual(after.approval_status, "none")

    def test_reject_keeps_override_in_review(self) -> None:
        approval = self.service.create_approval_request(
            target_type="override",
            target_id="OVR-P2-RIPPLE-LOOSEN",
            project_id="CUST-A-P2",
            atom_id="REQATOM-DCDC-OUTPUT-RIPPLE",
            variant_id="REQVAR-P2-RIPPLE",
            override_id="OVR-P2-RIPPLE-LOOSEN",
            reason="Request sample rejection.",
        )
        rejected = self.service.reject(approval["approval_id"], approver="chief-engineer", reason="Evidence is insufficient.")
        self.assertEqual(rejected["approval_status"], "rejected")
        report = self.service.build_review_report(project_id="CUST-A-P2")
        self.assertGreaterEqual(report["summary"]["approval_required_count"], 1)


if __name__ == "__main__":
    unittest.main()
