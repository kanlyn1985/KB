"""Phase 3: Approval state machine and concurrency guard tests."""
from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from enterprise_agent_kb.requirements.approval import RequirementApprovalService
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class ApprovalStateMachineTest(unittest.TestCase):
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
            pass

    def _make_approval(self, suffix: str = "OVR-P2-RIPPLE-LOOSEN") -> str:
        approval = self.service.create_approval_request(
            target_type="override",
            target_id=suffix,
            project_id="CUST-A-P2",
            atom_id="REQATOM-DCDC-OUTPUT-RIPPLE",
            variant_id="REQVAR-P2-RIPPLE",
            override_id=suffix,
            reason="test approval",
        )
        return approval["approval_id"]

    def test_approve_then_reject_raises(self) -> None:
        approval_id = self._make_approval()
        self.service.approve(approval_id, approver="eng-1")
        with self.assertRaises(ValueError) as ctx:
            self.service.reject(approval_id, approver="eng-2", reason="undo")
        self.assertIn("cannot be rejected", str(ctx.exception))

    def test_reject_then_approve_raises(self) -> None:
        approval_id = self._make_approval()
        self.service.reject(approval_id, approver="eng-1")
        with self.assertRaises(ValueError) as ctx:
            self.service.approve(approval_id, approver="eng-2")
        self.assertIn("cannot be approved", str(ctx.exception))

    def test_double_approve_raises(self) -> None:
        approval_id = self._make_approval()
        self.service.approve(approval_id, approver="eng-1")
        with self.assertRaises(ValueError) as ctx:
            self.service.approve(approval_id, approver="eng-2")
        self.assertIn("cannot be approved", str(ctx.exception))

    def test_double_reject_raises(self) -> None:
        approval_id = self._make_approval()
        self.service.reject(approval_id, approver="eng-1")
        with self.assertRaises(ValueError) as ctx:
            self.service.reject(approval_id, approver="eng-2")
        self.assertIn("cannot be rejected", str(ctx.exception))

    def test_concurrent_state_change_blocks_approve(self) -> None:
        """Concurrent decide: pre-check sees 'submitted' but a concurrent actor
        flips the DB status before the atomic UPDATE runs. The atomic
        WHERE approval_status='submitted' guard must detect the race and raise.
        """
        approval_id = self._make_approval()
        real_get = self.service.get_approval

        def flip_then_get(aid):
            result = real_get(aid)
            if not getattr(flip_then_get, "_flipped", False):
                with closing(self.repo.connection()) as conn:
                    conn.execute(
                        "UPDATE requirement_approvals SET approval_status='approved' WHERE approval_id=?",
                        (aid,),
                    )
                    conn.commit()
                flip_then_get._flipped = True
                # Return the stale 'submitted' snapshot so the pre-check passes,
                # forcing the atomic UPDATE guard to catch the concurrent change.
                return result
            return result

        self.service.get_approval = flip_then_get  # type: ignore[assignment]
        try:
            with self.assertRaises(ValueError) as ctx:
                self.service.approve(approval_id, approver="late-actor")
            msg = str(ctx.exception).lower()
            self.assertTrue("concurrently" in msg or "cannot be approved" in msg,
                            f"unexpected error: {ctx.exception}")
        finally:
            self.service.get_approval = real_get  # type: ignore[assignment]

    def test_normal_approve_still_works(self) -> None:
        approval_id = self._make_approval()
        approved = self.service.approve(approval_id, approver="eng-1")
        self.assertEqual(approved["approval_status"], "approved")

    def test_normal_reject_still_works(self) -> None:
        approval_id = self._make_approval()
        rejected = self.service.reject(approval_id, approver="eng-1")
        self.assertEqual(rejected["approval_status"], "rejected")


if __name__ == "__main__":
    unittest.main()
