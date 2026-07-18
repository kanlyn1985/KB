from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_kb.storage import run_recovery_drill


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-kb-recovery",
        description="Restore a backup into an isolated workspace and verify it.",
    )
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--keep-restored-copy", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = run_recovery_drill(
        args.backup,
        workspace_dir=args.workspace,
        keep_restored_copy=args.keep_restored_copy,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if report.status != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
