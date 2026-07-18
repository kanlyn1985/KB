from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from agent_kb.context.builder import build_context_pack
from agent_kb.context.context_pack import AgentContextPack
from agent_kb.context.evidence_judge import EvidenceJudgement, judge_context_pack
from agent_kb.core.compiler import compile_text_document
from agent_kb.domains.schema import DomainPack
from agent_kb.embeddings import EmbeddingProvider
from agent_kb.graph import SQLiteGraphStore
from agent_kb.pipeline.document_context import CompiledKnowledgeIndex, build_compiled_knowledge_index
from agent_kb.query.query_frame import QueryFrame
from agent_kb.query.understanding import UnderstandingOptions, understand_query
from agent_kb.retrieval.hybrid import hybrid_retrieve
from agent_kb.retrieval.models import RetrievalResult
from agent_kb.retrieval.production import ProductionCandidateProvider
from agent_kb.retrieval.reranker import Reranker
from agent_kb.retrieval.vector import SQLiteVectorIndex, VectorIndexSummary
from agent_kb.storage.lifecycle import DocumentLifecycleRecord, DocumentLifecycleStore, DocumentVersion
from agent_kb.storage.migrations import SchemaMigrator
from agent_kb.storage.sqlite_store import PersistentIndexView, SQLiteKnowledgeStore


@dataclass(frozen=True)
class ProductionIndexResult:
    compiled_index: CompiledKnowledgeIndex
    store_summary: dict[str, int]
    vector_summary: VectorIndexSummary
    document_version: DocumentVersion
    graph_edge_count: int
    schema_version: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "compiled_index": self.compiled_index.to_dict(),
            "store_summary": dict(self.store_summary),
            "vector_summary": self.vector_summary.to_dict(),
            "document_version": self.document_version.to_dict(),
            "graph_edge_count": self.graph_edge_count,
            "schema_version": self.schema_version,
        }

    @property
    def summary(self) -> dict[str, Any]:
        return {
            **self.compiled_index.summary,
            **self.store_summary,
            "vectors": self.vector_summary.vector_count,
            "graph_edges_materialized": self.graph_edge_count,
            "logical_document_id": self.document_version.logical_document_id,
            "version_id": self.document_version.version_id,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class ProductionQueryResult:
    query_frame: QueryFrame
    retrieval_result: RetrievalResult
    context_pack: AgentContextPack
    evidence_judgement: EvidenceJudgement
    run_id: str
    store_summary: dict[str, int]
    schema_version: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_frame": self.query_frame.to_dict(),
            "retrieval_result": self.retrieval_result.to_dict(),
            "context_pack": self.context_pack.to_dict(),
            "evidence_judgement": self.evidence_judgement.to_dict(),
            "run_id": self.run_id,
            "store_summary": dict(self.store_summary),
            "schema_version": self.schema_version,
        }

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "intent": self.query_frame.intent,
            "retrieval_candidates": len(self.retrieval_result.candidates),
            "selected_objects": len(self.context_pack.target_objects),
            "selected_cards": len(self.context_pack.retrieval_cards),
            "selected_facts": len(self.context_pack.facts),
            "selected_evidence": len(self.context_pack.evidence),
            "evidence_status": self.evidence_judgement.status,
            "evidence_score": self.evidence_judgement.score,
            "schema_version": self.schema_version,
        }


