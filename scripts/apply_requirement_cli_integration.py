#!/usr/bin/env python3
"""Apply Requirement Resolver CLI integration (modular cli/ package layout).

Idempotent: re-running after integration prints "already integrated" and
makes no changes. Targets the modular CLI orchestrator
(`src/enterprise_agent_kb/cli/_orchestrator.py` + `cli/_requirement.py`),
NOT the legacy single-file `cli.py` shipped in the overlay package.

Three edits to _orchestrator.py:
  1. import line for _requirement register/handle
  2. register_subcommand call in build_parser
  3. handle_command entry in the dispatch loop

Plus creates cli/_requirement.py adapter if absent.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ORCH_PATH = REPO_ROOT / "src" / "enterprise_agent_kb" / "cli" / "_orchestrator.py"
ADAPTER_PATH = REPO_ROOT / "src" / "enterprise_agent_kb" / "cli" / "_requirement.py"

IMPORT_LINE = (
    "from ._requirement import register_subcommand as _requirement_register, "
    "handle_command as _requirement_handle\n"
)
REGISTER_LINE = "    _requirement_register(subparsers)\n"
HANDLE_LINE = "        _requirement_handle,\n"

ADAPTER_CONTENT = '''"""Requirement subcommand family.

Adapter wiring the Requirement Resolver program
(`enterprise_agent_kb.requirements.cli`) into the modular CLI orchestrator
pattern (`register_subcommand` + `handle_command`). Replaces the legacy
single-file `cli.py` patch shipped in the overlay package.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from enterprise_agent_kb.requirements.cli import (
    configure_parser as _configure_requirement_parser,
    handle_requirement_command,
)


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "requirement",
        help="Manage customer/project requirement profiles and effective requirements.",
    )
    _configure_requirement_parser(parser)


def handle_command(args: argparse.Namespace, schema_path: Path) -> bool:
    if args.command != "requirement":
        return False
    result: dict[str, Any] = handle_requirement_command(args.root, args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return True
'''


def fail(msg: str) -> None:
    raise SystemExit(f"[apply_requirement_cli_integration] {msg}")


def integrate_cli(repo_root: Path) -> bool:
    """Apply CLI integration to the given repo root.

    Returns True if any change was made (adapter created or orchestrator
    patched), False if already fully integrated. Raises SystemExit if a
    required anchor is missing (manual patch needed).
    """
    orch_path = repo_root / "src" / "enterprise_agent_kb" / "cli" / "_orchestrator.py"
    adapter_path = repo_root / "src" / "enterprise_agent_kb" / "cli" / "_requirement.py"
    if not orch_path.exists():
        fail(f"cannot find {orch_path.relative_to(repo_root)}; run from repo root.")
    created_adapter = False
    if not adapter_path.exists():
        adapter_path.write_text(ADAPTER_CONTENT, encoding="utf-8")
        created_adapter = True

    text = orch_path.read_text(encoding="utf-8")
    changed = False

    # 1. import line (anchor: after _serve import)
    if IMPORT_LINE not in text:
        anchor = "from ._serve import register_subcommand as _serve_register, handle_command as _serve_handle\n"
        if anchor not in text:
            fail("_serve import anchor not found; patch _orchestrator.py manually.")
        text = text.replace(anchor, anchor + IMPORT_LINE, 1)
        changed = True

    # 2. register call in build_parser (anchor: after _serve_register)
    if REGISTER_LINE not in text:
        anchor = "    _serve_register(subparsers)\n"
        if anchor not in text:
            fail("_serve_register anchor not found; patch _orchestrator.py manually.")
        text = text.replace(anchor, anchor + REGISTER_LINE, 1)
        changed = True

    # 3. handle entry in dispatch loop (anchor: after _serve_handle)
    if HANDLE_LINE not in text:
        anchor = "        _serve_handle,\n"
        if anchor not in text:
            fail("_serve_handle anchor not found; patch _orchestrator.py manually.")
        text = text.replace(anchor, anchor + HANDLE_LINE, 1)
        changed = True

    if changed:
        orch_path.write_text(text, encoding="utf-8")
    return created_adapter or changed


def main() -> None:
    if not (REPO_ROOT / "pyproject.toml").exists():
        fail("pyproject.toml not found; run from repository root.")
    changed = integrate_cli(REPO_ROOT)
    if not changed:
        print("requirement CLI integration already applied; no changes made.")
        return
    print("requirement CLI integration applied successfully.")


if __name__ == "__main__":
    main()
