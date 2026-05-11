from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent_tools import run_agent_query
from .answer_api import answer_query
from .api_server import serve_api
from .mcp_server import run_mcp_stdio
from .bootstrap import initialize_workspace, workspace_status
from .corpus_eval import generate_corpus_eval_cases, run_corpus_retrieval_eval
from .coverage import build_coverage_for_document, build_test_gap_candidates_for_document
from .coverage_diagnostics import build_all_docs_uncovered_priority_report
from .doc_diagnostics import build_document_diagnostics
from .evidence import build_evidence_for_document
from .entities import build_entities_for_document
from .facts import build_facts_for_document
from .generated_tests import (
    assess_all_coverage_test_draft_readiness,
    assess_coverage_test_draft_readiness_for_document,
    close_coverage_test_gaps,
    generate_coverage_test_drafts_for_document,
    promote_coverage_test_drafts_for_document,
    run_coverage_promoted_pytest_for_document,
    run_coverage_promoted_tests_for_document,
    run_query_repair_smoke_eval,
    validate_coverage_test_drafts_for_document,
)
from .graph import build_graph_for_document
from .graph_report import build_graph_health_report, format_graph_health_report
from .governance import assess_pending_quality
from .ingest import register_document
from .jobs import run_parse_jobs, summarize_job_results
from .parse import parse_document
from .pipeline import (
    run_batch_pipeline,
    run_document_pipeline,
    run_document_pipeline_and_tests,
    run_file_pipeline,
    run_file_pipeline_and_tests,
)
from .query_api import build_query_context
from .quality import assess_document_quality
from .retrieval import search_knowledge_base
from .user_query_retrieval_eval import run_user_query_retrieval_eval
from .workspace_admin import reset_workspace_data
from .wiki_compiler import build_wiki_for_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eakb",
        description="Enterprise agent knowledge base bootstrap CLI.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("knowledge_base"),
        help="Workspace root directory for the knowledge base.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create the workspace layout and SQLite schema.")
    subparsers.add_parser("status", help="Print workspace and database status.")

    register_parser = subparsers.add_parser(
        "register",
        help="Register a source document into the knowledge base.",
    )
    register_parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the source file to ingest.",
    )

    reset_parser = subparsers.add_parser(
        "reset-workspace",
        help="Delete ingested records and generated artifacts.",
    )
    reset_parser.add_argument(
        "--drop-raw",
        action="store_true",
        help="Also delete files under raw/.",
    )

    parse_parser = subparsers.add_parser(
        "parse-document",
        help="Parse a registered document into pages and blocks.",
    )
    parse_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to parse.",
    )

    convert_document_parser = subparsers.add_parser(
        "convert-document",
        help="Only parse/convert a registered document and stop after normalized output.",
    )
    convert_document_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to convert.",
    )

    jobs_parser = subparsers.add_parser(
        "run-jobs",
        help="Run pending background jobs.",
    )
    jobs_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of jobs to execute.",
    )

    quality_parser = subparsers.add_parser(
        "quality-document",
        help="Assess quality for a parsed document.",
    )
    quality_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to assess.",
    )

    quality_batch_parser = subparsers.add_parser(
        "quality-batch",
        help="Assess quality for parsed documents.",
    )
    quality_batch_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of documents to assess.",
    )

    evidence_parser = subparsers.add_parser(
        "build-evidence",
        help="Build evidence objects for a quality-assessed document.",
    )
    evidence_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build evidence for.",
    )

    facts_parser = subparsers.add_parser(
        "build-facts",
        help="Build facts for an evidenced document.",
    )
    facts_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build facts for.",
    )

    entities_parser = subparsers.add_parser(
        "build-entities",
        help="Build entities and attach facts for a document.",
    )
    entities_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build entities for.",
    )

    wiki_parser = subparsers.add_parser(
        "build-wiki",
        help="Build wiki pages for a document.",
    )
    wiki_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build wiki for.",
    )

    coverage_parser = subparsers.add_parser(
        "build-coverage",
        help="Build source-unit coverage reports for a document.",
    )
    coverage_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build coverage for.",
    )

    test_gaps_parser = subparsers.add_parser(
        "build-test-gaps",
        help="Build test-gap candidates for source units that are ingested but not tested.",
    )
    test_gaps_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to inspect.",
    )
    test_gaps_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of candidates to emit.",
    )
    test_gaps_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild coverage before deriving test-gap candidates.",
    )

    draft_tests_parser = subparsers.add_parser(
        "generate-coverage-test-drafts",
        help="Generate reviewable draft tests from coverage test-gap candidates.",
    )
    draft_tests_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to inspect.",
    )
    draft_tests_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of draft cases to emit.",
    )
    draft_tests_parser.add_argument(
        "--rebuild-coverage",
        action="store_true",
        help="Rebuild coverage before deriving draft tests.",
    )
    draft_tests_parser.add_argument(
        "--validate",
        action="store_true",
        help="Run each draft through the answer/query validator.",
    )

    close_gaps_parser = subparsers.add_parser(
        "close-coverage-test-gaps",
        help="Generate, validate, promote, and rebuild coverage tests for golden-gap source units.",
    )
    close_gaps_parser.add_argument(
        "--doc-id",
        action="append",
        default=None,
        help="Document ID to process. Repeat to process multiple docs. Defaults to all active documents.",
    )
    close_gaps_parser.add_argument(
        "--limit-per-doc",
        type=int,
        default=25,
        help="Maximum number of draft cases to emit per document.",
    )
    close_gaps_parser.add_argument(
        "--mode",
        choices=["trace", "answer", "hybrid"],
        default="trace",
        help="Validation mode for generated coverage drafts.",
    )
    close_gaps_parser.add_argument(
        "--rebuild-coverage",
        action="store_true",
        help="Rebuild each document's coverage before deriving draft tests.",
    )
    close_gaps_parser.add_argument(
        "--no-promote",
        action="store_true",
        help="Only generate and validate drafts; do not promote them into golden tests.",
    )

    validate_draft_tests_parser = subparsers.add_parser(
        "validate-coverage-test-drafts",
        help="Validate existing coverage test drafts for a document.",
    )
    validate_draft_tests_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to validate.",
    )
    validate_draft_tests_parser.add_argument(
        "--mode",
        choices=["trace", "answer", "hybrid"],
        default="trace",
        help="Validation mode. trace checks source/fact/wiki coverage; answer also runs generated answers.",
    )

    readiness_parser = subparsers.add_parser(
        "assess-coverage-test-draft-readiness",
        help="Assess whether coverage test drafts are suitable for validation or promotion.",
    )
    readiness_parser.add_argument(
        "--doc-id",
        help="Document ID to assess. Omit to assess all active documents with draft files.",
    )

    promote_draft_tests_parser = subparsers.add_parser(
        "promote-coverage-test-drafts",
        help="Promote validated coverage test drafts into the document golden suite.",
    )
    promote_draft_tests_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to promote.",
    )
    promote_draft_tests_parser.add_argument(
        "--allow-unvalidated",
        action="store_true",
        help="Allow promotion without a validated draft file.",
    )

    run_coverage_tests_parser = subparsers.add_parser(
        "run-coverage-promoted-tests",
        help="Run only generated golden tests promoted from coverage gaps.",
    )
    run_coverage_tests_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to test.",
    )
    run_coverage_tests_parser.add_argument(
        "--pytest",
        action="store_true",
        help="Run through pytest marker selection instead of the direct JSON runner.",
    )
    run_coverage_tests_parser.add_argument(
        "--mode",
        choices=["trace", "context", "rich", "hybrid"],
        default="trace",
        help="Validation mode for the direct JSON runner.",
    )

    graph_parser = subparsers.add_parser(
        "build-graph",
        help="Build graph edges for a document.",
    )
    graph_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build graph for.",
    )

    subparsers.add_parser(
        "graph-report",
        help="Print a graph health report across all query types.",
    )

    subparsers.add_parser(
        "run-query-repair-smoke",
        help="Run a small query repair regression suite and record an eval run.",
    )

    user_query_retrieval_parser = subparsers.add_parser(
        "run-user-query-retrieval-eval",
        help="Run real user-style query retrieval evaluation and record an eval run.",
    )
    user_query_retrieval_parser.add_argument(
        "--case-file",
        type=Path,
        default=None,
        help="JSON file containing real user-style retrieval cases.",
    )
    user_query_retrieval_parser.add_argument(
        "--suite-id",
        default="regression:user_query_retrieval",
        help="Eval suite ID to record.",
    )
    user_query_retrieval_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Retrieval hit limit per query.",
    )
    user_query_retrieval_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for JSON and Markdown reports.",
    )

    corpus_cases_parser = subparsers.add_parser(
        "generate-corpus-eval-cases",
        help="Generate source-unit driven corpus retrieval evaluation cases.",
    )
    corpus_cases_parser.add_argument(
        "--doc-id",
        action="append",
        default=None,
        help="Document ID to sample from. Repeat to include multiple docs. Defaults to all active documents.",
    )
    corpus_cases_parser.add_argument(
        "--limit-per-type",
        type=int,
        default=20,
        help="Maximum generated cases per corpus case type.",
    )
    corpus_cases_parser.add_argument(
        "--case-type",
        action="append",
        default=None,
        help="Case type to generate: definition, parameter, or process_activity. Repeat for multiple types.",
    )
    corpus_cases_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for JSON and Markdown reports.",
    )

    corpus_eval_parser = subparsers.add_parser(
        "run-corpus-retrieval-eval",
        help="Run source-unit driven corpus retrieval evaluation and record an eval run.",
    )
    corpus_eval_parser.add_argument(
        "--case-file",
        type=Path,
        default=None,
        help="JSON file containing corpus retrieval cases. Omit to generate cases first.",
    )
    corpus_eval_parser.add_argument(
        "--suite-id",
        default="regression:corpus_retrieval",
        help="Eval suite ID to record.",
    )
    corpus_eval_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Retrieval hit limit per query.",
    )
    corpus_eval_parser.add_argument(
        "--case-limit",
        type=int,
        default=None,
        help="Maximum cases to run after loading or generation.",
    )
    corpus_eval_parser.add_argument(
        "--doc-id",
        action="append",
        default=None,
        help="Document ID to generate cases from when --case-file is omitted. Repeat for multiple docs.",
    )
    corpus_eval_parser.add_argument(
        "--generation-limit-per-type",
        type=int,
        default=20,
        help="Maximum generated cases per corpus case type when --case-file is omitted.",
    )
    corpus_eval_parser.add_argument(
        "--case-type",
        action="append",
        default=None,
        help="Case type to generate when --case-file is omitted: definition, parameter, or process_activity.",
    )
    corpus_eval_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for JSON and Markdown reports.",
    )

    diagnostics_parser = subparsers.add_parser(
        "document-diagnostics",
        help="Build diagnostics and coverage summary for a document.",
    )
    diagnostics_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to inspect.",
    )

    uncovered_priority_parser = subparsers.add_parser(
        "uncovered-priority-report",
        help="Build an all-docs priority report for uncovered coverage units.",
    )
    uncovered_priority_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for the generated JSON and Markdown reports.",
    )
    uncovered_priority_parser.add_argument(
        "--sample-limit",
        type=int,
        default=8,
        help="Maximum sampled issues per document and coverage status.",
    )
    uncovered_priority_parser.add_argument(
        "--no-rebuild-missing-coverage",
        action="store_true",
        help="Do not rebuild missing per-document coverage artifacts.",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Search evidence, facts, and wiki pages.",
    )
    search_parser.add_argument(
        "--query",
        required=True,
        help="Search query.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results.",
    )

    query_parser = subparsers.add_parser(
        "query-context",
        help="Build structured retrieval context for agents.",
    )
    query_parser.add_argument(
        "--query",
        required=True,
        help="Query text.",
    )
    query_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of search hits to expand.",
    )

    answer_parser = subparsers.add_parser(
        "answer-query",
        help="Build an explainable answer from structured query context.",
    )
    answer_parser.add_argument(
        "--query",
        required=True,
        help="Question or query text.",
    )
    answer_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of search hits to expand.",
    )

    agent_parser = subparsers.add_parser(
        "agent-query",
        help="Run a lightweight multi-hop agent query over the knowledge base.",
    )
    agent_parser.add_argument(
        "--query",
        required=True,
        help="Question or query text.",
    )
    agent_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of search hits per tool call.",
    )

    build_document_parser = subparsers.add_parser(
        "build-document",
        help="Run the full pipeline for a registered document.",
    )
    build_document_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build end-to-end.",
    )

    build_file_parser = subparsers.add_parser(
        "build-file",
        help="Register a source file and run the full pipeline.",
    )
    build_file_parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the source file.",
    )

    convert_file_parser = subparsers.add_parser(
        "convert-file",
        help="Register a source file and only run parse/convert.",
    )
    convert_file_parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the source file.",
    )

    build_document_test_parser = subparsers.add_parser(
        "build-document-and-test",
        help="Run the full pipeline and golden tests for a registered document.",
    )
    build_document_test_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to build and test end-to-end.",
    )

    build_file_test_parser = subparsers.add_parser(
        "build-file-and-test",
        help="Register a source file, run the full pipeline, and execute golden tests.",
    )
    build_file_test_parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the source file.",
    )

    build_batch_parser = subparsers.add_parser(
        "build-batch",
        help="Run the full pipeline for multiple registered documents.",
    )
    build_batch_parser.add_argument(
        "--doc-ids",
        nargs="+",
        required=True,
        help="One or more document IDs.",
    )

    serve_parser = subparsers.add_parser(
        "serve-api",
        help="Start the local HTTP API server.",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind.",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind.",
    )

    mcp_parser = subparsers.add_parser(
        "serve-mcp",
        help="Start the stdio MCP server.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    schema_path = Path(__file__).with_name("schema.sql")

    if args.command == "init":
        paths = initialize_workspace(args.root, schema_path)
        print(f"initialized workspace: {paths.root}")
        print(f"database: {paths.db_file}")
        return

    if args.command == "status":
        status = workspace_status(args.root)
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return

    if args.command == "register":
        result = register_document(args.root, args.file)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "job_id": result.job_id,
                    "deduplicated": result.deduplicated,
                    "stored_path": str(result.stored_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "reset-workspace":
        result = reset_workspace_data(args.root, keep_raw=not args.drop_raw)
        print(
            json.dumps(
                {
                    "keep_raw": result.keep_raw,
                    "deleted_rows": result.deleted_rows,
                    "deleted_files": result.deleted_files,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "parse-document":
        result = parse_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "page_count": result.page_count,
                    "block_count": result.block_count,
                    "normalized_path": str(result.normalized_path),
                    "parser_engine": result.parser_engine,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "convert-document":
        result = parse_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "page_count": result.page_count,
                    "block_count": result.block_count,
                    "normalized_path": str(result.normalized_path),
                    "parser_engine": result.parser_engine,
                    "mode": "convert_only",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "run-jobs":
        results = run_parse_jobs(args.root, limit=args.limit)
        print(json.dumps(summarize_job_results(results), indent=2, ensure_ascii=False))
        return

    if args.command == "quality-document":
        result = assess_document_quality(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "overall_score": result.overall_score,
                    "high_risk_page_count": result.high_risk_page_count,
                    "review_required_count": result.review_required_count,
                    "blocked_count": result.blocked_count,
                    "report_path": str(result.report_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "quality-batch":
        results = assess_pending_quality(args.root, limit=args.limit)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if args.command == "build-evidence":
        result = build_evidence_for_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "evidence_count": result.evidence_count,
                    "skipped_block_count": result.skipped_block_count,
                    "export_path": str(result.export_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "build-facts":
        result = build_facts_for_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "fact_count": result.fact_count,
                    "fact_types": result.fact_types,
                    "export_path": str(result.export_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "build-entities":
        result = build_entities_for_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "entity_count": result.entity_count,
                    "entity_types": result.entity_types,
                    "export_path": str(result.export_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "build-wiki":
        result = build_wiki_for_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "page_count": result.page_count,
                    "export_paths": [str(path) for path in result.export_paths],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "build-coverage":
        result = build_coverage_for_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "source_unit_count": result.source_unit_count,
                    "text_coverage_rate": result.text_coverage_rate,
                    "semantic_coverage_rate": result.semantic_coverage_rate,
                    "object_coverage_rate": result.object_coverage_rate,
                    "test_coverage_rate": result.test_coverage_rate,
                    "uncovered_counts": result.uncovered_counts,
                    "summary_path": str(result.summary_path),
                    "report_path": str(result.report_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "build-test-gaps":
        result = build_test_gap_candidates_for_document(
            args.root,
            args.doc_id,
            limit=args.limit,
            rebuild=args.rebuild,
        )
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "candidate_count": result.candidate_count,
                    "candidates_path": str(result.candidates_path),
                    "report_path": str(result.report_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "generate-coverage-test-drafts":
        result = generate_coverage_test_drafts_for_document(
            args.root,
            args.doc_id,
            limit=args.limit,
            rebuild_coverage=args.rebuild_coverage,
            validate=args.validate,
        )
        print(
            json.dumps(
                {
                    "doc_id": result["doc_id"],
                    "draft_case_count": result["draft_case_count"],
                    "validated": result["validated"],
                    "json_path": result["json_path"],
                    "report_path": result["report_path"],
                    "coverage_candidates_path": result["coverage_candidates_path"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "close-coverage-test-gaps":
        result = close_coverage_test_gaps(
            args.root,
            doc_ids=args.doc_id,
            limit_per_doc=args.limit_per_doc,
            validation_mode=args.mode,
            rebuild_coverage=args.rebuild_coverage,
            promote=not args.no_promote,
        )
        print(
            json.dumps(
                {
                    "document_count": result["document_count"],
                    "limit_per_doc": result["limit_per_doc"],
                    "validation_mode": result["validation_mode"],
                    "promote": result["promote"],
                    "totals": result["totals"],
                    "success": result["success"],
                    "json_path": result["json_path"],
                    "uncovered_priority_report": result["uncovered_priority_report"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "validate-coverage-test-drafts":
        result = validate_coverage_test_drafts_for_document(args.root, args.doc_id, mode=args.mode)
        print(
            json.dumps(
                {
                    "doc_id": result["doc_id"],
                    "draft_case_count": result["draft_case_count"],
                    "validation_mode": result["validation_mode"],
                    "passed_count": result["passed_count"],
                    "failed_count": result["failed_count"],
                    "json_path": result["json_path"],
                    "report_path": result["report_path"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "assess-coverage-test-draft-readiness":
        if args.doc_id:
            result = assess_coverage_test_draft_readiness_for_document(args.root, args.doc_id)
        else:
            result = assess_all_coverage_test_draft_readiness(args.root)
        print(
            json.dumps(
                {
                    "status_counts": result["status_counts"],
                    "flag_counts": result["flag_counts"],
                    "json_path": result["json_path"],
                    "report_path": result["report_path"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "promote-coverage-test-drafts":
        result = promote_coverage_test_drafts_for_document(
            args.root,
            args.doc_id,
            require_validated=not args.allow_unvalidated,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "run-coverage-promoted-tests":
        if args.pytest:
            result = run_coverage_promoted_pytest_for_document(args.root, args.doc_id)
        else:
            result = run_coverage_promoted_tests_for_document(
                args.root,
                args.doc_id,
                validation_mode=args.mode,
            )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "build-graph":
        result = build_graph_for_document(args.root, args.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "edge_count": result.edge_count,
                    "edge_types": result.edge_types,
                    "export_path": str(result.export_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "graph-report":
        db_path = Path(args.root) / "db" / "knowledge.db"
        report = build_graph_health_report(db_path)
        print(format_graph_health_report(report))
        return

    if args.command == "run-query-repair-smoke":
        result = run_query_repair_smoke_eval(args.root)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "run-user-query-retrieval-eval":
        result = run_user_query_retrieval_eval(
            args.root,
            case_file=args.case_file,
            suite_id=args.suite_id,
            limit=args.limit,
            output_dir=args.output_dir,
        )
        print(
            json.dumps(
                {
                    "eval_run_id": result.eval_run_id,
                    "suite_id": result.suite_id,
                    "case_count": result.case_count,
                    "passed": result.passed,
                    "failed": result.failed,
                    "success": result.success,
                    "json_path": str(result.json_path),
                    "report_path": str(result.report_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "generate-corpus-eval-cases":
        result = generate_corpus_eval_cases(
            args.root,
            doc_ids=args.doc_id,
            limit_per_type=args.limit_per_type,
            output_dir=args.output_dir,
            case_types=args.case_type,
        )
        print(
            json.dumps(
                {
                    "case_count": result.case_count,
                    "summary": result.summary,
                    "json_path": str(result.json_path),
                    "report_path": str(result.report_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "run-corpus-retrieval-eval":
        result = run_corpus_retrieval_eval(
            args.root,
            case_file=args.case_file,
            suite_id=args.suite_id,
            limit=args.limit,
            output_dir=args.output_dir,
            doc_ids=args.doc_id,
            generation_limit_per_type=args.generation_limit_per_type,
            case_limit=args.case_limit,
            case_types=args.case_type,
        )
        print(
            json.dumps(
                {
                    "eval_run_id": result.eval_run_id,
                    "suite_id": result.suite_id,
                    "case_count": result.case_count,
                    "passed": result.passed,
                    "failed": result.failed,
                    "success": result.success,
                    "case_file": str(result.case_file),
                    "json_path": str(result.json_path),
                    "report_path": str(result.report_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "document-diagnostics":
        result = build_document_diagnostics(args.root, args.doc_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "uncovered-priority-report":
        result = build_all_docs_uncovered_priority_report(
            args.root,
            output_dir=args.output_dir,
            sample_limit_per_doc_status=args.sample_limit,
            rebuild_missing_coverage=not args.no_rebuild_missing_coverage,
        )
        print(
            json.dumps(
                {
                    "document_count": result.document_count,
                    "issue_count": result.issue_count,
                    "json_path": str(result.json_path),
                    "report_path": str(result.report_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "search":
        results = search_knowledge_base(args.root, args.query, limit=args.limit)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if args.command == "query-context":
        result = build_query_context(args.root, args.query, limit=args.limit)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "answer-query":
        result = answer_query(args.root, args.query, limit=args.limit)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "agent-query":
        result = run_agent_query(args.root, args.query, limit=args.limit)
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return

    if args.command == "build-document":
        result = run_document_pipeline(args.root, args.doc_id)
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return

    if args.command == "build-file":
        result = run_file_pipeline(args.root, args.file)
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return

    if args.command == "convert-file":
        register_result = register_document(args.root, args.file)
        result = parse_document(args.root, register_result.doc_id)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "registered": True,
                    "deduplicated": register_result.deduplicated,
                    "page_count": result.page_count,
                    "block_count": result.block_count,
                    "normalized_path": str(result.normalized_path),
                    "parser_engine": result.parser_engine,
                    "mode": "convert_only",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "build-document-and-test":
        result = run_document_pipeline_and_tests(args.root, args.doc_id)
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return

    if args.command == "build-file-and-test":
        result = run_file_pipeline_and_tests(args.root, args.file)
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return

    if args.command == "build-batch":
        results = run_batch_pipeline(args.root, args.doc_ids)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if args.command == "serve-api":
        serve_api(args.root, host=args.host, port=args.port)
        return

    if args.command == "serve-mcp":
        run_mcp_stdio(args.root)
        return

    parser.error(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