def compile_text_to_production_store(
    text: str,
    *,
    title: str,
    db_path: str | Path,
    domain_pack: DomainPack | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    source_type: str = "text",
    source_uri: str | None = None,
    version_label: str | None = None,
    logical_document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    max_evidence_chars: int = 900,
) -> ProductionIndexResult:
    compilation = compile_text_document(
        text,
        title=title,
        domain_pack=domain_pack,
        source_type=source_type,
        source_uri=source_uri,
        version_label=version_label,
        metadata=metadata,
        max_evidence_chars=max_evidence_chars,
    )
    index = build_compiled_knowledge_index(compilation, domain_pack=domain_pack)
    with SQLiteKnowledgeStore(db_path) as store:
        migrator = SchemaMigrator(store.connection)
        migrator.migrate()
        store_summary = store.upsert_index(index)
        lifecycle = DocumentLifecycleStore(store.connection)
        document_version = lifecycle.register_version(
            compilation.document,
            logical_document_id=logical_document_id,
            activate=True,
        )
        vector_index = SQLiteVectorIndex(store.connection, provider=embedding_provider)
        vector_summary = vector_index.index_view(index)
        graph = SQLiteGraphStore(store.connection)
        graph_edge_count = graph.materialize_from_cards(index.retrieval_cards)
        schema_version = migrator.current_version()
    return ProductionIndexResult(
        compiled_index=index,
        store_summary=store_summary,
        vector_summary=vector_summary,
        document_version=document_version,
        graph_edge_count=graph_edge_count,
        schema_version=schema_version,
    )


def query_production_store(
    query: str,
    *,
    db_path: str | Path,
    domain_pack: DomainPack | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    understanding_options: UnderstandingOptions | None = None,
    reranker: Reranker | None = None,
    retrieval_top_k: int = 12,
) -> ProductionQueryResult:
    frame = understand_query(query, domain_pack=domain_pack, options=understanding_options)
    with SQLiteKnowledgeStore(db_path) as store:
        migrator = SchemaMigrator(store.connection)
        migrator.migrate()
        index = store.load_index_view()
        vector = SQLiteVectorIndex(store.connection, provider=embedding_provider)
        graph = SQLiteGraphStore(store.connection)
        provider = ProductionCandidateProvider(lexical=store, vector=vector, graph=graph)
        retrieval_result = hybrid_retrieve(
            frame,
            index,
            persistent_provider=provider,
            reranker=reranker,
            top_k=max(1, retrieval_top_k),
        )
        context_pack = _context_from_retrieval(
            frame=frame,
            index=index,
            retrieval_result=retrieval_result,
            domain_pack=domain_pack,
        )
        judgement = judge_context_pack(context_pack)
        context_pack = _apply_judgement(context_pack, judgement)
        run_id = store.record_retrieval(
            query_frame=frame,
            retrieval_result=retrieval_result,
            evidence_judgement=judgement.to_dict(),
        )
        summary = store.summary()
        schema_version = migrator.current_version()
    return ProductionQueryResult(
        query_frame=frame,
        retrieval_result=retrieval_result,
        context_pack=context_pack,
        evidence_judgement=judgement,
        run_id=run_id,
        store_summary=summary,
        schema_version=schema_version,
    )


def list_production_documents(db_path: str | Path, *, include_deleted: bool = False) -> list[DocumentLifecycleRecord]:
    with SQLiteKnowledgeStore(db_path) as store:
        return DocumentLifecycleStore(store.connection).list_documents(include_deleted=include_deleted)


def set_production_document_status(db_path: str | Path, logical_document_id: str, status: str) -> None:
    with SQLiteKnowledgeStore(db_path) as store:
        DocumentLifecycleStore(store.connection).set_status(logical_document_id, status)


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
    return build_context_pack(
        query_frame=frame,
        domain_pack=domain_pack,
        objects=[item for item in index.object_projections if item.object_id in object_ids],
        retrieval_cards=[item for item in index.retrieval_cards if item.card_id in card_ids],
        facts=[item for item in index.context_facts if item.fact_id in fact_ids],
        evidence=[item for item in index.context_evidence if item.evidence_id in evidence_ids],
    )


def _apply_judgement(context_pack: AgentContextPack, judgement: EvidenceJudgement) -> AgentContextPack:
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
        strategy = (
            "ask_clarification_or_abstain"
            if judgement.status == "insufficient"
            else "answer_with_caution_and_disclose_gaps"
        )
    return replace(
        context_pack,
        warnings=warnings,
        knowledge_gaps=gaps,
        recommended_answer_strategy=strategy,
    )
