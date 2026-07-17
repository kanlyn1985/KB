from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agent_kb.context.builder import build_context_pack
from agent_kb.context.context_pack import AgentContextPack, ContextEvidence, ContextFact
from agent_kb.core.compiler import KnowledgeCompilation, compile_text_document
from agent_kb.core.evidence import EvidenceBlock
from agent_kb.core.facts import Fact
from agent_kb.domains.schema import DomainPack
from agent_kb.projection.models import ObjectProjection
from agent_kb.projection.projector import build_terminology_projections, project_evidence_candidate
from agent_kb.query.query_frame import QueryFrame
from agent_kb.query.understanding import UnderstandingOptions, understand_query
from agent_kb.retrieval.card_builder import build_retrieval_cards
from agent_kb.retrieval.cards import RetrievalCard


@dataclass(frozen=True)
class CompiledKnowledgeIndex:
    """Reusable in-memory index built from one compilation result.

    The index is intentionally light-weight for Phase 3. It is not a database,
    vector store, or final search engine. It materializes the normalized objects
    required by the Agent Context Pack builder:

    - context facts
    - context evidence
    - object projections
    - retrieval cards
    """

    compilation: KnowledgeCompilation
    context_facts: list[ContextFact]
    context_evidence: list[ContextEvidence]
    object_projections: list[ObjectProjection]
    retrieval_cards: list[RetrievalCard]

    def to_dict(self) -> dict[str, Any]:
        return {
            "compilation": self.compilation.to_dict(),
            "context_facts": [item.to_dict() for item in self.context_facts],
            "context_evidence": [item.to_dict() for item in self.context_evidence],
            "object_projections": [item.to_dict() for item in self.object_projections],
            "retrieval_cards": [item.to_dict() for item in self.retrieval_cards],
        }

    @property
    def summary(self) -> dict[str, int]:
        payload = dict(self.compilation.summary)
        payload.update(
            {
                "context_facts": len(self.context_facts),
                "context_evidence": len(self.context_evidence),
                "object_projections": len(self.object_projections),
                "retrieval_cards": len(self.retrieval_cards),
            }
        )
        return payload


@dataclass(frozen=True)
class DocumentContextResult:
    """End-to-end output for one document and one user query."""

    query_frame: QueryFrame
    compiled_index: CompiledKnowledgeIndex
    context_pack: AgentContextPack

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_frame": self.query_frame.to_dict(),
            "compiled_index": self.compiled_index.to_dict(),
            "context_pack": self.context_pack.to_dict(),
        }

    @property
    def summary(self) -> dict[str, int]:
        payload = dict(self.compiled_index.summary)
        payload.update(
            {
                "selected_objects": len(self.context_pack.target_objects),
                "selected_cards": len(self.context_pack.retrieval_cards),
                "selected_facts": len(self.context_pack.facts),
                "selected_evidence": len(self.context_pack.evidence),
                "hidden_context_items": len(self.context_pack.hidden_context),
                "warnings": len(self.context_pack.warnings),
                "knowledge_gaps": len(self.context_pack.knowledge_gaps),
            }
        )
        return payload


def build_compiled_knowledge_index(
    compilation: KnowledgeCompilation,
    *,
    domain_pack: DomainPack | None = None,
) -> CompiledKnowledgeIndex:
    """Convert a generic compilation into context-ready retrieval surfaces."""

    context_facts = [_to_context_fact(fact) for fact in compilation.facts]
    context_evidence = [_to_context_evidence(block) for block in compilation.evidence_blocks]
    object_projections = _build_object_projections(
        compilation=compilation,
        context_facts=context_facts,
        domain_pack=domain_pack,
    )
    retrieval_cards = build_retrieval_cards(
        object_projections,
        facts=context_facts,
        evidence=context_evidence,
    )
    return CompiledKnowledgeIndex(
        compilation=compilation,
        context_facts=context_facts,
        context_evidence=context_evidence,
        object_projections=object_projections,
        retrieval_cards=retrieval_cards,
    )


def build_context_pack_from_compilation(
    query: str,
    compilation: KnowledgeCompilation,
    *,
    domain_pack: DomainPack | None = None,
    understanding_options: UnderstandingOptions | None = None,
) -> DocumentContextResult:
    """Build an Agent Context Pack from a precompiled document."""

    frame = understand_query(query, domain_pack=domain_pack, options=understanding_options)
    compiled_index = build_compiled_knowledge_index(compilation, domain_pack=domain_pack)
    context_pack = build_context_pack(
        query_frame=frame,
        domain_pack=domain_pack,
        objects=compiled_index.object_projections,
        retrieval_cards=compiled_index.retrieval_cards,
        facts=compiled_index.context_facts,
        evidence=compiled_index.context_evidence,
    )
    return DocumentContextResult(
        query_frame=frame,
        compiled_index=compiled_index,
        context_pack=context_pack,
    )


