from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent_kb.adapters import (
    AgentKBMCPAdapter,
    MCPJSONRPCServer,
    build_openapi_spec,
    generate_python_client,
)
from agent_kb.core.compiler import compile_text_document
from agent_kb.domains.loader import load_domain_pack
from agent_kb.embeddings import RemoteJSONEmbeddingProvider
from agent_kb.evaluation import RetrievalGoldenCase, evaluate_feedback, evaluate_retrieval
from agent_kb.observability import OTLPHTTPJSONExporter
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
from agent_kb.retrieval import QdrantVectorBackend
from agent_kb.runtime import SQLiteJobQueue
from agent_kb.security import (
    EnvironmentSecretProvider,
    JSONFileSecretProvider,
    RotatingAPIKeyAuthenticator,
)
from agent_kb.service import (
    AgentKBService,
    HardenedAgentKBService,
    HardenedServiceConfig,
    TLSConfig,
    create_http_server,
    create_secure_http_server,
    enable_tls,
)
from agent_kb.storage import (
    BackupRetentionPolicy,
    FilesystemBackupReplicator,
    KnowledgeMaintenance,
    LegalHoldStore,
    RetentionManager,
    RetentionPolicy,
    SchemaMigrator,
    SQLiteBackupManager,
    SQLiteKnowledgeStore,
)


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
        help="Compile a text file and persist lexical retrieval surfaces.",
    )
    _add_index_arguments(index_text)

    query_store = subparsers.add_parser(
        "query-store",
        help="Query the SQLite index with lexical hybrid retrieval.",
    )
    _add_query_arguments(query_store)

    index_production = subparsers.add_parser(
        "index-production",
        help="Compile and persist lifecycle, vector, graph, and lexical surfaces.",
    )
    _add_index_arguments(index_production)
    index_production.add_argument("--version-label")
    index_production.add_argument("--logical-document-id")
    index_production.add_argument("--tenant-id", default="default")
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

    purge_document = subparsers.add_parser(
        "purge-document",
        help="Transactionally remove one logical document and local derived index surfaces.",
    )
    purge_document.add_argument("--db", type=Path, required=True)
    purge_document.add_argument("--logical-document-id", required=True)

    backup = subparsers.add_parser("backup", help="Create, verify, replicate, and prune SQLite backups.")
    backup.add_argument("--db", type=Path, required=True)
    backup.add_argument("--backup-dir", type=Path, required=True)
    backup.add_argument("--replica-dir", type=Path)
    backup.add_argument("--tenant-id", default="default")
    backup.add_argument("--keep-last", type=int, default=5)
    backup.add_argument("--keep-days", type=int, default=30)

    queue_index = subparsers.add_parser("queue-index", help="Submit an idempotent persistent index job.")
    queue_index.add_argument("--db", type=Path, required=True)
    queue_index.add_argument("--text-file", type=Path, required=True)
    queue_index.add_argument("--title", default="")
    queue_index.add_argument("--logical-document-id")
    queue_index.add_argument("--version-label")
    queue_index.add_argument("--tenant-id", default="default")
    queue_index.add_argument("--max-attempts", type=int, default=3)
    queue_index.add_argument("--idempotency-key")

    worker_once = subparsers.add_parser("worker-once", help="Claim and execute at most one background job.")
    worker_once.add_argument("--db", type=Path, required=True)
    worker_once.add_argument("--domain-dir", type=Path)
    worker_once.add_argument("--worker-id", default="cli-worker")
    worker_once.add_argument("--tenant-id")

    legal_hold = subparsers.add_parser("legal-hold", help="Place a legal hold on one logical document.")
    legal_hold.add_argument("--db", type=Path, required=True)
    legal_hold.add_argument("--tenant-id", default="default")
    legal_hold.add_argument("--logical-document-id", required=True)
    legal_hold.add_argument("--reason", required=True)
    legal_hold.add_argument("--created-by", default="cli-admin")

    release_hold = subparsers.add_parser("release-hold", help="Release a legal hold.")
    release_hold.add_argument("--db", type=Path, required=True)
    release_hold.add_argument("--hold-id", required=True)

    retention = subparsers.add_parser("retention", help="Evaluate or execute a retention policy.")
    retention.add_argument("--db", type=Path, required=True)
    retention.add_argument("--tenant-id", default="default")
    retention.add_argument("--policy-id", default="cli-retention")
    retention.add_argument("--retain-days", type=int, required=True)
    retention.add_argument("--status", action="append", dest="statuses")
    retention.add_argument("--execute", action="store_true")

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

    openapi = subparsers.add_parser("openapi", help="Print the Phase 8 OpenAPI 3.1 contract.")
    openapi.add_argument("--output", type=Path)

    generate_client = subparsers.add_parser("generate-client", help="Generate a dependency-free Python API client.")
    generate_client.add_argument("--output", type=Path, required=True)
    generate_client.add_argument("--class-name", default="AgentKBClient")

    mcp_stdio = subparsers.add_parser("mcp-stdio", help="Run the MCP JSON-RPC stdio transport.")
    mcp_stdio.add_argument("--db", type=Path, required=True)
    mcp_stdio.add_argument("--domain-dir", type=Path)

    serve = subparsers.add_parser("serve", help="Run the trusted-network JSON service.")
    serve.add_argument("--db", type=Path, required=True)
    serve.add_argument("--domain-dir", type=Path)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)

    secure_serve = subparsers.add_parser(
        "secure-serve",
        help="Run the authenticated, tenant-isolated deployment service.",
    )
    secure_serve.add_argument("--tenant-db-root", type=Path, required=True)
    secure_serve.add_argument("--backup-root", type=Path, required=True)
    secure_serve.add_argument("--backup-replica-dir", type=Path)
    secure_serve.add_argument("--domain-dir", type=Path)
    secure_serve.add_argument("--host", default="127.0.0.1")
    secure_serve.add_argument("--port", type=int, default=8443)
    secure_serve.add_argument("--rate-limit-capacity", type=int, default=60)
    secure_serve.add_argument("--rate-limit-refill", type=float, default=1.0)
    secure_serve.add_argument("--distributed-rate-limit", action="store_true")
    secure_serve.add_argument("--rate-limit-window", type=int, default=60)
    secure_serve.add_argument("--api-key-secret-file", type=Path)
    secure_serve.add_argument("--api-key-secret-name", default="AGENT_KB_API_KEYS")
    secure_serve.add_argument("--secret-refresh-seconds", type=float, default=30.0)
    secure_serve.add_argument("--remote-embedding", action="store_true")
    secure_serve.add_argument("--qdrant-url")
    secure_serve.add_argument("--qdrant-collection")
    secure_serve.add_argument("--qdrant-api-key-env", default="QDRANT_API_KEY")
    secure_serve.add_argument("--otlp", action="store_true")
    secure_serve.add_argument("--tls-cert", type=Path)
    secure_serve.add_argument("--tls-key", type=Path)
    secure_serve.add_argument("--tls-ca", type=Path)
    secure_serve.add_argument("--require-client-cert", action="store_true")

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
        _print(_domain_summary(load_domain_pack(args.domain_dir)))
        return

    if args.command == "compile-context":
        result = compile_text_to_context_pack(
            args.text_file.read_text(encoding="utf-8"),
            query=args.query,
            title=args.title or args.text_file.stem,
            domain_pack=_load_optional_domain(args.domain_dir),
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
            tenant_id=args.tenant_id,
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

    if args.command == "purge-document":
        with SQLiteKnowledgeStore(args.db) as store:
            if LegalHoldStore(store.connection).active_for(args.logical_document_id):
                parser.error("document is protected by an active legal hold")
            _print(KnowledgeMaintenance(store.connection).purge_document(args.logical_document_id).to_dict())
        return

    if args.command == "backup":
        record = SQLiteBackupManager(args.db, tenant_id=args.tenant_id).create_backup(args.backup_dir)
        payload = record.to_dict()
        if args.replica_dir:
            payload["replication"] = FilesystemBackupReplicator(args.replica_dir).replicate(record).to_dict()
        payload["pruned"] = BackupRetentionPolicy(
            keep_last=max(1, args.keep_last),
            keep_days=max(0, args.keep_days),
        ).prune(args.backup_dir)
        _print(payload)
        return

    if args.command == "queue-index":
        payload = {
            "text": args.text_file.read_text(encoding="utf-8"),
            "title": args.title or args.text_file.stem,
            "logical_document_id": args.logical_document_id,
            "version_label": args.version_label,
            "source_uri": str(args.text_file),
        }
        with SQLiteKnowledgeStore(args.db) as store:
            job = SQLiteJobQueue(store.connection).submit(
                "index_text",
                payload,
                tenant_id=args.tenant_id,
                max_attempts=max(1, args.max_attempts),
                idempotency_key=args.idempotency_key,
            )
        _print(job.to_dict())
        return

    if args.command == "worker-once":
        service = AgentKBService(db_path=args.db, domain_pack=_load_optional_domain(args.domain_dir))
        with SQLiteKnowledgeStore(args.db) as store:
            job = SQLiteJobQueue(store.connection).run_once(
                args.worker_id,
                {"index_text": service.index},
                tenant_id=args.tenant_id,
            )
        _print({"job": job.to_dict() if job else None})
        return

    if args.command == "legal-hold":
        with SQLiteKnowledgeStore(args.db) as store:
            hold = LegalHoldStore(store.connection).place(
                tenant_id=args.tenant_id,
                logical_document_id=args.logical_document_id,
                reason=args.reason,
                created_by=args.created_by,
            )
        _print(hold.to_dict())
        return

    if args.command == "release-hold":
        with SQLiteKnowledgeStore(args.db) as store:
            LegalHoldStore(store.connection).release(args.hold_id)
        _print({"hold_id": args.hold_id, "status": "released"})
        return

    if args.command == "retention":
        policy = RetentionPolicy(
            policy_id=args.policy_id,
            tenant_id=args.tenant_id,
            retain_days=max(0, args.retain_days),
            statuses=tuple(args.statuses or ["deprecated", "deleted"]),
            dry_run=not args.execute,
        )
        with SQLiteKnowledgeStore(args.db) as store:
            result = RetentionManager(store.connection).execute(policy)
        _print(result.to_dict())
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

    if args.command == "openapi":
        payload = build_openapi_spec()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            _print({"output": str(args.output)})
        else:
            _print(payload)
        return

    if args.command == "generate-client":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(generate_python_client(class_name=args.class_name), encoding="utf-8")
        _print({"output": str(args.output), "class_name": args.class_name})
        return

    if args.command == "mcp-stdio":
        service = AgentKBService(db_path=args.db, domain_pack=_load_optional_domain(args.domain_dir))
        MCPJSONRPCServer(AgentKBMCPAdapter(service)).serve(sys.stdin, sys.stdout)
        return

    if args.command == "serve":
        service = AgentKBService(db_path=args.db, domain_pack=_load_optional_domain(args.domain_dir))
        _serve(create_http_server(service, host=args.host, port=args.port), args.host, args.port, authenticated=False, tls=False)
        return

    if args.command == "secure-serve":
        if bool(args.tls_cert) != bool(args.tls_key):
            parser.error("--tls-cert and --tls-key must be supplied together")
        secret_provider = (
            JSONFileSecretProvider(args.api_key_secret_file)
            if args.api_key_secret_file
            else EnvironmentSecretProvider()
        )
        authenticator = RotatingAPIKeyAuthenticator(
            secret_provider,
            secret_name=args.api_key_secret_name,
            refresh_interval_seconds=max(0.1, args.secret_refresh_seconds),
        )
        embedding_provider = RemoteJSONEmbeddingProvider.from_environment() if args.remote_embedding else None
        vector_backend = None
        if args.qdrant_url or args.qdrant_collection:
            if not args.qdrant_url or not args.qdrant_collection:
                parser.error("--qdrant-url and --qdrant-collection must be supplied together")
            vector_backend = QdrantVectorBackend(
                base_url=args.qdrant_url,
                collection_name=args.qdrant_collection,
                api_key=os.environ.get(args.qdrant_api_key_env, ""),
            )
        backup_replicators = (
            [FilesystemBackupReplicator(args.backup_replica_dir)]
            if args.backup_replica_dir
            else []
        )
        hardened = HardenedAgentKBService(
            config=HardenedServiceConfig(
                tenant_db_root=args.tenant_db_root,
                backup_root=args.backup_root,
                rate_limit_capacity=max(1, args.rate_limit_capacity),
                rate_limit_refill_per_second=max(0.001, args.rate_limit_refill),
                distributed_rate_limit=args.distributed_rate_limit,
                rate_limit_window_seconds=max(1, args.rate_limit_window),
            ),
            authenticator=authenticator,
            domain_pack=_load_optional_domain(args.domain_dir),
            embedding_provider=embedding_provider,
            external_vector_backend=vector_backend,
            backup_replicators=backup_replicators,
            telemetry_exporter=OTLPHTTPJSONExporter.from_environment() if args.otlp else None,
        )
        server = create_secure_http_server(hardened, host=args.host, port=args.port)
        tls_enabled = bool(args.tls_cert)
        if tls_enabled:
            server = enable_tls(
                server,
                TLSConfig(
                    certificate_file=args.tls_cert,
                    private_key_file=args.tls_key,
                    ca_file=args.tls_ca,
                    require_client_certificate=args.require_client_cert,
                ),
            )
        _serve(server, args.host, args.port, authenticated=True, tls=tls_enabled)
        return

    parser.error(f"unsupported command: {args.command}")


def _serve(server, host: str, port: int, *, authenticated: bool, tls: bool) -> None:
    print(
        json.dumps(
            {
                "status": "serving",
                "host": host,
                "port": port,
                "authenticated": authenticated,
                "tls": tls,
            },
            ensure_ascii=False,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


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
