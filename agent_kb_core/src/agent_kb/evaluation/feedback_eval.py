from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FeedbackSlice:
    key: str
    count: int
    mean_rating: float
    positive_rate: float
    negative_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeedbackEvaluationReport:
    feedback_count: int
    rated_run_count: int
    mean_rating: float
    positive_rate: float
    negative_rate: float
    by_intent: list[FeedbackSlice] = field(default_factory=list)
    by_evidence_status: list[FeedbackSlice] = field(default_factory=list)
    channel_counts: dict[str, int] = field(default_factory=dict)
    improvement_candidates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_count": self.feedback_count,
            "rated_run_count": self.rated_run_count,
            "mean_rating": self.mean_rating,
            "positive_rate": self.positive_rate,
            "negative_rate": self.negative_rate,
            "by_intent": [item.to_dict() for item in self.by_intent],
            "by_evidence_status": [item.to_dict() for item in self.by_evidence_status],
            "channel_counts": dict(self.channel_counts),
            "improvement_candidates": list(self.improvement_candidates),
        }


def evaluate_feedback(db_path: str | Path) -> FeedbackEvaluationReport:
    """Aggregate explicit retrieval feedback into tuning signals."""

    connection = sqlite3.connect(Path(db_path))
    connection.row_factory = sqlite3.Row
    try:
        rows = list(
            connection.execute(
                """
                SELECT f.rating, f.comment, f.metadata_json,
                       r.query_frame_json, r.retrieval_result_json, r.evidence_judgement_json
                FROM feedback f
                JOIN retrieval_runs r ON r.run_id = f.run_id
                ORDER BY f.created_at
                """
            )
        )
    except sqlite3.OperationalError:
        rows = []
    finally:
        connection.close()

    ratings: list[int] = []
    intent_ratings: dict[str, list[int]] = defaultdict(list)
    status_ratings: dict[str, list[int]] = defaultdict(list)
    channel_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()

    for row in rows:
        rating = int(row["rating"])
        ratings.append(rating)
        frame = _loads(row["query_frame_json"], {})
        result = _loads(row["retrieval_result_json"], {})
        judgement = _loads(row["evidence_judgement_json"], {})
        intent = str(frame.get("intent") or "unknown")
        status = str(judgement.get("status") or "unknown")
        intent_ratings[intent].append(rating)
        status_ratings[status].append(rating)
        diagnostics = result.get("diagnostics") or {}
        for channel in diagnostics.get("executed_channels") or []:
            channel_counts[str(channel)] += 1
        if rating < 0:
            if status == "insufficient":
                issue_counts["negative_feedback_with_insufficient_evidence"] += 1
            if not result.get("candidates"):
                issue_counts["negative_feedback_with_no_candidates"] += 1
            metadata = _loads(row["metadata_json"], {})
            reason = str(metadata.get("reason") or "").strip()
            if reason:
                issue_counts[f"feedback_reason:{reason}"] += 1

    return FeedbackEvaluationReport(
        feedback_count=len(rows),
        rated_run_count=len(ratings),
        mean_rating=_mean(ratings),
        positive_rate=_rate(ratings, lambda value: value > 0),
        negative_rate=_rate(ratings, lambda value: value < 0),
        by_intent=_slices(intent_ratings),
        by_evidence_status=_slices(status_ratings),
        channel_counts=dict(channel_counts.most_common()),
        improvement_candidates=[key for key, _ in issue_counts.most_common(20)],
    )


def _slices(grouped: dict[str, list[int]]) -> list[FeedbackSlice]:
    slices = [
        FeedbackSlice(
            key=key,
            count=len(values),
            mean_rating=_mean(values),
            positive_rate=_rate(values, lambda value: value > 0),
            negative_rate=_rate(values, lambda value: value < 0),
        )
        for key, values in grouped.items()
    ]
    return sorted(slices, key=lambda item: (-item.count, item.key))


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _mean(values: list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _rate(values: list[int], predicate) -> float:
    return sum(1 for value in values if predicate(value)) / len(values) if values else 0.0
