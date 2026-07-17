from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_kb.domains.loader import load_domain_pack
from agent_kb.pipeline import compile_text_to_context_pack


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-kb", description="Agent KB Core CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_domain = subparsers.add_parser("inspect-domain", help="Load and summarize a domain pack.")
    inspect_domain.add_argument("--domain-dir", type=Path, required=True)

    compile_context = subparsers.add_parser(
        "compile-context",
        help="Compile a text file and produce an Agent Context Pack for one query.",
    )
    compile_context.add_argument("--text-file", type=Path, required=True)
    compile_context.add_argument("--query", required=True)
    compile_context.add_argument("--title", default="")
    compile_context.add_argument("--domain-dir", type=Path)
    compile_context.add_argument("--max-evidence-chars", type=int, default=900)
    compile_context.add_argument(
        "--summary-only",
        action="store_true",
        help="Print only pipeline counts rather than the full structured payload.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "inspect-domain":
        pack = load_domain_pack(args.domain_dir)
        print(json.dumps(_domain_summary(pack), ensure_ascii=False, indent=2))
        return

    if args.command == "compile-context":
        domain_pack = load_domain_pack(args.domain_dir) if args.domain_dir else None
        text = args.text_file.read_text(encoding="utf-8")
        result = compile_text_to_context_pack(
            text,
            query=args.query,
            title=args.title or args.text_file.stem,
            domain_pack=domain_pack,
            source_uri=str(args.text_file),
            max_evidence_chars=args.max_evidence_chars,
        )
        payload = result.summary if args.summary_only else result.to_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    parser.error(f"unsupported command: {args.command}")


def _domain_summary(pack) -> dict[str, object]:
    return {
        "domain_id": pack.domain_id,
        "name": pack.name,
        "version": pack.version,
        "object_types": sorted(pack.object_types),
        "relation_types": sorted(pack.relation_types),
        "terminology_count": len(pack.terminology),
        "answer_contracts": sorted(pack.answer_contracts),
        "hidden_context_rules": [rule.rule_id for rule in pack.hidden_context_rules],
    }


if __name__ == "__main__":
    main()
