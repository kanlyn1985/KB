from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from agent_kb.context.builder import (
    build_context_pack,
    fill_missing_shapes,
    select_retrieval_cards,
)
from agent_kb.context.context_pack import AgentContextPack
from agent_kb.context.evidence_judge import EvidenceJudgement, judge_context_pack
from agent_kb.core.compiler import compile_text_document
from agent_kb.domains.schema import DomainPack
from agent_kb.pipeline.document_context import CompiledKnowledgeIndex, build_compiled_knowledge_index
from agent_kb.query.query_frame import QueryFrame
from agent_kb.query.understanding import UnderstandingOptions, understand_query
from agent_kb.retrieval.hybrid import hybrid_retrieve
from agent_kb.retrieval.models import RetrievalResult
from agent_kb.retrieval.reranker import Reranker
from agent_kb.storage.sqlite_store import PersistentIndexView, SQLiteKnowledgeStore


@dataclass(frozen=True)
class PersistentQueryResult:
    """Persistent retrieval output with sufficiency judgement and audit run id."""

    query_frame: QueryFrame
    retrieval_result: RetrievalResult
    context_pack: AgentContextPack
    evidence_judgement: EvidenceJudgement
    run_id: str
    store_summary: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_frame": self.query_frame.to_dict(),
            "retrieval_result": self.retrieval_result.to_dict(),
            "context_pack": self.context_pack.to_dict(),
            "evidence_judgement": self.evidence_judgement.to_dict(),
            "run_id": self.run_id,
            "store_summary": dict(self.store_summary),
        }

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "intent": self.query_frame.intent,
            "target_objects": len(self.context_pack.target_objects),
            "retrieval_candidates": len(self.retrieval_result.candidates),
            "selected_cards": len(self.context_pack.retrieval_cards),
            "selected_facts": len(self.context_pack.facts),
            "selected_evidence": len(self.context_pack.evidence),
            "evidence_status": self.evidence_judgement.status,
            "evidence_score": self.evidence_judgement.score,
            "warnings": len(self.context_pack.warnings),
            "knowledge_gaps": len(self.context_pack.knowledge_gaps),
        }


def compile_text_to_store(
    text: str,
    *,
    title: str,
    db_path: str | Path,
    domain_pack: DomainPack | None = None,
    source_type: str = "text",
    source_uri: str | None = None,
    metadata: dict[str, Any] | None = None,
    max_evidence_chars: int = 900,
) -> tuple[CompiledKnowledgeIndex, dict[str, int]]:
    """Compile one text source and upsert its retrieval surfaces into SQLite."""

    compilation = compile_text_document(
        text,
        title=title,
        domain_pack=domain_pack,
        source_type=source_type,
        source_uri=source_uri,
        metadata=metadata,
        max_evidence_chars=max_evidence_chars,
    )
    index = build_compiled_knowledge_index(compilation, domain_pack=domain_pack)
    with SQLiteKnowledgeStore(db_path) as store:
        summary = store.upsert_index(index)
    return index, summary


def query_persistent_store(
    query: str,
    *,
    db_path: str | Path,
    domain_pack: DomainPack | None = None,
    understanding_options: UnderstandingOptions | None = None,
    reranker: Reranker | None = None,
    retrieval_top_k: int = 12,
) -> PersistentQueryResult:
    """Query a persisted knowledge index through hybrid retrieval."""

    frame = understand_query(query, domain_pack=domain_pack, options=understanding_options)
    with SQLiteKnowledgeStore(db_path) as store:
        index = store.load_index_view()
        retrieval_result = hybrid_retrieve(
            frame,
            index,
            persistent_provider=store,
            reranker=reranker,
            top_k=max(1, retrieval_top_k),
        )
        context_pack = _context_from_retrieval(
            frame=frame,
            index=index,
            retrieval_result=retrieval_result,
            domain_pack=domain_pack,
        )
        judgement = judge_context_pack(
            context_pack,
            relevance_score=(
                float(retrieval_result.candidates[0].score)
                if retrieval_result.candidates else 0.0
            ),
        )
        context_pack = _apply_judgement(context_pack, judgement)
        run_id = store.record_retrieval(
            query_frame=frame,
            retrieval_result=retrieval_result,
            evidence_judgement=judgement.to_dict(),
        )
        summary = store.summary()

    return PersistentQueryResult(
        query_frame=frame,
        retrieval_result=retrieval_result,
        context_pack=context_pack,
        evidence_judgement=judgement,
        run_id=run_id,
        store_summary=summary,
    )


