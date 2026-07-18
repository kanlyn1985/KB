from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent_kb.embeddings import EmbeddingProvider, HashEmbeddingProvider, cosine_similarity
from agent_kb.query.query_frame import QueryFrame
from agent_kb.retrieval.models import RetrievalCandidate
from agent_kb.storage.migrations import SchemaMigrator


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class VectorIndexSummary:
    provider_id: str
    dimensions: int
    vector_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "dimensions": self.dimensions,
            "vector_count": self.vector_count,
        }


class SQLiteVectorIndex:
    """SQLite-backed vector adapter with pluggable embedding provider.

    Similarity is computed in Python to keep Core dependency-free. Production
    deployments can replace this adapter with pgvector, Qdrant, Milvus, FAISS,
    or another provider while preserving the candidate contract.
    """

    def __init__(self, connection: sqlite3.Connection, provider: EmbeddingProvider | None = None) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self.provider = provider or HashEmbeddingProvider()
        SchemaMigrator(connection).migrate()

    def index_view(self, index: Any) -> VectorIndexSummary:
        records: list[tuple[str, str, str | None, str, dict[str, Any]]] = []
        for item in index.object_projections:
            records.append(
                (
                    "object",
                    item.object_id,
                    item.object_id,
                    " ".join([item.object_id, item.canonical_name, item.description, *item.aliases]),
                    {"object_id": item.object_id, "object_type": item.object_type},
                )
            )
        for item in index.retrieval_cards:
            records.append(
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
            records.append(
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
            records.append(
                (
                    "evidence",
                    item.evidence_id,
                    None,
                    item.snippet,
                    {"document_id": item.document_id, "page_no": item.page_no},
                )
            )

        texts = [record[3] for record in records]
        vectors = self.provider.embed(texts)
        now = _utc_now_iso()
        with self.connection:
            for record, vector in zip(records, vectors, strict=True):
                source_type, source_id, object_id, text, payload = record
                self.connection.execute(
                    """
                    INSERT INTO embedding_vectors(
                        source_type, source_id, object_id, provider_id, dimensions,
                        vector_json, text_hash, payload_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_type, source_id, provider_id) DO UPDATE SET
                        object_id=excluded.object_id,
                        dimensions=excluded.dimensions,
                        vector_json=excluded.vector_json,
                        text_hash=excluded.text_hash,
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        source_type,
                        source_id,
                        object_id,
                        self.provider.provider_id,
                        self.provider.dimensions,
                        _json(vector),
                        hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        _json(payload),
                        now,
                    ),
                )
        return self.summary()

    def search(self, query_frame: QueryFrame, *, limit: int = 32) -> list[RetrievalCandidate]:
        query_text = " ".join(
            value
            for value in [
                query_frame.normalized_query,
                query_frame.target_topic,
                *query_frame.must_terms,
                *query_frame.aliases,
                *query_frame.should_terms,
            ]
            if value
        )
        query_vector = self.provider.embed([query_text])[0]
        candidates: list[RetrievalCandidate] = []
        rows = self.connection.execute(
            "SELECT * FROM embedding_vectors WHERE provider_id = ? AND dimensions = ?",
            (self.provider.provider_id, self.provider.dimensions),
        )
        for row in rows:
            vector = json.loads(row["vector_json"])
            similarity = cosine_similarity(query_vector, vector)
            if similarity <= 0.0:
                continue
            payload = json.loads(row["payload_json"] or "{}")
            if row["object_id"] and "object_id" not in payload and "subject" not in payload:
                payload["object_id"] = row["object_id"]
            candidates.append(
                RetrievalCandidate(
                    candidate_id=f"{row['source_type']}:{row['source_id']}",
                    source_type=row["source_type"],
                    source_id=row["source_id"],
                    channel="vector",
                    score=float(similarity),
                    matched_terms=[],
                    reasons=["vector_similarity"],
                    payload=payload,
                )
            )
        candidates.sort(key=lambda item: (item.score, item.source_id), reverse=True)
        return candidates[: max(1, limit)]

    def delete_source(self, source_type: str, source_id: str) -> int:
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM embedding_vectors WHERE source_type = ? AND source_id = ? AND provider_id = ?",
                (source_type, source_id, self.provider.provider_id),
            )
        return int(cursor.rowcount)

    def summary(self) -> VectorIndexSummary:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM embedding_vectors WHERE provider_id = ?",
            (self.provider.provider_id,),
        ).fetchone()
        return VectorIndexSummary(
            provider_id=self.provider.provider_id,
            dimensions=self.provider.dimensions,
            vector_count=int(row[0] or 0),
        )
