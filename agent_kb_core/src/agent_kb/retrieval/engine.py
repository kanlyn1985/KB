from __future__ import annotations

import re
from dataclasses import replace
from typing import Protocol

from agent_kb.context.context_pack import ContextEvidence, ContextFact
from agent_kb.projection.models import ObjectProjection
from agent_kb.query.query_frame import QueryFrame
from agent_kb.retrieval.cards import RetrievalCard
from agent_kb.retrieval.models import RetrievalCandidate, RetrievalDiagnostics, RetrievalResult


class RetrievalIndexView(Protocol):
    object_projections: list[ObjectProjection]
    retrieval_cards: list[RetrievalCard]
    context_facts: list[ContextFact]
    context_evidence: list[ContextEvidence]


_CHANNEL_WEIGHTS: dict[str, float] = {
    "object_card": 1.35,
    "fact": 1.25,
    "table": 1.2,
    "evidence": 1.0,
    "keyword": 0.95,
    "semantic": 0.9,
}


def retrieve(
    query_frame: QueryFrame,
    index: RetrievalIndexView,
    *,
    top_k: int = 12,
    per_channel_limit: int = 24,
) -> RetrievalResult:
    """Run deterministic multi-channel retrieval and intent-aware fusion.

    Phase 4 deliberately establishes a stable baseline before adding vector or
    LLM rerank providers. The engine uses object aliases, canonical ids, fact
    types, evidence text, answer shapes, and QueryFrame intent constraints.
    """

    terms = _query_terms(query_frame)
    requested = _normalize_requested_channels(query_frame.retrieval_channels)
    channel_results: dict[str, list[RetrievalCandidate]] = {}
    skipped: dict[str, str] = {}

    for channel in requested:
        if channel == "object_card":
            channel_results[channel] = _search_cards(query_frame, index.retrieval_cards, terms)
        elif channel == "fact":
            channel_results[channel] = _search_facts(query_frame, index.context_facts, terms)
        elif channel == "table":
            channel_results[channel] = _search_tables(query_frame, index.context_facts, index.context_evidence, terms)
        elif channel == "evidence":
            channel_results[channel] = _search_evidence(query_frame, index.context_evidence, terms, channel="evidence")
        elif channel == "keyword":
            channel_results[channel] = _search_keyword(query_frame, index, terms)
        elif channel == "semantic":
            # Dependency-free semantic fallback: canonical objects and aliases
            # are treated as semantic concepts rather than raw token equality.
            channel_results[channel] = _search_semantic_fallback(query_frame, index, terms)
        elif channel in {"graph", "wiki_chunk", "source_unit", "document"}:
            skipped[channel] = "channel_not_materialized_in_phase4_index"
        else:
            skipped[channel] = "unsupported_channel"

    ranked_channels: dict[str, list[RetrievalCandidate]] = {}
    for channel, candidates in channel_results.items():
        ranked = sorted(candidates, key=lambda item: (item.score, item.source_id), reverse=True)[:per_channel_limit]
        ranked_channels[channel] = [replace(item, rank=rank) for rank, item in enumerate(ranked, start=1)]

    fused = _fuse(query_frame, ranked_channels)
    selected = fused[: max(1, top_k)]
    object_ids, card_ids, fact_ids, evidence_ids = _selected_ids(query_frame, selected)

    diagnostics = RetrievalDiagnostics(
        requested_channels=requested,
        executed_channels=list(ranked_channels),
        skipped_channels=skipped,
        channel_candidate_counts={name: len(items) for name, items in ranked_channels.items()},
        query_terms=terms,
        target_object_ids=[item.object_id for item in query_frame.target_objects],
    )
    return RetrievalResult(
        query_frame=query_frame,
        candidates=selected,
        selected_object_ids=object_ids,
        selected_card_ids=card_ids,
        selected_fact_ids=fact_ids,
        selected_evidence_ids=evidence_ids,
        diagnostics=diagnostics,
    )


def _normalize_requested_channels(channels: list[str]) -> list[str]:
    result: list[str] = []
    for channel in channels or ["object_card", "fact", "evidence"]:
        normalized = str(channel or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _query_terms(frame: QueryFrame) -> list[str]:
    values = [
        frame.normalized_query,
        frame.target_topic,
        *frame.must_terms,
        *frame.aliases,
        *frame.should_terms,
        *(target.object_id for target in frame.target_objects),
        *(target.canonical_name for target in frame.target_objects),
        *(target.matched_text for target in frame.target_objects),
    ]
    terms: list[str] = []
    for value in values:
        text = _normalize_text(str(value or ""))
        if text and text not in terms:
            terms.append(text)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_/-]{1,31}|\d+(?:\.\d+)?(?:mVpp|mV|V|A|W|kW|%|ms|s)?", text, re.I):
            normalized = _normalize_text(token)
            if normalized and normalized not in terms:
                terms.append(normalized)
    return terms[:48]


