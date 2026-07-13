from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.eco import RequirementEcoService
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.resolver import RequirementResolver
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementEcoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.service = RequirementEcoService(self.repo)

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_create_eco_runs_impact_and_actions(self) -> None:
        eco = self.service.create_change_order(
            project_id="CUST-A-P1",
            title="Tighten customer ripple to 20mV",
            variant_id="REQVAR-CUST-A-RIPPLE",
            proposed_change={"value_numeric": 20, "unit": "mV", "operator": "<="},
            created_by="tester",
        )
        self.assertEqual(eco["status"], "impact_analyzed")
        self.assertEqual(eco["project_id"], "CUST-A-P1")
        self.assertGreaterEqual(eco["impact"]["summary"]["affected_project_count"], 1)
        self.assertGreaterEqual(len(eco["actions"]), 1)

    def test_submit_approve_apply_and_close_eco(self) -> None:
        eco = self.service.create_change_order(
            project_id="CUST-A-P1",
            title="Tighten customer ripple to 20mV",
            variant_id="REQVAR-CUST-A-RIPPLE",
            proposed_change={"value_numeric": 20, "unit": "mV", "operator": "<="},
            created_by="tester",
        )
        submitted = self.service.submit_for_approval(eco["eco_id"], submitted_by="tester")
        self.assertEqual(submitted["status"], "approval_pending")
        approved = self.service.approve(eco["eco_id"], approver="chief-engineer")
        self.assertEqual(approved["status"], "approved")
        applied = self.service.apply_change(eco["eco_id"], applied_by="chief-engineer")
        self.assertEqual(applied["status"], "applied")

        customer_variant = self.service._load_variant("REQVAR-CUST-A-RIPPLE")
        self.assertEqual(customer_variant["value_numeric"], 20)

        p1 = RequirementResolver(self.repo).resolve_requirement("CUST-A-P1", "REQATOM-DCDC-OUTPUT-RIPPLE")
        self.assertEqual(p1.selected_variant_id, "REQVAR-P1-RIPPLE")

        closed = self.service.close_with_release_gate(eco["eco_id"], stage="DV", closed_by="chief-engineer")
        self.assertIn(closed["status"], {"closed", "gate_blocked"})
        self.assertIsNotNone(closed.get("baseline_after_id"))
        self.assertIsNotNone(closed.get("release_gate_after_id"))
        self.assertIn("release_gate", closed)

    def test_run_full_cycle_returns_all_steps(self) -> None:
        result = self.service.run_full_cycle(
            project_id="CUST-A-P1",
            title="Tighten customer ripple to 20mV",
            variant_id="REQVAR-CUST-A-RIPPLE",
            proposed_change={"value_numeric": 20, "unit": "mV", "operator": "<="},
            actor="tester",
            stage="DV",
        )
        self.assertIn("eco_id", result)
        self.assertEqual(result["closed"]["eco_id"], result["eco_id"])
        self.assertIn(result["closed"]["status"], {"closed", "gate_blocked"})


if __name__ == "__main__":
    unittest.main()