def add_persistent_feedback(
    *,
    db_path: str | Path,
    run_id: str,
    rating: int,
    comment: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    with SQLiteKnowledgeStore(db_path) as store:
        return store.add_feedback(
            run_id=run_id,
            rating=rating,
            comment=comment,
            metadata=metadata,
        )


def _context_from_retrieval(
    *,
    frame: QueryFrame,
    index: PersistentIndexView,
    retrieval_result: RetrievalResult,
    domain_pack: DomainPack | None,
) -> AgentContextPack:
    object_ids = set(retrieval_result.selected_object_ids)
    card_ids = set(retrieval_result.selected_card_ids)
    fact_ids = set(retrieval_result.selected_fact_ids)
    evidence_ids = set(retrieval_result.selected_evidence_ids)

    objects = [item for item in index.object_projections if item.object_id in object_ids]
    cards = select_retrieval_cards(
        selected_card_ids=card_ids,
        selected_object_ids=object_ids,
        all_cards=list(index.retrieval_cards),
    )
    facts = [item for item in index.context_facts if item.fact_id in fact_ids]
    evidence = [item for item in index.context_evidence if item.evidence_id in evidence_ids]

    pack = build_context_pack(
        query_frame=frame,
        domain_pack=domain_pack,
        objects=objects,
        retrieval_cards=cards,
        facts=facts,
        evidence=evidence,
    )

    fill = fill_missing_shapes(
        frame,
        list(index.context_facts),
        list(index.context_evidence),
        selected_fact_ids={item.fact_id for item in pack.facts},
        selected_evidence_ids={item.evidence_id for item in pack.evidence},
    )
    if fill.fact_ids or fill.evidence_ids:
        have_facts = {item.fact_id for item in pack.facts}
        have_evidence = {item.evidence_id for item in pack.evidence}
        fact_map = {item.fact_id: item for item in index.context_facts}
        evidence_map = {item.evidence_id: item for item in index.context_evidence}
        extra_facts = [fact_map[fid] for fid in fill.fact_ids if fid in fact_map and fid not in have_facts]
        extra_evidence = [evidence_map[eid] for eid in fill.evidence_ids if eid in evidence_map and eid not in have_evidence]
        pack = replace(
            pack,
            facts=[*pack.facts, *extra_facts],
            evidence=[*pack.evidence, *extra_evidence],
        )
    return pack


def _apply_judgement(
    context_pack: AgentContextPack,
    judgement: EvidenceJudgement,
) -> AgentContextPack:
    warnings = list(context_pack.warnings)
    gaps = list(context_pack.knowledge_gaps)
    strategy = context_pack.recommended_answer_strategy

    if judgement.status != "sufficient":
        warning = f"evidence sufficiency is {judgement.status} ({judgement.score:.2f})"
        if warning not in warnings:
            warnings.append(warning)
        for shape in judgement.missing_shapes:
            gap = f"missing_evidence_shape:{shape}"
            if gap not in gaps:
                gaps.append(gap)
        if judgement.status == "insufficient":
            strategy = "ask_clarification_or_abstain"
        elif strategy == "answer_with_evidence":
            strategy = "answer_with_caution_and_disclose_gaps"

    return replace(
        context_pack,
        warnings=warnings,
        knowledge_gaps=gaps,
        recommended_answer_strategy=strategy,
    )
