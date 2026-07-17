from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_kb.domains.loader import load_domain_pack


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-kb", description="Agent KB Core CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_domain = subparsers.add_parser("inspect-domain", help="Load and summarize a domain pack.")
    inspect_domain.add_argument("--domain-dir", type=Path, required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "inspect-domain":
        pack = load_domain_pack(args.domain_dir)
        print(json.dumps({
            "domain_id": pack.domain_id,
            "name": pack.name,
            "version": pack.version,
            "object_types": sorted(pack.object_types),
            "relation_types": sorted(pack.relation_types),
            "terminology_count": len(pack.terminology),
            "answer_contracts": sorted(pack.answer_contracts),
            "hidden_context_rules": [rule.rule_id for rule in pack.hidden_context_rules],
        }, ensure_ascii=False, indent=2))
        return

    parser.error(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
