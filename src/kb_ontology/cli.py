"""Operator CLI for kb-ontology."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kb-ontology", description="KB Ontology CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Start HTTP API (trusted, no auth)")
    serve.add_argument("--db", required=True, help="Path to ontology SQLite DB")
    serve.add_argument("--domain-dir", default=None, help="Domain pack directory")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)

    secure = sub.add_parser(
        "secure-serve", help="Start API-key secured multi-tenant HTTP API"
    )
    secure.add_argument(
        "--tenant-db-root",
        required=True,
        help="Directory of per-tenant SQLite files",
    )
    secure.add_argument("--domain-dir", default=None, help="Domain pack directory")
    secure.add_argument("--host", default="0.0.0.0")
    secure.add_argument("--port", type=int, default=8080)

    mcp = sub.add_parser("mcp", help="Run MCP JSON-RPC server on stdio")
    mcp.add_argument("--db", required=True, help="Path to ontology SQLite DB")
    mcp.add_argument("--domain-dir", default=None, help="Domain pack directory")

    health = sub.add_parser("health", help="Print store health JSON")
    health.add_argument("--db", required=True)
    health.add_argument("--domain-dir", default=None)

    query_p = sub.add_parser("query", help="Run one query → ContextPack JSON")
    query_p.add_argument("--db", required=True)
    query_p.add_argument("--domain-dir", default=None)
    query_p.add_argument("--text", required=True, help="Natural-language query")
    query_p.add_argument(
        "--use-llm-understanding",
        action="store_true",
        help="Opt-in LLM refine for QueryFrame",
    )
    query_p.add_argument(
        "--use-llm-judgement",
        action="store_true",
        help="Opt-in LLM semantic judgement when rules need it",
    )

    extract_p = sub.add_parser(
        "extract", help="Extract ontology from a text/markdown file (needs LLM env)"
    )
    extract_p.add_argument("--db", required=True)
    extract_p.add_argument("--domain-dir", required=True)
    extract_p.add_argument("--file", required=True, help="Path to clean document text")
    extract_p.add_argument(
        "--document-id",
        default=None,
        help="Document id for evidence (default: file stem)",
    )
    extract_p.add_argument("--max-tokens", type=int, default=4000)

    batch = sub.add_parser(
        "extract-batch",
        help="Enqueue extract jobs for a directory/file (idempotent by document_id)",
    )
    batch.add_argument("--db", required=True)
    batch.add_argument("--domain-dir", required=True)
    batch.add_argument("--path", required=True, help="File or directory of clean text")
    batch.add_argument("--max-files", type=int, default=None)
    batch.add_argument("--max-tokens", type=int, default=4000)
    batch.add_argument("--no-recursive", action="store_true")

    worker = sub.add_parser(
        "worker-once",
        help="Claim and process one queued extract job (needs LLM env)",
    )
    worker.add_argument("--db", required=True)
    worker.add_argument("--domain-dir", required=True)
    worker.add_argument("--worker-id", default="worker-1")

    worker_run = sub.add_parser(
        "worker-run",
        help="Drain extract job queue until idle (needs LLM env)",
    )
    worker_run.add_argument("--db", required=True)
    worker_run.add_argument("--domain-dir", required=True)
    worker_run.add_argument("--worker-id", default="worker-1")
    worker_run.add_argument("--max-jobs", type=int, default=None)
    worker_run.add_argument(
        "--jobs-db",
        default=None,
        help="Override job queue path (default: <db>.jobs)",
    )

    jobs_p = sub.add_parser("jobs", help="List background jobs")
    jobs_p.add_argument("--db", required=True)
    jobs_p.add_argument("--status", default=None)
    jobs_p.add_argument("--limit", type=int, default=50)

    args = parser.parse_args(argv)

    if args.command == "health":
        from kb_ontology.service.app import OntologyService

        svc = OntologyService(
            db_path=args.db,
            domain_dir=Path(args.domain_dir) if args.domain_dir else None,
        )
        print(json.dumps(svc.health().to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "query":
        from kb_ontology.service.app import OntologyService

        svc = OntologyService(
            db_path=args.db,
            domain_dir=Path(args.domain_dir) if args.domain_dir else None,
        )
        out = svc.query(
            {
                "query": args.text,
                "use_llm_understanding": bool(args.use_llm_understanding),
                "use_llm_judgement": bool(args.use_llm_judgement),
            }
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.command == "extract":
        from kb_ontology.service.app import OntologyService

        path = Path(args.file)
        text = path.read_text(encoding="utf-8")
        document_id = args.document_id or path.stem
        svc = OntologyService(
            db_path=args.db,
            domain_dir=Path(args.domain_dir),
        )
        out = svc.extract(
            {
                "text": text,
                "document_id": document_id,
                "max_tokens": int(args.max_tokens),
            }
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.command == "serve":
        from kb_ontology.service.app import OntologyService
        from kb_ontology.service.http_api import create_http_server

        svc = OntologyService(
            db_path=args.db,
            domain_dir=Path(args.domain_dir) if args.domain_dir else None,
        )
        server = create_http_server(svc, host=args.host, port=args.port)
        print(
            f"kb-ontology listening on http://{args.host}:{args.port}",
            file=sys.stderr,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nshutting down", file=sys.stderr)
        finally:
            server.server_close()
        return 0

    if args.command == "secure-serve":
        from kb_ontology.service.http_api import (
            build_secure_context_from_environment,
            create_secure_http_server,
        )

        ctx = build_secure_context_from_environment(
            tenant_db_root=args.tenant_db_root,
            domain_dir=args.domain_dir,
        )
        server = create_secure_http_server(ctx, host=args.host, port=args.port)
        print(
            f"kb-ontology secure listening on http://{args.host}:{args.port}",
            file=sys.stderr,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nshutting down", file=sys.stderr)
        finally:
            server.server_close()
        return 0

    if args.command == "mcp":
        from kb_ontology import __version__
        from kb_ontology.adapters.mcp import OntologyMCPAdapter
        from kb_ontology.adapters.mcp_transport import (
            MCPJSONRPCServer,
            MCPServerInfo,
        )
        from kb_ontology.service.app import OntologyService

        svc = OntologyService(
            db_path=args.db,
            domain_dir=Path(args.domain_dir) if args.domain_dir else None,
        )
        adapter = OntologyMCPAdapter(svc)
        server = MCPJSONRPCServer(
            adapter,
            server_info=MCPServerInfo(name="kb-ontology", version=__version__),
        )
        server.serve(sys.stdin, sys.stdout)
        return 0

    if args.command == "extract-batch":
        from kb_ontology.service.app import OntologyService

        svc = OntologyService(
            db_path=args.db,
            domain_dir=Path(args.domain_dir),
        )
        out = svc.enqueue_extract_batch(
            {
                "path": args.path,
                "max_files": args.max_files,
                "max_tokens": args.max_tokens,
                "recursive": not args.no_recursive,
            }
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.command == "worker-once":
        from kb_ontology.service.app import OntologyService

        svc = OntologyService(
            db_path=args.db,
            domain_dir=Path(args.domain_dir),
        )
        out = svc.worker_once(worker_id=args.worker_id)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("processed") or out.get("job") is None else 1

    if args.command == "worker-run":
        from kb_ontology.domains.loader import load_domain_pack
        from kb_ontology.ingestion.batch import run_extract_worker_loop
        from kb_ontology.llm.llm_client import LLMChatClient
        from kb_ontology.runtime.jobs import SQLiteJobQueue

        pack = load_domain_pack(Path(args.domain_dir))
        client = LLMChatClient.from_environment()
        jobs_path = args.jobs_db or (str(args.db) + ".jobs")
        queue = SQLiteJobQueue.open(jobs_path)
        done = run_extract_worker_loop(
            queue,
            db_path=args.db,
            domain_pack=pack,
            client=client,
            worker_id=args.worker_id,
            max_jobs=args.max_jobs,
        )
        summary = {
            "processed": len(done),
            "succeeded": sum(1 for j in done if j.status == "succeeded"),
            "failed": sum(1 for j in done if j.status == "failed"),
            "jobs": [j.to_dict() for j in done],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["failed"] == 0 else 2

    if args.command == "jobs":
        from kb_ontology.service.app import OntologyService

        svc = OntologyService(db_path=args.db)
        out = svc.list_jobs(status=args.status, limit=args.limit)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
