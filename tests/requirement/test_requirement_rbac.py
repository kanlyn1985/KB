"""Phase 6: RBAC permission model tests."""
from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from enterprise_agent_kb.requirements.seed import seed_sample_data
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.rbac import (
    RequirementRbacService, ROLE_ADMIN, ROLE_REVIEWER, ROLE_APPROVER, ROLE_VIEWER,
)


class RbacTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.rbac = RequirementRbacService(self.repo)

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except OSError:
            pass

    def test_unknown_user_defaults_to_viewer(self):
        self.assertEqual(self.rbac.get_user_role("unknown"), ROLE_VIEWER)
        self.assertTrue(self.rbac.has_permission("unknown", "requirement.view"))
        self.assertFalse(self.rbac.has_permission("unknown", "requirement.create_eco"))

    def test_global_role_applies_to_all_projects(self):
        self.rbac.assign_role(user_id="alice", role=ROLE_ADMIN)
        self.assertTrue(self.rbac.has_permission("alice", "requirement.create_eco"))
        self.assertTrue(self.rbac.has_permission("alice", "requirement.create_eco", "ANY-PROJECT"))

    def test_project_scoped_role_overrides_global(self):
        self.rbac.assign_role(user_id="bob", role=ROLE_VIEWER)
        self.rbac.assign_role(user_id="bob", role=ROLE_APPROVER, project_id="CUST-A-P1")
        self.assertEqual(self.rbac.get_user_role("bob"), ROLE_VIEWER)
        self.assertEqual(self.rbac.get_user_role("bob", "CUST-A-P1"), ROLE_APPROVER)
        self.assertFalse(self.rbac.has_permission("bob", "requirement.approve"))
        self.assertTrue(self.rbac.has_permission("bob", "requirement.approve", "CUST-A-P1"))

    def test_role_hierarchy(self):
        self.rbac.assign_role(user_id="rev", role=ROLE_REVIEWER)
        self.assertTrue(self.rbac.has_permission("rev", "requirement.promote_candidate"))
        self.assertFalse(self.rbac.has_permission("rev", "requirement.approve"))
        self.assertFalse(self.rbac.has_permission("rev", "requirement.create_eco"))

    def test_require_permission_raises_on_denial(self):
        self.rbac.assign_role(user_id="rev", role=ROLE_REVIEWER)
        with self.assertRaises(PermissionError):
            self.rbac.require_permission("rev", "requirement.create_eco")
        # should not raise
        self.rbac.require_permission("rev", "requirement.promote_candidate")

    def test_assign_invalid_role_raises(self):
        with self.assertRaises(ValueError):
            self.rbac.assign_role(user_id="x", role="superuser")

    def test_list_users(self):
        self.rbac.assign_role(user_id="alice", role=ROLE_ADMIN)
        self.rbac.assign_role(user_id="bob", role=ROLE_VIEWER, project_id="P1")
        result = self.rbac.list_users()
        self.assertEqual(result["user_count"], 2)

    def test_reassign_role_updates(self):
        self.rbac.assign_role(user_id="alice", role=ROLE_VIEWER)
        self.rbac.assign_role(user_id="alice", role=ROLE_ADMIN)
        self.assertEqual(self.rbac.get_user_role("alice"), ROLE_ADMIN)


if __name__ == "__main__":
    unittest.main()
