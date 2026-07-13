from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.answer import answer_requirement_query
from enterprise_agent_kb.requirements.api import handle_requirement_api_request
from enterprise_agent_kb.requirements.eco import RequirementEcoService
from enterprise_agent_kb.requirements.repository import RequirementRepository
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementEcoQueryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.service = RequirementEcoService(self.repo)

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_natural_language_lists_ecos(self) -> None:
        self.service.create_change_order(
            project_id="CUST-A-P1",
            title="Tighten customer ripple to 20mV",
            variant_id="REQVAR-CUST-A-RIPPLE",
            proposed_change={"value_numeric": 20, "unit": "mV", "operator": "<="},
        )
        result = answer_requirement_query(self.root, "P1 有哪些 ECO 工程变更单？")
        self.assertEqual(result["intent"], "requirement_eco")
        self.assertIn("工程变更单", result["direct_answer"])

    def test_api_create_and_run_cycle(self) -> None:
        create = handle_requirement_api_request(
            self.root,
            "POST",
            "/requirements/ecos",
            body={
                "project_id": "CUST-A-P1",
                "title": "Tighten customer ripple to 20mV",
                "variant_id": "REQVAR-CUST-A-RIPPLE",
                "new_value": 20,
                "unit": "mV",
                "operator": "<=",
            },
        )
        self.assertEqual(create["status_code"], 201)
        self.assertEqual(create["status"], "impact_analyzed")
        eco_id = create["eco_id"]

        listed = handle_requirement_api_request(self.root, "GET", "/requirements/ecos?project_id=CUST-A-P1")
        self.assertEqual(listed["status_code"], 200)
        self.assertGreaterEqual(listed["eco_count"], 1)

        cycle = handle_requirement_api_request(
            self.root,
            "POST",
            "/requirements/ecos/run-cycle",
            body={
                "project_id": "CUST-A-P1",
                "title": "Second tighten customer ripple to 18mV",
                "variant_id": "REQVAR-CUST-A-RIPPLE",
                "new_value": 18,
                "unit": "mV",
                "operator": "<=",
                "actor": "tester",
            },
        )
        self.assertEqual(cycle["status_code"], 201)
        self.assertIn("closed", cycle)
        self.assertIn(cycle["closed"]["status"], {"closed", "gate_blocked"})

        shown = handle_requirement_api_request(self.root, "GET", f"/requirements/ecos/{eco_id}")
        self.assertEqual(shown["status_code"], 200)
        self.assertEqual(shown["eco_id"], eco_id)


if __name__ == "__main__":
    unittest.main()
