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
        # (provider_id, row_count) -> 归一化矩阵+元数据 的进程级缓存：
        # 纯 Python 逐行 json.loads + 余弦在 31557x512 下需 ~30s/查询，
        # numpy 矩阵乘法后降到毫秒级。写操作后置 _invalidate_cache()。

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
        fast = self._matrix_cache_get()
        if fast is not None:
            return self._search_numpy(query_vector, limit, *fast)
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

    # ---- numpy 快速路径（无可选依赖时自动回退上面的纯 Python 路径） ----

    _NUMPY_MISSING = False
    _CLASS_MATRIX_CACHE: dict[tuple[str, str, int, int], tuple] = {}

    def _matrix_cache_get(self):
        """返回 (meta, matrix_norm) 或 None（numpy 不可用/未初始化/库已变更）。"""
        import os
        if os.environ.get("AGENT_KB_VECTOR_NO_NUMPY"):
            return None
        if self._NUMPY_MISSING:
            return None
        key = (self.provider.provider_id, self.provider.dimensions)
        row = self.connection.execute(
            "SELECT COUNT(*) FROM embedding_vectors WHERE provider_id = ? AND dimensions = ?",
            key,
        ).fetchone()
        db_path = ""
        try:
            for db_row in self.connection.execute("PRAGMA database_list"):
                if db_row[1] == "main":
                    db_path = str(db_row[2] or ":memory:")
                    break
        except Exception:
            pass
        cache_key = (db_path, key[0], key[1], int(row[0] if row else 0))
        cached = type(self)._CLASS_MATRIX_CACHE.get(cache_key)
        if cached is not None:
            return cached
        try:
            import numpy as np
        except Exception:
            type(self)._NUMPY_MISSING = True
            return None
        rows = self.connection.execute(
            "SELECT source_type, source_id, object_id, payload_json, vector_json "
            "FROM embedding_vectors WHERE provider_id = ? AND dimensions = ?",
            (key[0], key[1]),
        ).fetchall()
        if not rows:
            return None
        meta = []
        vectors = []
        for r in rows:
            meta.append((
                r["source_type"], r["source_id"], r["object_id"],
                json.loads(r["payload_json"] or "{}"),
            ))
            vectors.append(json.loads(r["vector_json"]))
        mat = np.asarray(vectors, dtype=np.float32)
        mat = mat / np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-12)
        type(self)._CLASS_MATRIX_CACHE[cache_key] = (meta, mat)
        return (meta, mat)

    def _search_numpy(self, query_vector, limit: int, meta, mat):
        import numpy as np
        q = np.asarray(query_vector, dtype=np.float32)
        norm = float(np.linalg.norm(q))
        if norm <= 0:
            return []
        q = q / norm
        sims = mat @ q
        take = int(min(max(1, limit) * 4, len(meta)))
        idx = np.argsort(-sims)[:take]
        candidates: list[RetrievalCandidate] = []
        for i in idx:
            score = float(sims[i])
            if score <= 0.0:
                break
            st, sid, oid, payload = meta[i]
            p = dict(payload)
            if oid and "object_id" not in p and "subject" not in p:
                p["object_id"] = oid
            candidates.append(
                RetrievalCandidate(
                    candidate_id=f"{st}:{sid}",
                    source_type=st,
                    source_id=sid,
                    channel="vector",
                    score=score,
                    matched_terms=[],
                    reasons=["vector_similarity"],
                    payload=p,
                )
            )
        return candidates[: max(1, limit)]

    def _invalidate_cache(self) -> None:
        try:
            db_path = ""
            for db_row in self.connection.execute("PRAGMA database_list"):
                if db_row[1] == "main":
                    db_path = str(db_row[2] or ":memory:")
                    break
            prefix = (db_path, self.provider.provider_id, self.provider.dimensions)
            for k in [k for k in type(self)._CLASS_MATRIX_CACHE if k[:3] == prefix]:
                type(self)._CLASS_MATRIX_CACHE.pop(k, None)
        except Exception:
            type(self)._CLASS_MATRIX_CACHE.clear()

    def delete_source(self, source_type: str, source_id: str) -> int:
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM embedding_vectors WHERE source_type = ? AND source_id = ? AND provider_id = ?",
                (source_type, source_id, self.provider.provider_id),
            )
        self._invalidate_cache()
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
