from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agent_kb.domains.schema import DomainPack
from agent_kb.query.understanding import understand_query
from agent_kb.retrieval.engine import RetrievalIndexView, retrieve


@dataclass(frozen=True)
class RetrievalGoldenCase:
    case_id: str
    query: str
    expected_object_ids: list[str] = field(default_factory=list)
    expected_card_ids: list[str] = field(default_factory=list)
    expected_fact_ids: list[str] = field(default_factory=list)
    expected_evidence_ids: list[str] = field(default_factory=list)
    top_k: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    query: str
    hit_at_k: bool
    reciprocal_rank: float
    object_recall: float
    card_recall: float
    fact_recall: float
    evidence_recall: float
    first_relevant_rank: int | None
    selected_object_ids: list[str]
    selected_card_ids: list[str]
    selected_fact_ids: list[str]
    selected_evidence_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalEvaluationReport:
    case_count: int
    hit_at_k: float
    mean_reciprocal_rank: float
    mean_object_recall: float
    mean_card_recall: float
    mean_fact_recall: float
    mean_evidence_recall: float
    results: list[RetrievalCaseResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_count": self.case_count,
            "hit_at_k": self.hit_at_k,
            "mean_reciprocal_rank": self.mean_reciprocal_rank,
            "mean_object_recall": self.mean_object_recall,
            "mean_card_recall": self.mean_card_recall,
            "mean_fact_recall": self.mean_fact_recall,
            "mean_evidence_recall": self.mean_evidence_recall,
            "results": [item.to_dict() for item in self.results],
        }


def evaluate_retrieval(
    cases: list[RetrievalGoldenCase],
    index: RetrievalIndexView,
    *,
    domain_pack: DomainPack | None = None,
) -> RetrievalEvaluationReport:
    """Evaluate QueryFrame + retrieval as one reproducible retrieval subsystem."""

    results: list[RetrievalCaseResult] = []
    for case in cases:
        frame = understand_query(case.query, domain_pack=domain_pack)
        result = retrieve(frame, index, top_k=max(1, case.top_k))
        relevant_keys = _relevant_keys(case)
        first_rank = _first_relevant_rank(result.candidates, relevant_keys)
        has_expectation = bool(relevant_keys)
        hit = first_rank is not None if has_expectation else bool(result.candidates)
        results.append(
            RetrievalCaseResult(
                case_id=case.case_id,
                query=case.query,
                hit_at_k=hit,
                reciprocal_rank=(1.0 / first_rank) if first_rank else 0.0,
                object_recall=_recall(case.expected_object_ids, result.selected_object_ids),
                card_recall=_recall(case.expected_card_ids, result.selected_card_ids),
                fact_recall=_recall(case.expected_fact_ids, result.selected_fact_ids),
                evidence_recall=_recall(case.expected_evidence_ids, result.selected_evidence_ids),
                first_relevant_rank=first_rank,
                selected_object_ids=list(result.selected_object_ids),
                selected_card_ids=list(result.selected_card_ids),
                selected_fact_ids=list(result.selected_fact_ids),
                selected_evidence_ids=list(result.selected_evidence_ids),
            )
        )

    count = len(results)
    return RetrievalEvaluationReport(
        case_count=count,
        hit_at_k=_mean([1.0 if item.hit_at_k else 0.0 for item in results]),
        mean_reciprocal_rank=_mean([item.reciprocal_rank for item in results]),
        mean_object_recall=_mean([item.object_recall for item in results]),
        mean_card_recall=_mean([item.card_recall for item in results]),
        mean_fact_recall=_mean([item.fact_recall for item in results]),
        mean_evidence_recall=_mean([item.evidence_recall for item in results]),
        results=results,
    )


def _relevant_keys(case: RetrievalGoldenCase) -> set[str]:
    keys = {f"card:{item}" for item in case.expected_card_ids}
    keys.update(f"fact:{item}" for item in case.expected_fact_ids)
    keys.update(f"evidence:{item}" for item in case.expected_evidence_ids)
    # Object expectations are satisfied by a card or fact payload carrying the object.
    keys.update(f"object:{item}" for item in case.expected_object_ids)
    return keys


def _first_relevant_rank(candidates: list[Any], relevant_keys: set[str]) -> int | None:
    if not relevant_keys:
        return 1 if candidates else None
    for candidate in candidates:
        direct_key = f"{candidate.source_type}:{candidate.source_id}"
        object_id = str(candidate.payload.get("object_id") or candidate.payload.get("subject") or "")
        if direct_key in relevant_keys or (object_id and f"object:{object_id}" in relevant_keys):
            return candidate.rank
    return None


def _recall(expected: list[str], actual: list[str]) -> float:
    if not expected:
        return 1.0
    return len(set(expected) & set(actual)) / len(set(expected))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
