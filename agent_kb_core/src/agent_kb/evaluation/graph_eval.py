from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from agent_kb.graph.store import GraphEdge


@dataclass(frozen=True)
class GraphGoldenEdge:
    relation_type: str
    source_object_id: str
    target_object_id: str

    def key(self) -> tuple[str, str, str]:
        return (self.relation_type, self.source_object_id, self.target_object_id)


@dataclass(frozen=True)
class GraphEvaluationReport:
    predicted_count: int
    expected_count: int
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float
    recall: float
    f1: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


def evaluate_graph_edges(
    predicted: Iterable[GraphEdge],
    expected: Iterable[GraphGoldenEdge],
    *,
    undirected_relation_types: set[str] | None = None,
) -> GraphEvaluationReport:
    undirected = set(undirected_relation_types or {"related_to"})
    predicted_keys = {
        _normalize(edge.relation_type, edge.source_object_id, edge.target_object_id, undirected)
        for edge in predicted
    }
    expected_keys = {
        _normalize(edge.relation_type, edge.source_object_id, edge.target_object_id, undirected)
        for edge in expected
    }
    true_positives = predicted_keys & expected_keys
    false_positives = predicted_keys - expected_keys
    false_negatives = expected_keys - predicted_keys
    precision = len(true_positives) / len(predicted_keys) if predicted_keys else (1.0 if not expected_keys else 0.0)
    recall = len(true_positives) / len(expected_keys) if expected_keys else 1.0
    f1 = 0.0 if precision + recall == 0.0 else 2.0 * precision * recall / (precision + recall)
    return GraphEvaluationReport(
        predicted_count=len(predicted_keys),
        expected_count=len(expected_keys),
        true_positive_count=len(true_positives),
        false_positive_count=len(false_positives),
        false_negative_count=len(false_negatives),
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _normalize(
    relation_type: str,
    source: str,
    target: str,
    undirected: set[str],
) -> tuple[str, str, str]:
    if relation_type in undirected and target < source:
        source, target = target, source
    return relation_type, source, target
