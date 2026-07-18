from __future__ import annotations

from typing import Any

from agent_kb.embeddings import EmbeddingProvider
from agent_kb.retrieval.external_vector import VectorRecord


def build_vector_records(index: Any, provider: EmbeddingProvider) -> list[VectorRecord]:
    surfaces: list[tuple[str, str, str | None, str, dict[str, Any]]] = []
    for item in index.object_projections:
        surfaces.append(
            (
                "object",
                item.object_id,
                item.object_id,
                " ".join([item.object_id, item.canonical_name, item.description, *item.aliases]),
                {"object_id": item.object_id, "object_type": item.object_type},
            )
        )
    for item in index.retrieval_cards:
        surfaces.append(
            (
                "card",
                item.card_id,
                item.object_id,
                " ".join([item.title, item.search_text, *item.aliases, *item.answer_shapes]),
                {
                    "object_id": item.object_id,
                    "evidence_ids": list(item.evidence_ids),
                    "answer_shapes": list(item.answer_shapes),
                },
            )
        )
    for item in index.context_facts:
        surfaces.append(
            (
                "fact",
                item.fact_id,
                item.subject,
                " ".join(
                    [
                        item.subject or "",
                        item.fact_type,
                        item.predicate,
                        str(item.object_value),
                        " ".join(f"{key} {value}" for key, value in item.qualifiers.items()),
                    ]
                ),
                {
                    "subject": item.subject,
                    "fact_type": item.fact_type,
                    "evidence_ids": list(item.evidence_ids),
                },
            )
        )
    for item in index.context_evidence:
        surfaces.append(
            (
                "evidence",
                item.evidence_id,
                None,
                item.snippet,
                {"document_id": item.document_id, "page_no": item.page_no},
            )
        )
    vectors = provider.embed([surface[3] for surface in surfaces])
    return [
        VectorRecord(
            source_type=surface[0],
            source_id=surface[1],
            object_id=surface[2],
            vector=vector,
            payload=surface[4],
        )
        for surface, vector in zip(surfaces, vectors, strict=True)
    ]
