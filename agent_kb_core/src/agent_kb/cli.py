from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_kb.core.compiler import compile_text_document
from agent_kb.domains.loader import load_domain_pack
from agent_kb.evaluation import RetrievalGoldenCase, evaluate_feedback, evaluate_retrieval
from agent_kb.pipeline import (
    add_persistent_feedback,
    build_compiled_knowledge_index,
    compile_text_to_context_pack,
    compile_text_to_production_store,
    compile_text_to_store,
    list_production_documents,
    query_persistent_store,
    query_production_store,
    set_production_document_status,
)
from agent_kb.service import AgentKBService, create_http_server
from agent_kb.storage import SchemaMigrator, SQLiteKnowledgeStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-kb", description="Agent KB Core CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_domain = subparsers.add_parser("inspect-domain", help="Load and summarize a domain pack.")
    inspect_domain.add_argument("--domain-dir", type=Path, required=True)

    compile_context = subparsers.add_parser(
        "compile-context",
        help="Compile a text file, retrieve evidence, and produce an Agent Context Pack.",
    )
    compile_context.add_argument("--text-file", type=Path, required=True)
    compile_context.add_argument("--query", required=True)
    compile_context.add_argument("--title", default="")
    compile_context.add_argument("--domain-dir", type=Path)
    compile_context.add_argument("--max-evidence-chars", type=int, default=900)
    compile_context.add_argument("--retrieval-top-k", type=int, default=12)
    compile_context.add_argument("--summary-only", action="store_true")

    eval_retrieval = subparsers.add_parser(
        "eval-retrieval",
        help="Evaluate retrieval against a JSON golden-case list.",
    )
    eval_retrieval.add_argument("--text-file", type=Path, required=True)
    eval_retrieval.add_argument("--cases-file", type=Path, required=True)
    eval_retrieval.add_argument("--title", default="")
    eval_retrieval.add_argument("--domain-dir", type=Path)
    eval_retrieval.add_argument("--max-evidence-chars", type=int, default=900)

    index_text = subparsers.add_parser(
        "index-text",
        help="Compile a text file and persist Phase 5 lexical retrieval surfaces.",
    )
    _add_index_arguments(index_text)

    query_store = subparsers.add_parser(
        "query-store",
        help="Query the Phase 5 SQLite index with lexical hybrid retrieval.",
    )
    _add_query_arguments(query_store)

    index_production = subparsers.add_parser(
        "index-production",
        help="Compile and persist lifecycle, vector, graph, and lexical surfaces.",
    )
    _add_index_arguments(index_production)
    index_production.add_argument("--version-label")
    index_production.add_argument("--logical-document-id")
    index_production.add_argument("--summary-only", action="store_true")

    query_production = subparsers.add_parser(
        "query-production",
        help="Query lexical, vector, and graph adapters and build an audited Context Pack.",
    )
    _add_query_arguments(query_production)

    migrate_db = subparsers.add_parser("migrate-db", help="Apply monotonic production schema migrations.")
    migrate_db.add_argument("--db", type=Path, required=True)

    documents = subparsers.add_parser("documents", help="List persisted logical documents and versions.")
    documents.add_argument("--db", type=Path, required=True)
    documents.add_argument("--include-deleted", action="store_true")

    document_status = subparsers.add_parser("document-status", help="Change a logical document lifecycle status.")
    document_status.add_argument("--db", type=Path, required=True)
    document_status.add_argument("--logical-document-id", required=True)
    document_status.add_argument("--status", choices=["active", "deprecated", "deleted"], required=True)

    feedback = subparsers.add_parser("feedback", help="Attach explicit feedback to a retrieval run.")
    feedback.add_argument("--db", type=Path, required=True)
    feedback.add_argument("--run-id", required=True)
    feedback.add_argument("--rating", type=int, required=True)
    feedback.add_argument("--comment", default="")
    feedback.add_argument("--reason", default="")

    eval_feedback = subparsers.add_parser(
        "eval-feedback",
        help="Aggregate explicit feedback into retrieval-tuning signals.",
    )
    eval_feedback.add_argument("--db", type=Path, required=True)

    serve = subparsers.add_parser("serve", help="Run the versioned standard-library JSON service.")
    serve.add_argument("--db", type=Path, required=True)
    serve.add_argument("--domain-dir", type=Path)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)

    return parser


def _add_index_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--text-file", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--domain-dir", type=Path)
    parser.add_argument("--max-evidence-chars", type=int, default=900)


