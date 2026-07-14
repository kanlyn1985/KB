"""Phase 6: Multi-project isolation tests."""
from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from enterprise_agent_kb.requirements.seed import seed_sample_data
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.eco import RequirementEcoService
from enterprise_agent_kb.requirements.baseline import RequirementBaselineService
from enterprise_agent_kb.requirements.isolation import assert_project_scope


class IsolationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except OSError:
            pass

    def test_assert_project_scope_matching(self):
        assert_project_scope({"project_id": "P1"}, "P1", "ECO", "E1")

    def test_assert_project_scope_mismatch_raises(self):
        with self.assertRaises(PermissionError):
            assert_project_scope({"project_id": "P1"}, "P2", "ECO", "E1")

    def test_assert_project_scope_none_project_ok(self):
        # Resources without project_id are shared, no restriction
        assert_project_scope({"project_id": None}, "P1", "ECO", "E1")

    def test_get_change_order_with_project_scope(self):
        eco = RequirementEcoService(self.repo)
        created = eco.create_change_order(
            project_id="CUST-A-P1", title="test", variant_id="REQVAR-P1-RIPPLE",
            proposed_change={"value_numeric": 25}, created_by="tester",
        )
        eco_id = created["eco_id"]
        # Same project: OK
        eco.get_change_order(eco_id, project_id="CUST-A-P1")
        # Different project: should raise
        with self.assertRaises(PermissionError):
            eco.get_change_order(eco_id, project_id="CUST-B-P2")

    def test_get_baseline_with_project_scope(self):
        bl = RequirementBaselineService(self.repo)
        result = bl.freeze_project_baseline("CUST-A-P1", baseline_name="test-bl", frozen_by="tester")
        bid = result["baseline_id"]
        # Same project: OK
        bl.get_baseline(bid, project_id="CUST-A-P1")
        # Different project: should raise
        with self.assertRaises(PermissionError):
            bl.get_baseline(bid, project_id="CUST-B-P2")


if __name__ == "__main__":
    unittest.main()
