"""Phase 3: ECO cross-service single transaction boundary tests."""
from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from enterprise_agent_kb.requirements.eco import RequirementEcoService
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class EcoTransactionBoundaryTest(unittest.TestCase):
    """Verify that ECO cross-service operations share a single transaction so
    a failure in any sub-step rolls back all preceding writes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.service = RequirementEcoService(self.repo)
        # Create and approve an ECO so apply_change can be tested.
        eco = self.service.create_change_order(
            project_id="CUST-A-P1",
            title="ripple tighten for transaction test",
            variant_id="REQVAR-P1-RIPPLE",
            proposed_change={"value_numeric": 25, "operator": "<=", "unit": "mV"},
            created_by="tester",
        )
        self.eco_id = eco["eco_id"]
        self.service.submit_for_approval(self.eco_id, submitted_by="tester")
        self.service.approve(self.eco_id, approver="approver")

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            pass

    def _variant_value(self) -> float | None:
        with closing(self.repo.connection()) as conn:
            row = conn.execute(
                "SELECT value_numeric FROM requirement_variants WHERE variant_id='REQVAR-P1-RIPPLE'"
            ).fetchone()
        return dict(row)["value_numeric"] if row else None

    def _eco_status(self) -> str:
        with closing(self.repo.connection()) as conn:
            row = conn.execute(
                "SELECT status FROM requirement_eco_orders WHERE eco_id=?", (self.eco_id,)
            ).fetchone()
        return dict(row)["status"] if row else ""

    def test_apply_change_rolls_back_variant_when_impact_analysis_fails(self) -> None:
        """If impact analysis (which runs outside the per-project try/except)
        raises, variant update + ECO status must roll back so the DB is not
        left in a half-applied state."""
        original_value = self._variant_value()
        with patch(
            "enterprise_agent_kb.requirements.impact.RequirementImpactAnalyzer.analyze_variant_change",
            side_effect=RuntimeError("impact boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.service.apply_change(self.eco_id, applied_by="tester")
        # Variant value must be unchanged (rolled back).
        self.assertEqual(self._variant_value(), original_value)
        # ECO status must still be 'approved', not 'applied'.
        self.assertEqual(self._eco_status(), "approved")

    def test_close_rolls_back_baseline_when_gate_evaluate_fails(self) -> None:
        """If release gate evaluation raises, the baseline freeze must roll
        back so no orphan baseline is left behind."""
        self.service.apply_change(self.eco_id, applied_by="tester")
        with patch(
            "enterprise_agent_kb.requirements.release_gate.RequirementReleaseGateService.evaluate_project",
            side_effect=RuntimeError("gate boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.service.close_with_release_gate(self.eco_id, closed_by="tester")
        # No baseline should have been persisted for this project.
        with closing(self.repo.connection()) as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM requirement_baselines WHERE source_id=?",
                (self.eco_id,),
            ).fetchone()["c"]
        self.assertEqual(n, 0)
        # ECO status must still be 'applied', not 'gate_blocked' or 'closed'.
        self.assertEqual(self._eco_status(), "applied")

    def test_submit_for_approval_rolls_back_on_failure(self) -> None:
        """If approval creation fails, ECO status must not advance to
        'approval_pending'."""
        eco2 = self.service.create_change_order(
            project_id="CUST-A-P1",
            title="second eco for submit rollback",
            variant_id="REQVAR-P1-RIPPLE",
            proposed_change={"value_numeric": 22, "operator": "<=", "unit": "mV"},
            created_by="tester",
        )
        eco2_id = eco2["eco_id"]
        with patch(
            "enterprise_agent_kb.requirements.approval.RequirementApprovalService.create_approval_request",
            side_effect=RuntimeError("approval boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.service.submit_for_approval(eco2_id, submitted_by="tester")
        with closing(self.repo.connection()) as conn:
            row = conn.execute(
                "SELECT status FROM requirement_eco_orders WHERE eco_id=?", (eco2_id,)
            ).fetchone()
        # Status should not be 'approval_pending'.
        self.assertNotEqual(dict(row)["status"], "approval_pending")


if __name__ == "__main__":
    unittest.main()