def _add_query_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--domain-dir", type=Path)
    parser.add_argument("--retrieval-top-k", type=int, default=12)
    parser.add_argument("--summary-only", action="store_true")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "inspect-domain":
        pack = load_domain_pack(args.domain_dir)
        print(json.dumps(_domain_summary(pack), ensure_ascii=False, indent=2))
        return

    if args.command == "compile-context":
        domain_pack = _load_optional_domain(args.domain_dir)
        result = compile_text_to_context_pack(
            args.text_file.read_text(encoding="utf-8"),
            query=args.query,
            title=args.title or args.text_file.stem,
            domain_pack=domain_pack,
            source_uri=str(args.text_file),
            max_evidence_chars=args.max_evidence_chars,
            retrieval_top_k=max(1, args.retrieval_top_k),
        )
        _print(result.summary if args.summary_only else result.to_dict())
        return

    if args.command == "eval-retrieval":
        domain_pack = _load_optional_domain(args.domain_dir)
        compilation = compile_text_document(
            args.text_file.read_text(encoding="utf-8"),
            title=args.title or args.text_file.stem,
            domain_pack=domain_pack,
            source_uri=str(args.text_file),
            max_evidence_chars=args.max_evidence_chars,
        )
        index = build_compiled_knowledge_index(compilation, domain_pack=domain_pack)
        raw_cases = json.loads(args.cases_file.read_text(encoding="utf-8"))
        if not isinstance(raw_cases, list):
            parser.error("--cases-file must contain a JSON array")
        cases = [RetrievalGoldenCase(**item) for item in raw_cases if isinstance(item, dict)]
        _print(evaluate_retrieval(cases, index, domain_pack=domain_pack).to_dict())
        return

    if args.command == "index-text":
        domain_pack = _load_optional_domain(args.domain_dir)
        index, store_summary = compile_text_to_store(
            args.text_file.read_text(encoding="utf-8"),
            title=args.title or args.text_file.stem,
            db_path=args.db,
            domain_pack=domain_pack,
            source_uri=str(args.text_file),
            max_evidence_chars=args.max_evidence_chars,
        )
        _print({"db": str(args.db), "compiled_index": index.summary, "store": store_summary})
        return

    if args.command == "query-store":
        result = query_persistent_store(
            args.query,
            db_path=args.db,
            domain_pack=_load_optional_domain(args.domain_dir),
            retrieval_top_k=max(1, args.retrieval_top_k),
        )
        _print(result.summary if args.summary_only else result.to_dict())
        return

    if args.command == "index-production":
        result = compile_text_to_production_store(
            args.text_file.read_text(encoding="utf-8"),
            title=args.title or args.text_file.stem,
            db_path=args.db,
            domain_pack=_load_optional_domain(args.domain_dir),
            source_uri=str(args.text_file),
            version_label=args.version_label,
            logical_document_id=args.logical_document_id,
            max_evidence_chars=args.max_evidence_chars,
        )
        _print(result.summary if args.summary_only else result.to_dict())
        return

    if args.command == "query-production":
        result = query_production_store(
            args.query,
            db_path=args.db,
            domain_pack=_load_optional_domain(args.domain_dir),
            retrieval_top_k=max(1, args.retrieval_top_k),
        )
        _print(result.summary if args.summary_only else result.to_dict())
        return

    if args.command == "migrate-db":
        with SQLiteKnowledgeStore(args.db) as store:
            migrator = SchemaMigrator(store.connection)
            applied = migrator.migrate()
            _print({"db": str(args.db), "applied_versions": applied, "schema_version": migrator.current_version()})
        return

    if args.command == "documents":
        _print(
            {
                "documents": [
                    item.to_dict()
                    for item in list_production_documents(args.db, include_deleted=args.include_deleted)
                ]
            }
        )
        return

    if args.command == "document-status":
        set_production_document_status(args.db, args.logical_document_id, args.status)
        _print({"logical_document_id": args.logical_document_id, "status": args.status})
        return

    if args.command == "feedback":
        metadata = {"reason": args.reason} if args.reason else None
        feedback_id = add_persistent_feedback(
            db_path=args.db,
            run_id=args.run_id,
            rating=args.rating,
            comment=args.comment,
            metadata=metadata,
        )
        _print({"feedback_id": feedback_id, "run_id": args.run_id})
        return

    if args.command == "eval-feedback":
        _print(evaluate_feedback(args.db).to_dict())
        return

    if args.command == "serve":
        service = AgentKBService(db_path=args.db, domain_pack=_load_optional_domain(args.domain_dir))
        server = create_http_server(service, host=args.host, port=args.port)
        print(json.dumps({"status": "serving", "host": args.host, "port": args.port}, ensure_ascii=False))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return

    parser.error(f"unsupported command: {args.command}")


def _load_optional_domain(path: Path | None):
    return load_domain_pack(path) if path else None


def _print(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


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