def _search_cards(frame: QueryFrame, cards: list[RetrievalCard], terms: list[str]) -> list[RetrievalCandidate]:
    target_ids = {item.object_id for item in frame.target_objects}
    candidates: list[RetrievalCandidate] = []
    for card in cards:
        blob = " ".join([card.object_id or "", card.title, card.search_text, *card.aliases, *card.answer_shapes])
        score, matched = _text_score(blob, terms)
        reasons: list[str] = []
        if card.object_id in target_ids:
            score += 4.0
            reasons.append("exact_target_object")
        if frame.intent in card.answer_shapes:
            score += 1.5
            reasons.append("answer_shape_match")
        if not score:
            continue
        candidates.append(
            RetrievalCandidate(
                candidate_id=f"card:{card.card_id}",
                source_type="card",
                source_id=card.card_id,
                channel="object_card",
                score=score,
                matched_terms=matched,
                reasons=reasons or ["lexical_card_match"],
                payload={
                    "object_id": card.object_id,
                    "evidence_ids": list(card.evidence_ids),
                    "answer_shapes": list(card.answer_shapes),
                },
            )
        )
    return candidates


def _search_facts(frame: QueryFrame, facts: list[ContextFact], terms: list[str]) -> list[RetrievalCandidate]:
    target_ids = {item.object_id for item in frame.target_objects}
    preferred = set(frame.preferred_fact_types)
    candidates: list[RetrievalCandidate] = []
    for fact in facts:
        blob = " ".join(
            [
                fact.subject or "",
                fact.fact_type,
                fact.predicate,
                str(fact.object_value),
                " ".join(f"{key} {value}" for key, value in fact.qualifiers.items()),
            ]
        )
        score, matched = _text_score(blob, terms)
        reasons: list[str] = []
        if fact.subject in target_ids:
            score += 3.5
            reasons.append("fact_subject_matches_target")
        if fact.fact_type in preferred:
            score += 2.0
            reasons.append("preferred_fact_type")
        if not score:
            continue
        candidates.append(
            RetrievalCandidate(
                candidate_id=f"fact:{fact.fact_id}",
                source_type="fact",
                source_id=fact.fact_id,
                channel="fact",
                score=score + fact.confidence,
                matched_terms=matched,
                reasons=reasons or ["lexical_fact_match"],
                payload={
                    "subject": fact.subject,
                    "fact_type": fact.fact_type,
                    "evidence_ids": list(fact.evidence_ids),
                },
            )
        )
    return candidates


def _search_tables(
    frame: QueryFrame,
    facts: list[ContextFact],
    evidence: list[ContextEvidence],
    terms: list[str],
) -> list[RetrievalCandidate]:
    candidates: list[RetrievalCandidate] = []
    for fact in facts:
        if fact.fact_type != "table_row":
            continue
        score, matched = _text_score(str(fact.object_value), terms)
        if score or "table_row" in frame.required_evidence_shapes:
            candidates.append(
                RetrievalCandidate(
                    candidate_id=f"fact:{fact.fact_id}",
                    source_type="fact",
                    source_id=fact.fact_id,
                    channel="table",
                    score=score + 1.25,
                    matched_terms=matched,
                    reasons=["table_fact"],
                    payload={"subject": fact.subject, "fact_type": fact.fact_type, "evidence_ids": list(fact.evidence_ids)},
                )
            )
    for item in evidence:
        if "|" not in item.snippet and "\t" not in item.snippet and len(re.findall(r"\s{2,}", item.snippet)) < 2:
            continue
        score, matched = _text_score(item.snippet, terms)
        if score:
            candidates.append(
                RetrievalCandidate(
                    candidate_id=f"evidence:{item.evidence_id}",
                    source_type="evidence",
                    source_id=item.evidence_id,
                    channel="table",
                    score=score + 0.75,
                    matched_terms=matched,
                    reasons=["table_like_evidence"],
                    payload={"document_id": item.document_id, "page_no": item.page_no},
                )
            )
    return candidates


def _search_evidence(
    frame: QueryFrame,
    evidence: list[ContextEvidence],
    terms: list[str],
    *,
    channel: str,
) -> list[RetrievalCandidate]:
    candidates: list[RetrievalCandidate] = []
    for item in evidence:
        score, matched = _text_score(item.snippet, terms)
        if not score:
            continue
        candidates.append(
            RetrievalCandidate(
                candidate_id=f"evidence:{item.evidence_id}",
                source_type="evidence",
                source_id=item.evidence_id,
                channel=channel,
                score=score + item.confidence * 0.25,
                matched_terms=matched,
                reasons=["evidence_text_match"],
                payload={"document_id": item.document_id, "page_no": item.page_no},
            )
        )
    return candidates


