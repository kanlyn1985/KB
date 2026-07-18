from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from agent_kb.query.query_frame import QueryFrame
from agent_kb.retrieval.engine import RetrievalIndexView, retrieve
from agent_kb.retrieval.models import RetrievalCandidate, RetrievalDiagnostics, RetrievalResult
from agent_kb.retrieval.reranker import DeterministicReranker, Reranker


class PersistentCandidateProvider(Protocol):
    def search(self, query_frame: QueryFrame, *, limit: int = 32) -> list[RetrievalCandidate]: ...


def hybrid_retrieve(
    query_frame: QueryFrame,
    index: RetrievalIndexView,
    *,
    persistent_provider: PersistentCandidateProvider | None = None,
    reranker: Reranker | None = None,
    top_k: int = 12,
    candidate_pool_size: int = 48,
) -> RetrievalResult:
    """Fuse the Phase 4 in-memory baseline with a persistent search adapter."""

    pool_size = max(top_k, candidate_pool_size)
    baseline = retrieve(query_frame, index, top_k=pool_size)
    persistent = (
        persistent_provider.search(query_frame, limit=pool_size)
        if persistent_provider is not None
        else []
    )
    merged = _merge_candidates(baseline.candidates, persistent)
    ranked = (reranker or DeterministicReranker()).rerank(
        query_frame,
        merged,
        top_k=max(1, top_k),
    )
    object_ids, card_ids, fact_ids, evidence_ids = _selected_ids(query_frame, ranked)

    executed = list(baseline.diagnostics.executed_channels)
    counts = dict(baseline.diagnostics.channel_candidate_counts)
    if persistent_provider is not None:
        if "persistent_search" not in executed:
            executed.append("persistent_search")
        counts["persistent_search"] = len(persistent)

    diagnostics = RetrievalDiagnostics(
        requested_channels=list(baseline.diagnostics.requested_channels),
        executed_channels=executed,
        skipped_channels=dict(baseline.diagnostics.skipped_channels),
        channel_candidate_counts=counts,
        query_terms=list(baseline.diagnostics.query_terms),
        target_object_ids=list(baseline.diagnostics.target_object_ids),
    )
    return RetrievalResult(
        query_frame=query_frame,
        candidates=ranked,
        selected_object_ids=object_ids,
        selected_card_ids=card_ids,
        selected_fact_ids=fact_ids,
        selected_evidence_ids=evidence_ids,
        diagnostics=diagnostics,
    )


def _merge_candidates(
    baseline: list[RetrievalCandidate],
    persistent: list[RetrievalCandidate],
) -> list[RetrievalCandidate]:
    merged: dict[str, RetrievalCandidate] = {}
    for candidate in [*baseline, *persistent]:
        key = f"{candidate.source_type}:{candidate.source_id}"
        existing = merged.get(key)
        if existing is None:
            merged[key] = candidate
            continue

        reasons = list(existing.reasons)
        for reason in candidate.reasons:
            if reason not in reasons:
                reasons.append(reason)
        matched_terms = list(existing.matched_terms)
        for term in candidate.matched_terms:
            if term not in matched_terms:
                matched_terms.append(term)
        payload = dict(existing.payload)
        for key_name, value in candidate.payload.items():
            payload.setdefault(key_name, value)
        channels = list(payload.get("channels") or [])
        for channel in [existing.channel, candidate.channel]:
            if channel and channel not in channels:
                channels.append(channel)
        payload["channels"] = channels

        # The second source is corroborating evidence, not an unbounded score sum.
        corroboration = min(existing.score, candidate.score) * 0.20
        merged[key] = replace(
            existing if existing.score >= candidate.score else candidate,
            score=max(existing.score, candidate.score) + corroboration,
            matched_terms=matched_terms,
            reasons=reasons + (["cross_index_corroboration"] if "cross_index_corroboration" not in reasons else []),
            payload=payload,
            channel="hybrid",
        )
    return list(merged.values())


def _selected_ids(
    frame: QueryFrame,
    candidates: list[RetrievalCandidate],
) -> tuple[list[str], list[str], list[str], list[str]]:
    object_ids: list[str] = [item.object_id for item in frame.target_objects]
    card_ids: list[str] = []
    fact_ids: list[str] = []
    evidence_ids: list[str] = []

    for candidate in candidates:
        payload = candidate.payload
        linked_object = str(payload.get("object_id") or payload.get("subject") or "")
        if linked_object and linked_object not in object_ids:
            object_ids.append(linked_object)
        if candidate.source_type == "object" and candidate.source_id not in object_ids:
            object_ids.append(candidate.source_id)
        if candidate.source_type == "card" and candidate.source_id not in card_ids:
            card_ids.append(candidate.source_id)
        if candidate.source_type == "fact" and candidate.source_id not in fact_ids:
            fact_ids.append(candidate.source_id)
        if candidate.source_type == "evidence" and candidate.source_id not in evidence_ids:
            evidence_ids.append(candidate.source_id)
        for evidence_id in payload.get("evidence_ids") or []:
            if evidence_id and evidence_id not in evidence_ids:
                evidence_ids.append(str(evidence_id))

    return object_ids, card_ids, fact_ids, evidence_ids
