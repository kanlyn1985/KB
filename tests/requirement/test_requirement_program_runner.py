from __future__ import annotations

import unittest
from pathlib import Path

# Repository root: tests/requirement/ -> parents[2] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class RequirementProgramRunnerPackagingTest(unittest.TestCase):
    def test_runner_script_exists(self):
        self.assertTrue((_REPO_ROOT / "scripts" / "run_requirement_program.py").exists())

    def test_program_plan_exists(self):
        plan = _REPO_ROOT / "docs" / "requirement-program" / "REQUIREMENT_PROGRAM_PLAN.md"
        self.assertTrue(plan.exists())
        self.assertIn("Program Gates", plan.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
