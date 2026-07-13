from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enterprise_agent_kb.requirements.baseline import RequirementBaselineService
from enterprise_agent_kb.requirements.repository import RequirementRepository, utc_now
from enterprise_agent_kb.requirements.seed import seed_sample_data


class RequirementBaselineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge_base"
        seed_sample_data(self.root)
        self.repo = RequirementRepository(self.root)
        self.service = RequirementBaselineService(self.repo)

    def tearDown(self) -> None:
        try:
            self.tmp.cleanup()
        except OSError:
            # Windows can briefly hold the sqlite file handle; the temp
            # dir is cleaned by the OS later. Ignore cleanup errors here.
            pass

    def test_freeze_project_baseline_captures_effective_requirements(self) -> None:
        baseline = self.service.freeze_project_baseline("CUST-A-P1", frozen_by="tester")
        self.assertEqual(baseline["status"], "frozen")
        self.assertEqual(baseline["project_id"], "CUST-A-P1")
        self.assertGreaterEqual(baseline["requirement_count"], 3)
        self.assertEqual(baseline["conflict_count"], 0)

        loaded = self.service.get_baseline(baseline["baseline_id"])
        self.assertEqual(loaded["baseline_id"], baseline["baseline_id"])
        self.assertEqual(len(loaded["items"]), baseline["requirement_count"])
        ripple = [item for item in loaded["items"] if item["atom_id"] == "REQATOM-DCDC-OUTPUT-RIPPLE"][0]
        self.assertEqual(ripple["value_numeric"], 30)
        self.assertEqual(ripple["unit"], "mV")

    def test_compare_two_baselines_detects_changed_requirement(self) -> None:
        first = self.service.freeze_project_baseline("CUST-A-P1", baseline_version="v1")
        now = utc_now()
        self.repo.insert_many(
            "requirement_variants",
            [
                {
                    "variant_id": "REQVAR-P1-RIPPLE-V2",
                    "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE",
                    "profile_id": "PROFILE-CUST-A-P1",
                    "requirement_text": "P1 项目 DCDC 输出纹波 ≤ 25mV @ 85℃",
                    "parameter_name": "output_ripple",
                    "operator": "<=",
                    "value_numeric": 25,
                    "value_text": None,
                    "unit": "mV",
                    "condition_json": '{"load":"full_load","temperature":"85C"}',
                    "requirement_type": "limit",
                    "mandatory_level": "project_specific",
                    "priority": 50,
                    "source_type": "test",
                    "source_id": None,
                    "evidence_id": "SAMPLE-EV-P1-RIPPLE-V2",
                    "fact_id": None,
                    "document_id": None,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )
        second = self.service.freeze_project_baseline("CUST-A-P1", baseline_version="v2", parent_baseline_id=first["baseline_id"])
        diff = self.service.compare_baselines(first["baseline_id"], second["baseline_id"])
        self.assertEqual(diff["summary"]["changed"], 1)
        self.assertEqual(diff["changed"][0]["atom_id"], "REQATOM-DCDC-OUTPUT-RIPPLE")

    def test_drift_and_rollback_plan_are_dry_run(self) -> None:
        frozen = self.service.freeze_project_baseline("CUST-A-P1", baseline_version="v1")
        now = utc_now()
        self.repo.insert_many(
            "requirement_variants",
            [
                {
                    "variant_id": "REQVAR-P1-RIPPLE-DRIFT",
                    "atom_id": "REQATOM-DCDC-OUTPUT-RIPPLE",
                    "profile_id": "PROFILE-CUST-A-P1",
                    "requirement_text": "P1 项目 DCDC 输出纹波 ≤ 26mV @ 85℃",
                    "parameter_name": "output_ripple",
                    "operator": "<=",
                    "value_numeric": 26,
                    "value_text": None,
                    "unit": "mV",
                    "condition_json": '{"load":"full_load","temperature":"85C"}',
                    "requirement_type": "limit",
                    "mandatory_level": "project_specific",
                    "priority": 40,
                    "source_type": "test",
                    "source_id": None,
                    "evidence_id": "SAMPLE-EV-P1-RIPPLE-DRIFT",
                    "fact_id": None,
                    "document_id": None,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )
        drift = self.service.detect_drift(frozen["baseline_id"])
        self.assertEqual(drift["summary"]["drifted"], 1)
        plan = self.service.build_rollback_plan(frozen["baseline_id"])
        self.assertEqual(plan["mode"], "dry_run")
        self.assertEqual(plan["action_count"], 1)
        self.assertEqual(plan["actions"][0]["action"], "restore_requirement_variant_or_overlay")


if __name__ == "__main__":
    unittest.main()
