"""Build pipeline commands: parse, convert, jobs, quality, evidence, facts, entities, wiki, coverage, test-gaps, drafts, graph, build-document/file/batch.

Extracted from `cli._impl` to isolate the per-domain argparse
subparser definitions and the corresponding main() handler branches.
The orchestrator (`cli._impl.build_parser` and `cli._impl.main`)
re-exports the public surface.
"""
from __future__ import annotations


import json
from pathlib import Path

from ..coverage import build_coverage_for_document, build_test_gap_candidates_for_document
from ..entities import build_entities_for_document
from ..evidence import build_evidence_for_document
from ..facts import build_facts_for_document
from ..generated_tests import (
    assess_all_coverage_test_draft_readiness,
    assess_coverage_test_draft_readiness_for_document,
    close_coverage_test_gaps,
    generate_coverage_test_drafts_for_document,
    promote_coverage_test_drafts_for_document,
    run_coverage_promoted_pytest_for_document,
    run_coverage_promoted_tests_for_document,
    validate_coverage_test_drafts_for_document,
)
from ..graph import build_graph_for_document
from ..governance import assess_pending_quality
from ..jobs import run_parse_jobs, summarize_job_results
from ..parse import parse_document
from ..quality import assess_document_quality
from ..wiki_compiler import build_wiki_for_document


def register_subcommand(subparsers) -> None:
    """Register the subparser(s) for this command family."""
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




def handle_command(args, schema_path) -> bool:
    """Handle the main() branch for this command family."""
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
        return True
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
        return True
    if args.command == "run-jobs":
        results = run_parse_jobs(args.root, limit=args.limit)
        print(json.dumps(summarize_job_results(results), indent=2, ensure_ascii=False))
        return True
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
        return True
    if args.command == "quality-batch":
        results = assess_pending_quality(args.root, limit=args.limit)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return True
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
        return True
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
        return True
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
        return True
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
        return True
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
        return True
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
        return True
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
        return True
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
        return True
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
        return True
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
        return True
    if args.command == "promote-coverage-test-drafts":
        result = promote_coverage_test_drafts_for_document(
            args.root,
            args.doc_id,
            require_validated=not args.allow_unvalidated,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return True
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
        return True
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
        return True

    return False
