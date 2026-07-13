from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.extraction import RequirementExtractionService
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementExtractionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.service = RequirementExtractionService(self.repo)

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp dir
            # is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_extracts_requirement_candidates_from_text(self) -> None:
        result = self.service.extract_from_text(
            "客户A要求DCDC输出纹波应不大于30mV。满载效率应不低于95%。",
            profile_id="PROFILE-CUST-A-DCDC-COMMON",
        )
        self.assertEqual(result["candidate_count"], 2)
        atoms = {item["suggested_atom_id"] for item in result["candidates"]}
        self.assertIn("REQATOM-DCDC-OUTPUT-RIPPLE", atoms)
        self.assertIn("REQATOM-DCDC-EFFICIENCY", atoms)
        ripple = [item for item in result["candidates"] if item["suggested_atom_id"] == "REQATOM-DCDC-OUTPUT-RIPPLE"][0]
        self.assertEqual(ripple["operator"], "<=")
        self.assertEqual(ripple["value_numeric"], 30)
        self.assertEqual(ripple["unit"], "mV")

    def test_promote_candidate_creates_requirement_variant(self) -> None:
        result = self.service.extract_from_text(
            "客户A要求DCDC输出纹波应不大于28mV。",
            profile_id="PROFILE-CUST-A-DCDC-COMMON",
            evidence_id="EV-CUSTOMER-RIPPLE-28",
        )
        candidate_id = result["candidates"][0]["candidate_id"]
        promoted = self.service.promote_candidate(candidate_id, promoted_by="reviewer")
        self.assertEqual(promoted["status"], "promoted")
        variant_id = promoted["variant_id"]
        with self.repo.connection() as connection:
            row = connection.execute(
                "SELECT * FROM requirement_variants WHERE variant_id = ?",
                (variant_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["value_numeric"], 28)
        self.assertEqual(row["source_type"], "candidate")

    def test_reject_candidate_marks_review_state(self) -> None:
        result = self.service.extract_from_text("客户A要求休眠电流应不超过1mA。")
        candidate_id = result["candidates"][0]["candidate_id"]
        rejected = self.service.reject_candidate(candidate_id, reviewer="reviewer", reason="duplicate")
        self.assertEqual(rejected["status"], "rejected")
        listed = self.service.list_candidates(status="rejected")
        self.assertEqual(listed["candidate_count"], 1)


if __name__ == "__main__":
    unittest.main()
