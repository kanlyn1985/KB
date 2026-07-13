from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.api import handle_requirement_api_request, response_to_json_bytes
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementApiAdapterTest(unittest.TestCase):
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

    def test_get_single_effective_requirement(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "GET",
            "/requirements/projects/CUST-A-P1/effective/REQATOM-DCDC-OUTPUT-RIPPLE",
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["status_code"], 200)
        self.assertEqual(response["value_numeric"], 30)
        self.assertEqual(response["conflict_status"], "none")

    def test_get_project_effective_requirements(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "GET",
            "/requirements/projects/CUST-A-P1/effective",
        )
        self.assertTrue(response["ok"])
        self.assertGreaterEqual(response["count"], 3)
        self.assertIn("requirements", response)

    def test_get_diff_requires_base_profile_id(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "GET",
            "/requirements/projects/CUST-A-P1/diff",
        )
        self.assertFalse(response["ok"])
        self.assertEqual(response["status_code"], 400)
        self.assertEqual(response["error"]["code"], "missing_base_profile_id")

    def test_get_diff_with_query_param(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "GET",
            "/requirements/projects/CUST-A-P1/diff?base_profile_id=PROFILE-CUST-A-DCDC-COMMON",
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["project_id"], "CUST-A-P1")

    def test_get_conflicts(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "GET",
            "/requirements/projects/CUST-A-P2/conflicts",
        )
        self.assertTrue(response["ok"])
        self.assertGreaterEqual(response["issue_count"], 1)

    def test_post_query(self) -> None:
        response = handle_requirement_api_request(
            self.root,
            "POST",
            "/requirements/query",
            body={"query": "客户A P1项目 DCDC 输出纹波要求是多少？"},
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["intent"], "requirement_effective")
        self.assertIn("direct_answer", response)

    def test_json_bytes_serializer(self) -> None:
        payload = response_to_json_bytes({"status_code": 200, "ok": True, "message": "测试"})
        self.assertIn("测试".encode("utf-8"), payload)


if __name__ == "__main__":
    unittest.main()
