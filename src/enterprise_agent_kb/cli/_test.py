"""Ad-hoc test commands: build-quality, check-quality, auto-close-coverage, revalidate-golden.

Extracted from `cli._impl` to isolate the per-domain argparse
subparser definitions and the corresponding main() handler branches.
The orchestrator (`cli._impl.build_parser` and `cli._impl.main`)
re-exports the public surface.
"""
from __future__ import annotations

import json


def register_subcommand(subparsers) -> None:
    """Register the subparser(s) for this command family."""
    build_quality_parser = subparsers.add_parser(
        "build-quality",
        help="Run full quality pipeline with auto-coverage closure.",
    )
    build_quality_parser.add_argument("--doc-id", required=True)
    build_quality_parser.add_argument("--min-test-coverage", type=float, default=0.3)

    check_quality_parser = subparsers.add_parser(
        "check-quality",
        help="Compute quality gate scores without running pipeline.",
    )
    check_quality_parser.add_argument("--doc-id", required=True)

    auto_close_parser = subparsers.add_parser(
        "auto-close-coverage",
        help="Auto-activate golden cases for uncovered units.",
    )
    auto_close_parser.add_argument("--doc-id", required=True)
    auto_close_parser.add_argument("--max-candidates", type=int, default=50)

    revalidate_parser = subparsers.add_parser(
        "revalidate-golden",
        help="Detect and revalidate stale golden cases.",
    )
    revalidate_parser.add_argument("--doc-id", required=True)


def handle_command(args, schema_path) -> bool:
    """Handle the main() branch for this command family.

    Returns True if the command was handled, False if it does not belong
    to this submodule. ``_impl.main`` walks each family in order and
    stops at the first True.
    """
    if args.command == "build-quality":
        from ..pipeline import run_full_quality_pipeline
        result = run_full_quality_pipeline(
            args.root,
            args.doc_id,
            min_test_coverage=args.min_test_coverage,
        )
        print(json.dumps({
            "doc_id": result.doc_id,
            "acceptance_status": result.acceptance_status,
            "overall_score": result.overall_score,
            "parse_quality_score": result.parse_quality_score,
            "knowledge_completeness_score": result.knowledge_completeness_score,
            "test_coverage_score": result.test_coverage_score,
            "contract_compliance_score": result.contract_compliance_score,
            "gate_status": result.gate_status,
            "coverage_iterations": result.coverage_iterations,
            "golden_cases_activated": result.golden_cases_activated,
            "stale_cases_removed": result.stale_cases_removed,
        }, indent=2, ensure_ascii=False))
        return True

    if args.command == "check-quality":
        from ..quality_gate import compute_quality_gate
        result = compute_quality_gate(args.root, args.doc_id)
        print(json.dumps({
            "doc_id": result.doc_id,
            "overall_score": result.overall_score,
            "parse_quality_score": result.parse_quality_score,
            "knowledge_completeness_score": result.knowledge_completeness_score,
            "test_coverage_score": result.test_coverage_score,
            "contract_compliance_score": result.contract_compliance_score,
            "gate_status": result.gate_status,
            "report_path": str(result.report_path),
        }, indent=2, ensure_ascii=False))
        return True

    if args.command == "auto-close-coverage":
        from ..generated_tests import auto_activate_golden_cases
        result = auto_activate_golden_cases(
            args.root,
            args.doc_id,
            max_candidates=args.max_candidates,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return True

    if args.command == "revalidate-golden":
        from ..generated_tests import revalidate_stale_golden_cases
        result = revalidate_stale_golden_cases(args.root, args.doc_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return True

    return False