def _search_keyword(frame: QueryFrame, index: RetrievalIndexView, terms: list[str]) -> list[RetrievalCandidate]:
    candidates = _search_cards(frame, index.retrieval_cards, terms)
    evidence = _search_evidence(frame, index.context_evidence, terms, channel="keyword")
    return [replace(item, channel="keyword", score=item.score * 0.9) for item in candidates] + evidence


def _search_semantic_fallback(frame: QueryFrame, index: RetrievalIndexView, terms: list[str]) -> list[RetrievalCandidate]:
    concept_terms = _query_terms(frame)
    candidates: list[RetrievalCandidate] = []
    for card in index.retrieval_cards:
        alias_blob = " ".join([card.object_id or "", card.title, *card.aliases])
        score, matched = _text_score(alias_blob, concept_terms)
        if not score:
            continue
        candidates.append(
            RetrievalCandidate(
                candidate_id=f"card:{card.card_id}",
                source_type="card",
                source_id=card.card_id,
                channel="semantic",
                score=score + (1.0 if frame.intent in card.answer_shapes else 0.0),
                matched_terms=matched,
                reasons=["domain_alias_semantic_fallback"],
                payload={"object_id": card.object_id, "evidence_ids": list(card.evidence_ids)},
            )
        )
    return candidates


def _fuse(frame: QueryFrame, channels: dict[str, list[RetrievalCandidate]]) -> list[RetrievalCandidate]:
    aggregate: dict[str, dict[str, object]] = {}
    for channel, candidates in channels.items():
        weight = _CHANNEL_WEIGHTS.get(channel, 1.0)
        max_score = max((candidate.score for candidate in candidates), default=1.0) or 1.0
        for candidate in candidates:
            key = f"{candidate.source_type}:{candidate.source_id}"
            state = aggregate.setdefault(
                key,
                {
                    "candidate": candidate,
                    "score": 0.0,
                    "terms": [],
                    "reasons": [],
                    "channels": [],
                },
            )
            # Weighted reciprocal-rank fusion plus a bounded channel relevance term.
            state["score"] = float(state["score"]) + weight * (1.0 / (60 + candidate.rank)) + 0.12 * weight * (candidate.score / max_score)
            _extend_unique(state["terms"], candidate.matched_terms)
            _extend_unique(state["reasons"], candidate.reasons)
            _extend_unique(state["channels"], [channel])

    target_ids = {item.object_id for item in frame.target_objects}
    fused: list[RetrievalCandidate] = []
    for state in aggregate.values():
        candidate = state["candidate"]
        score = float(state["score"])
        payload = dict(candidate.payload)
        if payload.get("object_id") in target_ids or payload.get("subject") in target_ids:
            score += 0.3
            _extend_unique(state["reasons"], ["fusion_target_boost"])
        if payload.get("fact_type") in set(frame.preferred_fact_types):
            score += 0.2
            _extend_unique(state["reasons"], ["fusion_fact_shape_boost"])
        payload["channels"] = list(state["channels"])
        fused.append(
            replace(
                candidate,
                channel="fused",
                score=score,
                rank=0,
                matched_terms=list(state["terms"]),
                reasons=list(state["reasons"]),
                payload=payload,
            )
        )
    fused.sort(key=lambda item: (item.score, item.source_type, item.source_id), reverse=True)
    return [replace(item, rank=rank) for rank, item in enumerate(fused, start=1)]


def _selected_ids(frame: QueryFrame, candidates: list[RetrievalCandidate]) -> tuple[list[str], list[str], list[str], list[str]]:
    object_ids = [item.object_id for item in frame.target_objects]
    card_ids: list[str] = []
    fact_ids: list[str] = []
    evidence_ids: list[str] = []
    for candidate in candidates:
        if candidate.source_type == "card":
            _append_unique(card_ids, candidate.source_id)
            _append_unique(object_ids, str(candidate.payload.get("object_id") or ""))
        elif candidate.source_type == "fact":
            _append_unique(fact_ids, candidate.source_id)
            _append_unique(object_ids, str(candidate.payload.get("subject") or ""))
        elif candidate.source_type == "evidence":
            _append_unique(evidence_ids, candidate.source_id)
        for evidence_id in candidate.payload.get("evidence_ids", []) or []:
            _append_unique(evidence_ids, str(evidence_id))
    return object_ids[:12], card_ids[:12], fact_ids[:20], evidence_ids[:24]


def _text_score(text: str, terms: list[str]) -> tuple[float, list[str]]:
    blob = _normalize_text(text)
    if not blob:
        return 0.0, []
    matched: list[str] = []
    score = 0.0
    for term in terms:
        normalized = _normalize_text(term)
        if len(normalized) < 2 or normalized not in blob:
            continue
        if normalized not in matched:
            matched.append(normalized)
        length_weight = min(len(normalized), 24) / 12
        score += 0.7 + length_weight
        if blob == normalized:
            score += 1.5
    return score, matched


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _extend_unique(items: list[str], values: list[str]) -> None:
    for value in values:
        _append_unique(items, value)
