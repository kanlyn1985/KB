"""Phase 1 evaluation framework.

Public API:
  - run_suite(suite: "golden"|"full", version: str = "v1") -> EvalResult
  - compute_coverage(question, system_answer, expected_points) -> float
  - score_answer(question, system_answer, expected_points) -> ScoreResult

The evaluator uses LLM to extract which expected_points the system
answer covers, then computes coverage (covered / total).  Multi-prompt
鲁棒性: 同一题用 2 个 prompt 跑, 差 < 10% 才认为有效.
"""
from .evaluator import (
    EvalResult,
    ScoreResult,
    run_suite,
    compute_coverage,
    score_answer,
)

__all__ = ["EvalResult", "ScoreResult", "run_suite", "compute_coverage", "score_answer"]
