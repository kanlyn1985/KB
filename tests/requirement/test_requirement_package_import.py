from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.package_import import RequirementPackageImportService
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementPackageImportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.service = RequirementPackageImportService(self.repo)

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_import_package_creates_project_profiles_and_candidates(self) -> None:
        result = self.service.import_project_package(
            customer_id="CUST-A",
            customer_name="客户A",
            project_id="CUST-A-P3",
            project_code="A-DCDC-P3",
            product_family="DCDC",
            package_name="P3 customer requirement pack",
            sources=[{"name": "req.txt", "text": "项目要求DCDC输出纹波应不大于25mV。休眠电流应不超过1mA。"}],
        )
        self.assertEqual(result["status"], "pending_review")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["target_profile_id"], "PROFILE-CUST-A-P3")

        listed = self.service.list_import_packages(project_id="CUST-A-P3")
        self.assertEqual(listed["package_count"], 1)
        self.assertEqual(listed["packages"][0]["candidate_count"], 2)

    def test_import_package_can_auto_promote_and_refresh_effective_requirements(self) -> None:
        result = self.service.import_project_package(
            customer_id="CUST-A",
            project_id="CUST-A-P3",
            project_code="A-DCDC-P3",
            product_family="DCDC",
            sources=[{"name": "req.txt", "text": "项目要求DCDC输出纹波应不大于25mV。"}],
            auto_promote=True,
            promoted_by="reviewer",
            refresh_effective=True,
        )
        self.assertEqual(result["status"], "promoted")
        self.assertEqual(result["promoted_count"], 1)
        self.assertGreaterEqual(result["effective_count"], 1)
        ripple = [item for item in result["effective_requirements"] if item["atom_id"] == "REQATOM-DCDC-OUTPUT-RIPPLE"][0]
        self.assertEqual(ripple["value_numeric"], 25)

    def test_refresh_package_effective_requirements(self) -> None:
        result = self.service.import_project_package(
            customer_id="CUST-A",
            project_id="CUST-A-P3",
            project_code="A-DCDC-P3",
            product_family="DCDC",
            sources=[{"name": "req.txt", "text": "项目要求DCDC输出纹波应不大于25mV。"}],
            auto_promote=True,
            promoted_by="reviewer",
        )
        refreshed = self.service.refresh_package_effective_requirements(result["package_id"])
        self.assertEqual(refreshed["project_id"], "CUST-A-P3")
        self.assertGreaterEqual(refreshed["effective_count"], 1)


if __name__ == "__main__":
    unittest.main()
