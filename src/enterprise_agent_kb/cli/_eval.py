"""Evaluation commands: graph-report, run-query-repair-smoke, run-user-query-retrieval-eval, generate-corpus-eval-cases, run-corpus-retrieval-eval, generate-golden-candidates.

Extracted from `cli._impl` to isolate the per-domain argparse
subparser definitions and the corresponding main() handler branches.
The orchestrator (`cli._impl.build_parser` and `cli._impl.main`)
re-exports the public surface.
"""
from __future__ import annotations


import json
from pathlib import Path

from ..corpus_eval import generate_corpus_eval_cases, run_corpus_retrieval_eval
from ..generated_tests import run_query_repair_smoke_eval
from ..golden_generation import generate_golden_candidates
from ..graph_report import build_graph_health_report, format_graph_health_report
from ..user_query_retrieval_eval import run_user_query_retrieval_eval


def register_subcommand(subparsers) -> None:
    """Register the subparser(s) for this command family."""
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
        help="Case type to generate: definition, parameter, process_activity, or requirement. Repeat for multiple types.",
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
        "--case-offset",
        type=int,
        default=0,
        help="Zero-based case offset for batched corpus evaluation.",
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
        help="Case type to generate when --case-file is omitted: definition, parameter, process_activity, or requirement.",
    )
    corpus_eval_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for JSON and Markdown reports.",
    )
    corpus_eval_parser.add_argument(
        "--progress",
        action="store_true",
        help="Write one JSON progress event to stderr after each evaluated corpus case.",
    )
    golden_candidates_parser = subparsers.add_parser(
        "generate-golden-candidates",
        help="Generate unified golden candidate drafts with tier/readiness report. Dry-run only; does not activate golden cases.",
    )
    golden_candidates_parser.add_argument(
        "--origin",
        action="append",
        default=None,
        choices=("source_unit", "eval_failure"),
        help="Candidate origin to include. May be repeated. Defaults to source_unit.",
    )
    golden_candidates_parser.add_argument(
        "--doc-id",
        action="append",
        default=None,
        help="Limit source_unit origin to one or more document IDs.",
    )
    golden_candidates_parser.add_argument(
        "--eval-run-id",
        default=None,
        help="Eval run ID required when --origin eval_failure is used.",
    )
    golden_candidates_parser.add_argument(
        "--limit-per-type",
        type=int,
        default=20,
        help="Maximum source_unit candidates per case type.",
    )
    golden_candidates_parser.add_argument(
        "--case-type",
        action="append",
        default=None,
        help="Limit source_unit case types. May be repeated.",
    )
    golden_candidates_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for JSON and Markdown reports.",
    )





    # --- Phase 1 evaluation suite (eval run-now) ---
    p_eval = subparsers.add_parser(
        "eval",
        help="Run the Phase 1 evaluation suite (sample_qa bank).",
    )
    eval_subs = p_eval.add_subparsers(dest="eval_command", required=True)
    rn = eval_subs.add_parser(
        "run-now",
        help="Run the golden or full evaluation suite and print pass_rate.",
    )
    rn.add_argument("--suite", choices=["golden", "full"], default="golden",
                    help="golden = 30 questions spot-check set; full = all questions")
    rn.add_argument("--version", default="v1", help="expected_points version")
    rn.add_argument("--max-questions", type=int, default=None,
                    help="Cap number of questions (for quick smoke tests)")
    rn.add_argument("--root", type=Path, default=Path("knowledge_base"),
                    help="Workspace root (default: knowledge_base)")
    # --- Sprint 3 WP8: sharded golden baseline ---
    sr = eval_subs.add_parser(
        "shard-run",
        help="Run one shard of the golden suite for parallel/large baseline runs.",
    )
    sr.add_argument("--suite", choices=["golden", "full"], default="golden",
                    help="golden = capped question set; full = all questions")
    sr.add_argument("--version", default="v1", help="expected_points version")
    sr.add_argument("--shard-index", type=int, required=True,
                    help="Zero-based shard index to run (0..shard-count-1)")
    sr.add_argument("--shard-count", type=int, required=True,
                    help="Total number of shards to split the question set into")
    sr.add_argument("--output", type=Path, required=True,
                    help="Output JSON path for this shard's full result (per-question included)")
    sr.add_argument("--root", type=Path, default=Path("knowledge_base"),
                    help="Workspace root (default: knowledge_base)")
    mr = eval_subs.add_parser(
        "merge-shards",
        help="Merge multiple shard-run JSON files into one aggregated result.",
    )
    mr.add_argument("--input", action="append", required=True,
                    help="Shard JSON path. Repeat for each shard file.")
    mr.add_argument("--output", type=Path, required=True,
                    help="Output JSON path for the merged result.")


