"""Batch-index validation documents into an agent_kb_core production SQLite store.

Each document is compiled through the full production pipeline
(document -> evidence -> source units -> facts -> object projections ->
 retrieval cards -> lifecycle/vector/graph/lexical surfaces) exactly like
 the `agent-kb index-production` CLI, but in one process for validation runs.

Usage:
  PYTHONPATH=agent_kb_core/src python3 agent_kb_core/validation/batch_index.py \\
      --db agent_kb_core/validation/baseline.sqlite3 \\
      --domain-dir agent_kb_core/domains/obc_dcdc \\
      --documents "ccu:agent_kb_core/validation/texts/ccu_spec.txt" \\
      --documents "gbt18487_1:agent_kb_core/validation/texts/gbt18487_1.txt"

Pure stdlib; the agent_kb_core package itself has zero runtime dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.pipeline.production_context import compile_text_to_production_store  # noqa: E402


def _parse_documents(raw: list[str]) -> list[tuple[str, Path]]:
    docs: list[tuple[str, Path]] = []
    for item in raw:
        doc_id, _, path = item.partition(":")
        if not doc_id or not path:
            raise SystemExit(f"invalid --documents entry (expected id:path): {item!r}")
        docs.append((doc_id, Path(path)))
    return docs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="target SQLite database (created if missing)")
    parser.add_argument("--domain-dir", type=Path, default=None, help="domain pack directory")
    parser.add_argument("--documents", action="append", required=True, metavar="ID:PATH")
    parser.add_argument("--version-label", default="v1")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--max-evidence-chars", type=int, default=900)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    domain_pack = load_domain_pack(args.domain_dir) if args.domain_dir else None
    results = []
    for logical_id, text_path in _parse_documents(args.documents):
        if not text_path.is_file():
            raise SystemExit(f"missing text file: {text_path}")
        text = text_path.read_text(encoding="utf-8")
        started = time.monotonic()
        result = compile_text_to_production_store(
            text,
            title=logical_id,
            db_path=args.db,
            domain_pack=domain_pack,
            source_uri=str(text_path),
            version_label=args.version_label,
            logical_document_id=logical_id,
            tenant_id=args.tenant_id,
            max_evidence_chars=args.max_evidence_chars,
        )
        elapsed = round(time.monotonic() - started, 3)
        summary = result.summary
        entry = {
            "logical_document_id": logical_id,
            "text_file": str(text_path),
            "chars": len(text),
            "elapsed_seconds": elapsed,
            "summary": summary,
        }
        results.append(entry)
        print(json.dumps(entry, ensure_ascii=False, default=str))

    print(json.dumps({"db": str(args.db), "documents_indexed": len(results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