def compile_text_to_context_pack(
    text: str,
    *,
    query: str,
    title: str,
    domain_pack: DomainPack | None = None,
    source_type: str = "text",
    source_uri: str | None = None,
    metadata: dict[str, Any] | None = None,
    max_evidence_chars: int = 900,
    understanding_options: UnderstandingOptions | None = None,
) -> DocumentContextResult:
    """Compile text and immediately produce an Agent Context Pack for a query."""

    compilation = compile_text_document(
        text,
        title=title,
        domain_pack=domain_pack,
        source_type=source_type,
        source_uri=source_uri,
        metadata=metadata,
        max_evidence_chars=max_evidence_chars,
    )
    return build_context_pack_from_compilation(
        query,
        compilation,
        domain_pack=domain_pack,
        understanding_options=understanding_options,
    )


def _to_context_fact(fact: Fact) -> ContextFact:
    return ContextFact(
        fact_id=fact.fact_id,
        fact_type=fact.fact_type,
        subject=fact.subject,
        predicate=fact.predicate,
        object_value=fact.object_value,
        qualifiers=dict(fact.qualifiers),
        evidence_ids=list(fact.evidence_ids),
        confidence=fact.confidence,
    )


def _to_context_evidence(block: EvidenceBlock) -> ContextEvidence:
    return ContextEvidence(
        evidence_id=block.evidence_id,
        document_id=block.document_id,
        page_no=block.page_no,
        snippet=block.normalized_text,
        confidence=block.confidence,
    )


def _build_object_projections(
    *,
    compilation: KnowledgeCompilation,
    context_facts: list[ContextFact],
    domain_pack: DomainPack | None,
) -> list[ObjectProjection]:
    if not domain_pack:
        return _generic_projections(compilation, context_facts)

    projections = build_terminology_projections(domain_pack)
    by_id = {projection.object_id: projection for projection in projections}

    for fact in context_facts:
        subject = str(fact.subject or "").strip()
        if not subject or subject in by_id:
            continue
        evidence_block = _evidence_by_id(compilation.evidence_blocks, fact.evidence_ids[0] if fact.evidence_ids else "")
        projection = project_evidence_candidate(
            domain_pack=domain_pack,
            object_id=subject,
            object_type="Concept",
            canonical_name=subject,
            evidence_id=evidence_block.evidence_id if evidence_block else (fact.evidence_ids[0] if fact.evidence_ids else ""),
            document_id=evidence_block.document_id if evidence_block else compilation.document.document_id,
            page_no=evidence_block.page_no if evidence_block else None,
            properties={
                "source": "compiled_fact.subject",
                "fact_type": fact.fact_type,
                "predicate": fact.predicate,
            },
            confidence=min(max(fact.confidence, 0.35), 0.75),
        )
        projections.append(projection)
        by_id[projection.object_id] = projection
    return projections


def _generic_projections(compilation: KnowledgeCompilation, facts: list[ContextFact]) -> list[ObjectProjection]:
    projections: list[ObjectProjection] = []
    seen: set[str] = set()
    pseudo_domain = "generic"
    for fact in facts:
        subject = str(fact.subject or "").strip()
        if not subject or subject in seen:
            continue
        seen.add(subject)
        evidence_block = _evidence_by_id(compilation.evidence_blocks, fact.evidence_ids[0] if fact.evidence_ids else "")
        projections.append(
            ObjectProjection(
                object_id=_safe_object_id(subject),
                domain=pseudo_domain,
                object_type="Concept",
                canonical_name=subject,
                description="Generic concept projected from compiled facts.",
                aliases=[subject],
                properties={
                    "source": "compiled_fact.subject",
                    "fact_type": fact.fact_type,
                },
                evidence_refs=[],
                confidence=min(max(fact.confidence, 0.3), 0.7),
                status="candidate",
            )
        )
    return projections


def _evidence_by_id(blocks: list[EvidenceBlock], evidence_id: str) -> EvidenceBlock | None:
    for block in blocks:
        if block.evidence_id == evidence_id:
            return block
    return None


def _safe_object_id(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned[:64] or "generic_concept"
