"""Run the Phase 1 evaluation suite and assert minimum pass rate.

This is the CI entry point for the evaluator.  It exits 0 if the pass
rate meets the configured minimum, non-zero otherwise.

Usage:
    # Token-overlap mode (default, fast)
    python scripts/run_eval_suite.py

    # LLM mode (more accurate, requires ANTHROPIC_BASE_URL)
    EVAL_USE_LLM=1 python scripts/run_eval_suite.py

    # Custom question count
    python scripts/run_eval_suite.py --max-questions 50

Environment variables:
    EVAL_MIN_TOKEN_PASS  Minimum token-overlap pass rate (default 0.30)
    EVAL_MIN_LLM_PASS     Minimum LLM pass rate (default 0.10)
    EVAL_USE_LLM          "1" to use LLM scoring
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", default="v1",
        help="expected_points version (default v1)",
    )
    parser.add_argument(
        "--suite", default="golden",
        help="suite name (default golden)",
    )
    parser.add_argument(
        "--max-questions", type=int, default=5,
        help="limit number of questions (default 5 for CI speed; "
             "use 30+ for full eval)",
    )
    parser.add_argument(
        "--use-llm", action="store_true",
        help="use LLM scoring instead of token-overlap",
    )
    parser.add_argument(
        "--min-token-pass", type=float,
        default=float(os.environ.get("EVAL_MIN_TOKEN_PASS", "0.30")),
        help="minimum token-overlap pass rate (default 0.30 or $EVAL_MIN_TOKEN_PASS)",
    )
    parser.add_argument(
        "--min-llm-pass", type=float,
        default=float(os.environ.get("EVAL_MIN_LLM_PASS", "0.10")),
        help="minimum LLM pass rate (default 0.10 or $EVAL_MIN_LLM_PASS)",
    )
    args = parser.parse_args()

    from enterprise_agent_kb.evaluation.evaluator import run_suite

    use_llm = args.use_llm or os.environ.get("EVAL_USE_LLM", "0") == "1"
    print(f"Running {args.suite} suite (scorer={'llm' if use_llm else 'token_overlap'})")

    result = run_suite(
        suite=args.suite,
        version=args.version,
        max_questions=args.max_questions,
        use_llm=use_llm,
    )

    print()
    print("=" * 60)
    print(f"Total: {result.total}, Passed: {result.passed}")
    print(f"Pass rate: {result.pass_rate:.2%}")
    print(f"Avg coverage: {result.avg_coverage:.2%}")
    print(f"By doc:")
    for doc_id, stats in result.by_doc.items():
        if stats["total"] > 0:
            print(f"  {doc_id}: {stats['total']}q, {stats['pass_rate']:.0%} pass, "
                  f"avg_cov={stats['avg_coverage']:.2%}")
    print("=" * 60)

    threshold = args.min_llm_pass if use_llm else args.min_token_pass
    if result.pass_rate < threshold:
        print(f"FAIL: pass_rate {result.pass_rate:.2%} < threshold {threshold:.2%}")
        return 1
    print(f"PASS: pass_rate {result.pass_rate:.2%} >= threshold {threshold:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
