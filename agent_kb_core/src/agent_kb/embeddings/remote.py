from __future__ import annotations

import http.client
import json
import os
from dataclasses import dataclass
from typing import Sequence
from urllib.parse import urlsplit

from .providers import normalize_vector


class EmbeddingProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteJSONEmbeddingProvider:
    """Generic JSON-over-HTTP embedding provider.

    The endpoint must accept `{model, input}` and return either a `data` array
    containing objects with `embedding`, or an `embeddings` array. Secrets are
    read from environment variables and are never included in repr/output.
    """

    endpoint: str
    model: str
    dimensions: int
    api_key: str = ""
    provider_id: str = "remote-json-embedding-v1"
    timeout_seconds: float = 30.0
    batch_size: int = 32

    def __post_init__(self) -> None:
        if not self.endpoint.startswith(("http://", "https://")):
            raise ValueError("embedding endpoint must use http or https")
        if not self.model.strip():
            raise ValueError("embedding model is required")
        if self.dimensions < 1:
            raise ValueError("embedding dimensions must be positive")
        if self.batch_size < 1:
            raise ValueError("embedding batch_size must be positive")

    @classmethod
    def from_environment(
        cls,
        *,
        endpoint_var: str = "AGENT_KB_EMBEDDING_URL",
        model_var: str = "AGENT_KB_EMBEDDING_MODEL",
        dimensions_var: str = "AGENT_KB_EMBEDDING_DIMENSIONS",
        api_key_var: str = "AGENT_KB_EMBEDDING_API_KEY",
        timeout_var: str = "AGENT_KB_EMBEDDING_TIMEOUT",
        batch_size_var: str = "AGENT_KB_EMBEDDING_BATCH_SIZE",
    ) -> RemoteJSONEmbeddingProvider:
        endpoint = os.environ.get(endpoint_var, "").strip()
        model = os.environ.get(model_var, "").strip()
        dimensions = int(os.environ.get(dimensions_var, "0") or 0)
        api_key = os.environ.get(api_key_var, "")
        timeout = float(os.environ.get(timeout_var, "30") or 30)
        batch_size = int(os.environ.get(batch_size_var, "32") or 32)
        provider_id = f"remote-json:{model}:{dimensions}"
        return cls(
            endpoint=endpoint,
            model=model,
            dimensions=dimensions,
            api_key=api_key,
            provider_id=provider_id,
            timeout_seconds=timeout,
            batch_size=batch_size,
        )

    def _endpoint_parts(self) -> tuple[str, int, str, bool]:
        parts = urlsplit(self.endpoint)
        use_tls = parts.scheme == "https"
        host = parts.hostname or ""
        port = parts.port or (443 if use_tls else 80)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        return host, port, path, use_tls

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        values = [str(text) for text in texts]
        if not values:
            return []
        # 批量分片：真实模型服务无法一次吃下数万条，按 batch_size 分批请求后拼接。
        # 关键：复用一条持久 HTTP 连接（keep-alive），避免每请求重新建连（SSH 隧道/DERP 下建连开销巨大）。
        host, port, path, use_tls = self._endpoint_parts()
        conn_cls = http.client.HTTPSConnection if use_tls else http.client.HTTPConnection
        vectors: list[list[float]] = []
        conn = conn_cls(host, port, timeout=self.timeout_seconds)
        try:
            for start in range(0, len(values), self.batch_size):
                vectors.extend(self._embed_batch(conn, path, values[start : start + self.batch_size]))
        finally:
            conn.close()
        return vectors

    def _embed_batch(self, conn, path: str, values: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": values}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            conn.request("POST", path, body=body, headers=headers)
            response = conn.getresponse()
            if response.status != 200:
                raise EmbeddingProviderError(f"remote embedding HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
        except EmbeddingProviderError:
            raise
        except (OSError, http.client.HTTPException, TimeoutError, json.JSONDecodeError) as exc:
            raise EmbeddingProviderError(f"remote embedding request failed: {type(exc).__name__}") from exc
        vectors = _parse_vectors(payload)
        if len(vectors) != len(values):
            raise EmbeddingProviderError("embedding response count does not match input count")
        normalized: list[list[float]] = []
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise EmbeddingProviderError(
                    f"embedding dimension mismatch: expected {self.dimensions}, received {len(vector)}"
                )
            normalized.append(normalize_vector(vector))
        return normalized

    def __repr__(self) -> str:
        return (
            "RemoteJSONEmbeddingProvider("
            f"endpoint={self.endpoint!r}, model={self.model!r}, dimensions={self.dimensions}, "
            f"provider_id={self.provider_id!r}, timeout_seconds={self.timeout_seconds})"
        )


def _parse_vectors(payload: object) -> list[list[float]]:
    if not isinstance(payload, dict):
        raise EmbeddingProviderError("embedding response must be a JSON object")
    raw = payload.get("embeddings")
    if raw is None and isinstance(payload.get("data"), list):
        raw = [item.get("embedding") for item in payload["data"] if isinstance(item, dict)]
    if not isinstance(raw, list):
        raise EmbeddingProviderError("embedding response does not contain vectors")
    vectors: list[list[float]] = []
    for item in raw:
        if not isinstance(item, list):
            raise EmbeddingProviderError("embedding vector must be an array")
        vectors.append([float(value) for value in item])
    return vectors
