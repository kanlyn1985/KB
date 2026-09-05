from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Protocol, Sequence
from urllib import error, request

from agent_kb.query.query_frame import QueryFrame
from agent_kb.retrieval.models import RetrievalCandidate


@dataclass(frozen=True)
class VectorRecord:
    source_type: str
    source_id: str
    object_id: str | None
    vector: list[float]
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExternalVectorBackend(Protocol):
    backend_id: str

    def upsert(self, records: Sequence[VectorRecord]) -> int: ...

    def search(self, vector: Sequence[float], *, limit: int = 32) -> list[RetrievalCandidate]: ...

    def delete(self, source_type: str, source_ids: Sequence[str]) -> int: ...


class ExternalVectorBackendError(RuntimeError):
    pass


@dataclass(frozen=True)
class HTTPVectorBackend:
    """Generic external vector backend using a small JSON contract.

    Endpoint contract:
    - POST `{base_url}/upsert` with `{records:[...]}`
    - POST `{base_url}/search` with `{vector:[...], limit:n}`
    - POST `{base_url}/delete` with `{source_type, source_ids}`
    """

    base_url: str
    api_key: str = ""
    backend_id: str = "http-vector-v1"
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("vector backend URL must use http or https")

    def upsert(self, records: Sequence[VectorRecord]) -> int:
        payload = self._post("/upsert", {"records": [record.to_dict() for record in records]})
        return int(payload.get("upserted") or len(records))

    def search(self, vector: Sequence[float], *, limit: int = 32) -> list[RetrievalCandidate]:
        payload = self._post("/search", {"vector": [float(value) for value in vector], "limit": max(1, int(limit))})
        raw = payload.get("candidates")
        if not isinstance(raw, list):
            raise ExternalVectorBackendError("vector search response is missing candidates")
        candidates: list[RetrievalCandidate] = []
        for rank, item in enumerate(raw, start=1):
            if not isinstance(item, dict):
                continue
            source_type = str(item.get("source_type") or "")
            source_id = str(item.get("source_id") or "")
            if not source_type or not source_id:
                continue
            candidates.append(
                RetrievalCandidate(
                    candidate_id=f"{source_type}:{source_id}",
                    source_type=source_type,
                    source_id=source_id,
                    channel="external_vector",
                    score=float(item.get("score") or 0.0),
                    rank=rank,
                    matched_terms=[],
                    reasons=["external_vector_similarity"],
                    payload=dict(item.get("payload") or {}),
                )
            )
        return candidates

    def delete(self, source_type: str, source_ids: Sequence[str]) -> int:
        payload = self._post(
            "/delete",
            {"source_type": source_type, "source_ids": [str(value) for value in source_ids]},
        )
        return int(payload.get("deleted") or 0)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        outbound = request.Request(
            self.base_url.rstrip("/") + path,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(outbound, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ExternalVectorBackendError(f"external vector request failed: {type(exc).__name__}") from exc
        if not isinstance(result, dict):
            raise ExternalVectorBackendError("external vector response must be a JSON object")
        return result

    def __repr__(self) -> str:
        return (
            "HTTPVectorBackend("
            f"base_url={self.base_url!r}, backend_id={self.backend_id!r}, "
            f"timeout_seconds={self.timeout_seconds})"
        )


@dataclass
class InMemoryVectorBackend:
    """Test and embedded backend implementing the external backend contract."""

    backend_id: str = "memory-vector-v1"

    def __post_init__(self) -> None:
        self._records: dict[tuple[str, str], VectorRecord] = {}

    def upsert(self, records: Sequence[VectorRecord]) -> int:
        for record in records:
            self._records[(record.source_type, record.source_id)] = record
        return len(records)

    def search(self, vector: Sequence[float], *, limit: int = 32) -> list[RetrievalCandidate]:
        from agent_kb.embeddings import cosine_similarity

        candidates: list[RetrievalCandidate] = []
        for record in self._records.values():
            score = cosine_similarity(vector, record.vector)
            if score <= 0.0:
                continue
            payload = dict(record.payload)
            if record.object_id and "object_id" not in payload and "subject" not in payload:
                payload["object_id"] = record.object_id
            candidates.append(
                RetrievalCandidate(
                    candidate_id=f"{record.source_type}:{record.source_id}",
                    source_type=record.source_type,
                    source_id=record.source_id,
                    channel="external_vector",
                    score=score,
                    matched_terms=[],
                    reasons=["external_vector_similarity"],
                    payload=payload,
                )
            )
        candidates.sort(key=lambda item: (item.score, item.source_id), reverse=True)
        return candidates[: max(1, int(limit))]

    def delete(self, source_type: str, source_ids: Sequence[str]) -> int:
        deleted = 0
        for source_id in source_ids:
            deleted += int(self._records.pop((source_type, str(source_id)), None) is not None)
        return deleted


class ExternalVectorCandidateProvider:
    def __init__(self, *, backend: ExternalVectorBackend, embedding_provider: Any) -> None:
        self.backend = backend
        self.embedding_provider = embedding_provider

    def search(self, query_frame: QueryFrame, *, limit: int = 32) -> list[RetrievalCandidate]:
        text = " ".join(
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
        vector = self.embedding_provider.embed([text])[0]
        return self.backend.search(vector, limit=limit)