def handle_command(args, schema_path) -> bool:
    """Handle the main() branch for this command family."""

    # --- eval run-now ---
    if getattr(args, "command", None) == "eval" and getattr(args, "eval_command", None) == "run-now":
        from enterprise_agent_kb.evaluation import run_suite
        from pathlib import Path
        try:
            result = run_suite(
                suite=args.suite,
                version=args.version,
                workspace_root=args.root,
                max_questions=args.max_questions,
            )
        except FileNotFoundError as e:
            print(f"ERROR: {e}")
            print("Run python tools/build_expected_points.py and "
                  "python tools/build_sample_qa.py first.")
            return True
        out = {
            "suite": result.suite,
            "total": result.total,
            "passed": result.passed,
            "pass_rate": result.pass_rate,
            "avg_coverage": result.avg_coverage,
            "multi_prompt_stability": result.multi_prompt_stability,
            "by_doc": result.by_doc,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        if 0.65 <= result.pass_rate <= 0.85 and result.multi_prompt_stability > 0.8:
            print(f"\nPhase 1 sign-off criteria met: pass_rate={result.pass_rate:.2f} "
                  f"in [0.65, 0.85], stability={result.multi_prompt_stability:.2f} > 0.8")
        elif result.pass_rate < 0.65:
            print(f"\nFAIL: pass_rate={result.pass_rate:.2f} < 0.65")
        elif result.pass_rate > 0.85:
            print(f"\nFAIL: pass_rate={result.pass_rate:.2f} > 0.85")
        return True

    # --- eval shard-run ---
    if getattr(args, "command", None) == "eval" and getattr(args, "eval_command", None) == "shard-run":
        from enterprise_agent_kb.evaluation import run_suite
        try:
            result = run_suite(
                suite=args.suite,
                version=args.version,
                workspace_root=args.root,
                shard_index=args.shard_index,
                shard_count=args.shard_count,
            )
        except FileNotFoundError as e:
            print(f"ERROR: {e}")
            return True
        payload = result.to_full_dict()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "shard_index": args.shard_index, "shard_count": args.shard_count,
            "total": result.total, "passed": result.passed,
            "pass_rate": result.pass_rate, "output": str(args.output),
        }, ensure_ascii=False, indent=2))
        return True

    # --- eval merge-shards ---
    if getattr(args, "command", None) == "eval" and getattr(args, "eval_command", None) == "merge-shards":
        from enterprise_agent_kb.evaluation.evaluator import shard_result_from_dict, merge_shard_results
        shards = []
        for path in args.input:
            shards.append(shard_result_from_dict(json.loads(Path(path).read_text(encoding="utf-8"))))
        merged = merge_shard_results(shards)
        payload = merged.to_full_dict()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "total": merged.total, "passed": merged.passed,
            "pass_rate": merged.pass_rate, "avg_coverage": round(merged.avg_coverage, 3),
            "by_doc": merged.by_doc, "safety_metrics": merged.safety_metrics,
            "output": str(args.output),
        }, ensure_ascii=False, indent=2))
        return True

    # --- existing eval handlers (graph-report, run-corpus-retrieval-eval, etc.) ---
    if args.command == "graph-report":
        db_path = Path(args.root) / "db" / "knowledge.db"
        report = build_graph_health_report(db_path)
        print(format_graph_health_report(report))
        return True
    if args.command == "run-query-repair-smoke":
        result = run_query_repair_smoke_eval(args.root)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return True
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
        return True
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
        return True
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
            case_offset=args.case_offset,
            case_types=args.case_type,
            progress=args.progress,
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
        return True
    if args.command == "generate-golden-candidates":
        result = generate_golden_candidates(
            args.root,
            origins=args.origin,
            doc_ids=args.doc_id,
            eval_run_id=args.eval_run_id,
            limit_per_type=args.limit_per_type,
            case_types=args.case_type,
            output_dir=args.output_dir,
        )
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return True

    return False
