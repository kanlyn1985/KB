from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.answer import answer_requirement_query
from enterprise_agent_kb.requirements.api import handle_requirement_api_request
from enterprise_agent_kb.requirements.extraction import RequirementExtractionService
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementExtractionQueryApiTest(unittest.TestCase):
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

    def test_query_lists_pending_requirement_candidates(self) -> None:
        RequirementExtractionService.from_root(self.root).extract_from_text("客户A要求DCDC输出纹波应不大于30mV。")
        answer = answer_requirement_query(self.root, "有哪些候选需求需要评审？")
        self.assertEqual(answer["intent"], "requirement_candidates")
        self.assertIn("待评审需求候选", answer["direct_answer"])
        self.assertIn("REQATOM-DCDC-OUTPUT-RIPPLE", answer["direct_answer"])

    def test_api_extract_list_and_promote_candidate(self) -> None:
        extracted = handle_requirement_api_request(
            self.root,
            "POST",
            "/requirements/candidates/extract",
            body={
                "text": "客户A要求DCDC输出纹波应不大于26mV。",
                "profile_id": "PROFILE-CUST-A-DCDC-COMMON",
            },
        )
        self.assertTrue(extracted["ok"])
        candidate_id = extracted["candidates"][0]["candidate_id"]

        listed = handle_requirement_api_request(self.root, "GET", "/requirements/candidates", query_params={"status": "pending_review"})
        self.assertTrue(listed["ok"])
        self.assertGreaterEqual(listed["candidate_count"], 1)

        promoted = handle_requirement_api_request(
            self.root,
            "POST",
            f"/requirements/candidates/{candidate_id}/promote",
            body={"promoted_by": "reviewer"},
        )
        self.assertTrue(promoted["ok"])
        self.assertEqual(promoted["status"], "promoted")
        self.assertTrue(str(promoted["variant_id"]).startswith("REQVAR-CAND-"))


if __name__ == "__main__":
    unittest.main()
