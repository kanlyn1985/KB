from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_kb.context.builder import build_context_pack
from agent_kb.context.context_pack import AgentContextPack
from agent_kb.context.evidence_judge import EvidenceJudgement, judge_context_pack
from agent_kb.core.compiler import compile_text_document
from agent_kb.domains.schema import DomainPack
from agent_kb.embeddings import EmbeddingProvider, HashEmbeddingProvider
from agent_kb.graph import DeterministicRelationExtractor, RelationExtractor, SQLiteGraphStore
from agent_kb.pipeline.document_context import CompiledKnowledgeIndex, build_compiled_knowledge_index
from agent_kb.query.query_frame import QueryFrame
from agent_kb.query.understanding import UnderstandingOptions, understand_query
from agent_kb.retrieval.external_vector import (
    ExternalVectorBackend,
    ExternalVectorCandidateProvider,
)
from agent_kb.retrieval.hybrid import hybrid_retrieve
from agent_kb.retrieval.models import RetrievalResult
from agent_kb.retrieval.production import ProductionCandidateProvider
from agent_kb.retrieval.reranker import Reranker
from agent_kb.retrieval.vector import SQLiteVectorIndex, VectorIndexSummary
from agent_kb.retrieval.vector_records import build_vector_records
from agent_kb.storage.lifecycle import DocumentLifecycleRecord, DocumentLifecycleStore, DocumentVersion
from agent_kb.storage.migrations import SchemaMigrator
from agent_kb.storage.sqlite_store import PersistentIndexView, SQLiteKnowledgeStore


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ProductionIndexResult:
    compiled_index: CompiledKnowledgeIndex
    store_summary: dict[str, int]
    vector_summary: VectorIndexSummary
    document_version: DocumentVersion
    graph_edge_count: int
    external_vector_count: int
    relation_extractor_id: str
    schema_version: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "compiled_index": self.compiled_index.to_dict(),
            "store_summary": dict(self.store_summary),
            "vector_summary": self.vector_summary.to_dict(),
            "document_version": self.document_version.to_dict(),
            "graph_edge_count": self.graph_edge_count,
            "external_vector_count": self.external_vector_count,
            "relation_extractor_id": self.relation_extractor_id,
            "schema_version": self.schema_version,
        }

    @property
    def summary(self) -> dict[str, Any]:
        return {
            **self.compiled_index.summary,
            **self.store_summary,
            "vectors": self.vector_summary.vector_count,
            "external_vectors": self.external_vector_count,
            "graph_edges_materialized": self.graph_edge_count,
            "relation_extractor_id": self.relation_extractor_id,
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
    external_vector_backend: ExternalVectorBackend | None = None,
    relation_extractor: RelationExtractor | None = None,
    tenant_id: str = "default",
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
    provider = embedding_provider or HashEmbeddingProvider()
    extractor = relation_extractor or DeterministicRelationExtractor()
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
        vector_index = SQLiteVectorIndex(store.connection, provider=provider)
        vector_summary = vector_index.index_view(index)
        external_vector_count = 0
        if external_vector_backend is not None:
            external_vector_count = external_vector_backend.upsert(build_vector_records(index, provider))
        graph = SQLiteGraphStore(store.connection)
        extracted_edges = extractor.extract(index)
        graph_edge_count = graph.upsert_relations(extracted_edges)
        _record_graph_extraction(
            store.connection,
            tenant_id=tenant_id,
            extractor_id=extractor.extractor_id,
            candidate_count=len(extracted_edges),
            accepted_count=graph_edge_count,
        )
        schema_version = migrator.current_version()
    return ProductionIndexResult(
        compiled_index=index,
        store_summary=store_summary,
        vector_summary=vector_summary,
        document_version=document_version,
        graph_edge_count=graph_edge_count,
        external_vector_count=external_vector_count,
        relation_extractor_id=extractor.extractor_id,
        schema_version=schema_version,
    )


def query_production_store(
    query: str,
    *,
    db_path: str | Path,
    domain_pack: DomainPack | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    external_vector_backend: ExternalVectorBackend | None = None,
    understanding_options: UnderstandingOptions | None = None,
    reranker: Reranker | None = None,
    retrieval_top_k: int = 12,
) -> ProductionQueryResult:
    frame = understand_query(query, domain_pack=domain_pack, options=understanding_options)
    provider = embedding_provider or HashEmbeddingProvider()
    with SQLiteKnowledgeStore(db_path) as store:
        migrator = SchemaMigrator(store.connection)
        migrator.migrate()
        index = store.load_index_view()
        local_vector = SQLiteVectorIndex(store.connection, provider=provider)
        vector_provider = (
            ExternalVectorCandidateProvider(backend=external_vector_backend, embedding_provider=provider)
            if external_vector_backend is not None
            else local_vector
        )
        graph = SQLiteGraphStore(store.connection)
        candidate_provider = ProductionCandidateProvider(lexical=store, vector=vector_provider, graph=graph)
        retrieval_result = hybrid_retrieve(
            frame,
            index,
            persistent_provider=candidate_provider,
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


def _record_graph_extraction(
    connection,
    *,
    tenant_id: str,
    extractor_id: str,
    candidate_count: int,
    accepted_count: int,
) -> str:
    run_id = f"gxr_{uuid4().hex}"
    metrics = {
        "acceptance_rate": accepted_count / candidate_count if candidate_count else 1.0,
    }
    with connection:
        connection.execute(
            """
            INSERT INTO graph_extraction_runs(
                run_id, tenant_id, extractor_id, candidate_count,
                accepted_count, metrics_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                tenant_id,
                extractor_id,
                candidate_count,
                accepted_count,
                json.dumps(metrics, ensure_ascii=False, sort_keys=True),
                _utc_now_iso(),
            ),
        )
    return run_id


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
