from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from enterprise_agent_kb.requirements.cli import handle_requirement_command
from enterprise_agent_kb.requirements.router import try_answer_requirement_query


class RequirementRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "knowledge_base"
        handle_requirement_command(self.root, SimpleNamespace(requirement_command="init-schema"))
        handle_requirement_command(self.root, SimpleNamespace(requirement_command="seed-sample"))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_router_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = try_answer_requirement_query(self.root, "客户A P1项目 DCDC 输出纹波要求是多少？")
        self.assertIsNone(result)

    def test_router_answers_when_enabled(self) -> None:
        with patch.dict(os.environ, {"EAKB_ENABLE_REQUIREMENT_ROUTER": "1"}, clear=True):
            result = try_answer_requirement_query(self.root, "客户A P1项目 DCDC 输出纹波要求是多少？")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["answer_mode"], "requirement_effective")
        self.assertRegex(result["direct_answer"], r"≤\s*30mV")
        self.assertEqual(result["context"]["requirement_router"]["project_id"], "CUST-A-P1")

    def test_router_does_not_hijack_unrelated_questions(self) -> None:
        with patch.dict(os.environ, {"EAKB_ENABLE_REQUIREMENT_ROUTER": "1"}, clear=True):
            result = try_answer_requirement_query(self.root, "什么是控制导引电路？")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
