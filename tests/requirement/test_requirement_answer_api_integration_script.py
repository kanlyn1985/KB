from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.apply_requirement_answer_api_integration import integrate_answer_api


class RequirementAnswerApiIntegrationScriptTests(unittest.TestCase):
    def test_integrates_answer_query_with_typed_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "answer_api.py"
            path.write_text(
                "from __future__ import annotations\n"
                "from pathlib import Path\n\n"
                "def answer_query(workspace_root: Path, query: str, limit: int = 8) -> dict[str, object]:\n"
                "    return {'direct_answer': query}\n",
                encoding="utf-8",
            )
            changed = integrate_answer_api(path)
            text = path.read_text(encoding="utf-8")
        self.assertTrue(changed)
        self.assertIn("from .requirements.router import try_answer_requirement_query", text)
        self.assertIn("try_answer_requirement_query(workspace_root, query)", text)

    def test_integration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "answer_api.py"
            path.write_text(
                "from .requirements.router import try_answer_requirement_query\n\n"
                "def answer_query(root, query):\n"
                "    # requirement_router_mvp: opt-in soft route for customer/project requirement questions.\n"
                "    requirement_answer = try_answer_requirement_query(root, query)\n"
                "    if requirement_answer is not None:\n"
                "        return requirement_answer\n\n"
                "    return {'direct_answer': query}\n",
                encoding="utf-8",
            )
            changed = integrate_answer_api(path)
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
