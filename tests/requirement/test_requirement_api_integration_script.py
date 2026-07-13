from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RequirementApiIntegrationScriptTest(unittest.TestCase):
    def test_script_refuses_unknown_api_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            source = Path(__file__).resolve().parents[2] / "scripts" / "apply_requirement_api_integration.py"
            target = scripts / "apply_requirement_api_integration.py"
            shutil.copyfile(source, target)
            api_dir = root / "src" / "enterprise_agent_kb" / "api_server"
            api_dir.mkdir(parents=True)
            (api_dir / "__init__.py").write_text("def serve_api(root):\n    return None\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(target)], cwd=root, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to patch", result.stderr + result.stdout)

    def test_script_patches_simple_fastapi_entrypoint_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            source = Path(__file__).resolve().parents[2] / "scripts" / "apply_requirement_api_integration.py"
            target = scripts / "apply_requirement_api_integration.py"
            shutil.copyfile(source, target)
            api_dir = root / "src" / "enterprise_agent_kb" / "api_server"
            api_dir.mkdir(parents=True)
            api_file = api_dir / "__init__.py"
            api_file.write_text(
                "from fastapi import FastAPI\n\n"
                "def serve_api(root):\n"
                "    app = FastAPI()\n"
                "    return app\n",
                encoding="utf-8",
            )
            first = subprocess.run([sys.executable, str(target)], cwd=root, text=True, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            patched = api_file.read_text(encoding="utf-8")
            self.assertIn("create_fastapi_router", patched)
            second = subprocess.run([sys.executable, str(target)], cwd=root, text=True, capture_output=True)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            self.assertEqual(api_file.read_text(encoding="utf-8"), patched)


if __name__ == "__main__":
    unittest.main()
