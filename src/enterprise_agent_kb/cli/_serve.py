"""Server & query commands: diagnostics, parse-risk-actions, parse-risk-repair-review, validate-document-ingestion, uncovered-priority-report, search, query-context, answer-query, agent-query, serve-api, serve-mcp.

Extracted from `cli._impl` to isolate the per-domain argparse
subparser definitions and the corresponding main() handler branches.
The orchestrator (`cli._impl.build_parser` and `cli._impl.main`)
re-exports the public surface.
"""
from __future__ import annotations


import argparse
import json
import sys
from pathlib import Path

from ..agent_tools import run_agent_query
from ..answer_api import answer_query
from ..api_server import serve_api
from ..coverage_diagnostics import build_all_docs_uncovered_priority_report
from ..doc_diagnostics import build_document_diagnostics
from ..ingest import register_document
from ..ingestion_acceptance import validate_document_ingestion
from ..mcp_server import run_mcp_stdio
from ..parse import parse_document
from ..parse_risk_actions import generate_parse_risk_action_plan, review_parse_risk_repair_tasks
from ..pipeline import (
    PipelineEvent,
    run_batch_pipeline,
    run_document_pipeline,
    run_document_pipeline_and_tests,
    run_document_pipeline_and_tests_with_progress,
    run_document_pipeline_with_progress,
    run_file_pipeline,
    run_file_pipeline_and_tests,
    run_file_pipeline_and_tests_with_progress,
    run_file_pipeline_with_progress,
)
from ..query_api import build_query_context
from ..retrieval import search_knowledge_base


def _add_pipeline_progress_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Write one JSON progress event to stderr before and after each pipeline stage.",
    )


def _pipeline_progress_printer(event: PipelineEvent) -> None:
    print(
        json.dumps(
            {
                "event": "pipeline_stage",
                "doc_id": event.doc_id,
                "stage": event.stage,
                "status": event.status,
                "progress": event.progress,
                "elapsed_seconds": event.elapsed_seconds,
                "detail": event.detail,
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
        flush=True,
    )


def register_subcommand(subparsers) -> None:
    """Register the subparser(s) for this command family."""
    diagnostics_parser = subparsers.add_parser(
        "document-diagnostics",
        help="Build diagnostics and coverage summary for a document.",
    )
    diagnostics_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to inspect.",
    )
    parse_risk_actions_parser = subparsers.add_parser(
        "parse-risk-actions",
        help="Generate a dry-run repair/golden-candidate action plan from parse risk attribution.",
    )
    parse_risk_actions_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to inspect.",
    )
    parse_risk_actions_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for JSON and Markdown action plan reports.",
    )
    parse_risk_actions_parser.add_argument(
        "--persist-repair-tasks",
        action="store_true",
        help="Persist non-review parse-risk repair proposals into repair_tasks. Default is dry-run only.",
    )
    parse_risk_review_parser = subparsers.add_parser(
        "parse-risk-repair-review",
        help="Review persisted parse-risk repair tasks against current diagnostics without changing task status.",
    )
    parse_risk_review_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to review.",
    )
    parse_risk_review_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for JSON and Markdown repair review reports.",
    )
    ingestion_acceptance_parser = subparsers.add_parser(
        "validate-document-ingestion",
        help="Validate whether a built document passes generic ingestion acceptance checks.",
    )
    ingestion_acceptance_parser.add_argument(
        "--doc-id",
        required=True,
        help="Document ID to validate.",
    )
    ingestion_acceptance_parser.add_argument(
        "--min-text-coverage",
        type=float,
        default=0.5,
        help="Minimum text coverage rate required for pass.",
    )
    ingestion_acceptance_parser.add_argument(
        "--min-semantic-coverage",
        type=float,
        default=0.2,
        help="Minimum semantic coverage rate required for pass.",
    )
    ingestion_acceptance_parser.add_argument(
        "--min-answerability",
        type=float,
        default=0.2,
        help="Minimum answerability score before warning.",
    )
    ingestion_acceptance_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for JSON and Markdown acceptance reports.",
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
    _add_pipeline_progress_argument(build_document_parser)
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
    _add_pipeline_progress_argument(build_file_parser)
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
    _add_pipeline_progress_argument(build_document_test_parser)
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
    _add_pipeline_progress_argument(build_file_test_parser)
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




def handle_command(args, schema_path) -> bool:
    """Handle the main() branch for this command family."""
    if args.command == "document-diagnostics":
        result = build_document_diagnostics(args.root, args.doc_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return True
    if args.command == "parse-risk-actions":
        result = generate_parse_risk_action_plan(
            args.root,
            args.doc_id,
            output_dir=args.output_dir,
            persist_repair_tasks=args.persist_repair_tasks,
        )
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return True
    if args.command == "parse-risk-repair-review":
        result = review_parse_risk_repair_tasks(
            args.root,
            args.doc_id,
            output_dir=args.output_dir,
        )
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return True
    if args.command == "validate-document-ingestion":
        result = validate_document_ingestion(
            args.root,
            args.doc_id,
            min_text_coverage=args.min_text_coverage,
            min_semantic_coverage=args.min_semantic_coverage,
            min_answerability=args.min_answerability,
            output_dir=args.output_dir,
        )
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return True
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
        return True
    if args.command == "search":
        results = search_knowledge_base(args.root, args.query, limit=args.limit)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return True
    if args.command == "query-context":
        result = build_query_context(args.root, args.query, limit=args.limit)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return True
    if args.command == "answer-query":
        result = answer_query(args.root, args.query, limit=args.limit)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return True
    if args.command == "agent-query":
        result = run_agent_query(args.root, args.query, limit=args.limit)
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return True
    if args.command == "build-document":
        result = (
            run_document_pipeline_with_progress(
                args.root,
                args.doc_id,
                progress_callback=_pipeline_progress_printer,
            )
            if args.progress
            else run_document_pipeline(args.root, args.doc_id)
        )
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return True
    if args.command == "build-file":
        result = (
            run_file_pipeline_with_progress(
                args.root,
                args.file,
                progress_callback=_pipeline_progress_printer,
            )
            if args.progress
            else run_file_pipeline(args.root, args.file)
        )
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return True
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
        return True
    if args.command == "build-document-and-test":
        result = (
            run_document_pipeline_and_tests_with_progress(
                args.root,
                args.doc_id,
                progress_callback=_pipeline_progress_printer,
            )
            if args.progress
            else run_document_pipeline_and_tests(args.root, args.doc_id)
        )
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return True
    if args.command == "build-file-and-test":
        result = (
            run_file_pipeline_and_tests_with_progress(
                args.root,
                args.file,
                progress_callback=_pipeline_progress_printer,
            )
            if args.progress
            else run_file_pipeline_and_tests(args.root, args.file)
        )
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
        return True
    if args.command == "build-batch":
        results = run_batch_pipeline(args.root, args.doc_ids)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return True
    if args.command == "serve-api":
        serve_api(args.root, host=args.host, port=args.port)
        return True
    if args.command == "serve-mcp":
        run_mcp_stdio(args.root)
        return True

    return False
