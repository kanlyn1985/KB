from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.answer import answer_requirement_query
from enterprise_agent_kb.requirements.api import handle_requirement_api_request
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementPackageImportQueryApiTest(unittest.TestCase):
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

    def test_api_import_package_and_list(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "POST",
            "/requirements/import-packages",
            body={
                "customer_id": "CUST-A",
                "project_id": "CUST-A-P3",
                "project_code": "A-DCDC-P3",
                "product_family": "DCDC",
                "text": "项目要求DCDC输出纹波应不大于25mV。",
            },
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["status_code"], 201)
        self.assertEqual(response["candidate_count"], 1)

        listed = handle_requirement_api_request(self.root, "GET", "/requirements/import-packages?project_id=CUST-A-P3")
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["package_count"], 1)

    def test_api_import_package_refresh(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "POST",
            "/requirements/import-packages",
            body={
                "customer_id": "CUST-A",
                "project_id": "CUST-A-P3",
                "project_code": "A-DCDC-P3",
                "product_family": "DCDC",
                "text": "项目要求DCDC输出纹波应不大于25mV。",
                "auto_promote": True,
                "promoted_by": "reviewer",
            },
        )
        package_id = response["package_id"]
        refreshed = handle_requirement_api_request(self.root, "POST", f"/requirements/import-packages/{package_id}/refresh")
        self.assertTrue(refreshed["ok"])
        self.assertGreaterEqual(refreshed["effective_count"], 1)

    def test_natural_language_lists_import_packages(self) -> None:
        handle_requirement_api_request(
            self.root,
            "POST",
            "/requirements/import-packages",
            body={
                "customer_id": "CUST-A",
                "project_id": "CUST-A-P3",
                "project_code": "A-DCDC-P3",
                "product_family": "DCDC",
                "text": "项目要求DCDC输出纹波应不大于25mV。",
            },
        )
        answer = answer_requirement_query(self.root, "有哪些需求包导入记录？")
        self.assertEqual(answer["intent"], "requirement_import_packages")
        self.assertIn("需求包导入记录", answer["direct_answer"])


if __name__ == "__main__":
    unittest.main()
