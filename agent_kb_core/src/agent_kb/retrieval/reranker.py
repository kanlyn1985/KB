from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from agent_kb.query.query_frame import QueryFrame
from agent_kb.retrieval.models import RetrievalCandidate


class Reranker(Protocol):
    def rerank(
        self,
        query_frame: QueryFrame,
        candidates: list[RetrievalCandidate],
        *,
        top_k: int,
    ) -> list[RetrievalCandidate]: ...


class DeterministicReranker:
    """Intent-aware baseline reranker.

    This preserves a stable dependency-free baseline before a cross-encoder or
    LLM reranker is plugged in. It only uses structured retrieval signals.
    """

    def rerank(
        self,
        query_frame: QueryFrame,
        candidates: list[RetrievalCandidate],
        *,
        top_k: int,
    ) -> list[RetrievalCandidate]:
        target_ids = {item.object_id for item in query_frame.target_objects}
        preferred_types = set(query_frame.preferred_fact_types)
        rescored: list[RetrievalCandidate] = []

        for candidate in candidates:
            payload = candidate.payload
            linked_object = str(payload.get("object_id") or payload.get("subject") or "")
            score = float(candidate.score)
            reasons = list(candidate.reasons)

            if linked_object and linked_object in target_ids:
                score += 0.45
                _append_unique(reasons, "rerank_target_object")
            if payload.get("fact_type") in preferred_types:
                score += 0.30
                _append_unique(reasons, "rerank_preferred_fact_type")
            if payload.get("evidence_ids"):
                score += 0.12
                _append_unique(reasons, "rerank_has_evidence_binding")
            if query_frame.intent in set(payload.get("answer_shapes") or []):
                score += 0.20
                _append_unique(reasons, "rerank_answer_shape")
            score += min(len(candidate.matched_terms), 5) * 0.02

            source_boost = {
                "card": 0.10,
                "fact": 0.09,
                "evidence": 0.06,
                "object": 0.04,
            }.get(candidate.source_type, 0.0)
            score += source_boost
            rescored.append(replace(candidate, score=score, reasons=reasons, channel="reranked"))

        rescored.sort(key=lambda item: (item.score, item.source_type, item.source_id), reverse=True)
        return [replace(item, rank=rank) for rank, item in enumerate(rescored[: max(1, top_k)], start=1)]


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
