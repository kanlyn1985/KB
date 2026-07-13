from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.diff import RequirementDiffService
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.resolver import RequirementResolver
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementResolverMvpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.resolver = RequirementResolver(self.repo)

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_p1_ripple_resolves_to_customer_value_with_project_condition(self) -> None:
        effective = self.resolver.resolve_requirement(
            "CUST-A-P1",
            "REQATOM-DCDC-OUTPUT-RIPPLE",
        )
        self.assertEqual(effective.value_numeric, 30)
        self.assertEqual(effective.unit, "mV")
        self.assertEqual(effective.conflict_status, "none")
        self.assertEqual(effective.verification_status, "verified")
        self.assertGreaterEqual(len(effective.resolution_path), 4)
        self.assertEqual(effective.resolution_path[-1].profile_id, "PROFILE-CUST-A-P1")

    def test_p2_ripple_loosen_requires_approval(self) -> None:
        effective = self.resolver.resolve_requirement(
            "CUST-A-P2",
            "REQATOM-DCDC-OUTPUT-RIPPLE",
        )
        self.assertEqual(effective.value_numeric, 40)
        self.assertEqual(effective.conflict_status, "approval_required")
        self.assertEqual(effective.approval_status, "required")

    def test_project_resolution_finds_all_atoms(self) -> None:
        requirements = self.resolver.resolve_project("CUST-A-P1")
        atoms = {item.atom_id for item in requirements}
        self.assertIn("REQATOM-DCDC-OUTPUT-RIPPLE", atoms)
        self.assertIn("REQATOM-DCDC-EFFICIENCY", atoms)
        self.assertIn("REQATOM-DCDC-SLEEP-CURRENT", atoms)

    def test_diff_against_customer_common_reports_p1_changes(self) -> None:
        diff = RequirementDiffService(self.repo).diff_project_against_profile(
            "CUST-A-P1",
            "PROFILE-CUST-A-DCDC-COMMON",
        )
        changed_atoms = {
            item["atom_id"]
            for bucket in ("tightened", "loosened", "replaced", "ambiguous")
            for item in diff["diff"][bucket]
        }
        self.assertIn("REQATOM-DCDC-OUTPUT-RIPPLE", changed_atoms)
        self.assertIn("REQATOM-DCDC-SLEEP-CURRENT", changed_atoms)


if __name__ == "__main__":
    unittest.main()
