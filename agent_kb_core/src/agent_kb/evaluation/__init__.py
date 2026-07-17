"""Golden-case retrieval evaluation contracts and runners."""

from .retrieval_eval import (
    RetrievalCaseResult,
    RetrievalEvaluationReport,
    RetrievalGoldenCase,
    evaluate_retrieval,
)

__all__ = [
    "RetrievalGoldenCase",
    "RetrievalCaseResult",
    "RetrievalEvaluationReport",
    "evaluate_retrieval",
]
