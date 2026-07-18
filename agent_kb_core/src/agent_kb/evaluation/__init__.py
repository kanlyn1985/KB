"""Golden-case and feedback-driven evaluation contracts."""

from .feedback_eval import FeedbackEvaluationReport, FeedbackSlice, evaluate_feedback
from .retrieval_eval import (
    RetrievalCaseResult,
    RetrievalEvaluationReport,
    RetrievalGoldenCase,
    evaluate_retrieval,
)

__all__ = [
    "FeedbackEvaluationReport",
    "FeedbackSlice",
    "RetrievalGoldenCase",
    "RetrievalCaseResult",
    "RetrievalEvaluationReport",
    "evaluate_feedback",
    "evaluate_retrieval",
]
