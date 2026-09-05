from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence
from urllib import error, parse, request
from uuid import NAMESPACE_URL, uuid5

from agent_kb.retrieval.external_vector import ExternalVectorBackendError, VectorRecord
from agent_kb.retrieval.models import RetrievalCandidate


@dataclass(frozen=True)
class QdrantVectorBackend:
    """Qdrant REST adapter implementing the ExternalVectorBackend contract.

    The target collection must already exist with a vector size compatible
    with the configured embedding provider.
    """

    base_url: str
    collection_name: str
    api_key: str = ""
    timeout_seconds: float = 30.0
    backend_id: str = "qdrant-rest-v1"

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("Qdrant base URL must use http or https")
        if not self.collection_name.strip():
            raise ValueError("Qdrant collection name is required")

    def upsert(self, records: Sequence[VectorRecord]) -> int:
        if not records:
            return 0
        points = []
        for record in records:
            payload = {
                **record.payload,
                "source_type": record.source_type,
                "source_id": record.source_id,
                "object_id": record.object_id,
            }
            points.append(
                {
                    "id": _point_id(record.source_type, record.source_id),
                    "vector": [float(value) for value in record.vector],
                    "payload": payload,
                }
            )
        self._request(
            "PUT",
            f"/collections/{parse.quote(self.collection_name, safe='')}/points?wait=true",
            {"points": points},
        )
        return len(records)

    def search(self, vector: Sequence[float], *, limit: int = 32) -> list[RetrievalCandidate]:
        payload = self._request(
            "POST",
            f"/collections/{parse.quote(self.collection_name, safe='')}/points/query",
            {
                "query": [float(value) for value in vector],
                "limit": max(1, int(limit)),
                "with_payload": True,
                "with_vector": False,
            },
        )
        result = payload.get("result")
        raw_points = result.get("points") if isinstance(result, dict) else result
        if not isinstance(raw_points, list):
            raise ExternalVectorBackendError("Qdrant response does not contain result points")
        candidates: list[RetrievalCandidate] = []
        for rank, point in enumerate(raw_points, start=1):
            if not isinstance(point, dict):
                continue
            point_payload = dict(point.get("payload") or {})
            source_type = str(point_payload.get("source_type") or "")
            source_id = str(point_payload.get("source_id") or "")
            if not source_type or not source_id:
                continue
            candidates.append(
                RetrievalCandidate(
                    candidate_id=f"{source_type}:{source_id}",
                    source_type=source_type,
                    source_id=source_id,
                    channel="qdrant_vector",
                    score=float(point.get("score") or 0.0),
                    rank=rank,
                    matched_terms=[],
                    reasons=["qdrant_vector_similarity"],
                    payload=point_payload,
                )
            )
        return candidates

    def delete(self, source_type: str, source_ids: Sequence[str]) -> int:
        ids = [_point_id(source_type, str(source_id)) for source_id in source_ids]
        if not ids:
            return 0
        self._request(
            "POST",
            f"/collections/{parse.quote(self.collection_name, safe='')}/points/delete?wait=true",
            {"points": ids},
        )
        return len(ids)

    def _request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        outbound = request.Request(
            self.base_url.rstrip("/") + path,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(outbound, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8") or "{}")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ExternalVectorBackendError(f"Qdrant HTTP {exc.code}: {detail[:500]}") from exc
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ExternalVectorBackendError(f"Qdrant request failed: {type(exc).__name__}") from exc
        if not isinstance(result, dict):
            raise ExternalVectorBackendError("Qdrant response must be a JSON object")
        status = str(result.get("status") or "ok").lower()
        if status not in {"ok", "acknowledged", "completed"}:
            raise ExternalVectorBackendError(f"Qdrant operation failed: {status}")
        return result

    def __repr__(self) -> str:
        return (
            "QdrantVectorBackend("
            f"base_url={self.base_url!r}, collection_name={self.collection_name!r}, "
            f"backend_id={self.backend_id!r}, timeout_seconds={self.timeout_seconds})"
        )


def _point_id(source_type: str, source_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"agent-kb:{source_type}:{source_id}"))
