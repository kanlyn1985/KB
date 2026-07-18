from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Sequence
from urllib import error, request

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

    def __post_init__(self) -> None:
        if not self.endpoint.startswith(("http://", "https://")):
            raise ValueError("embedding endpoint must use http or https")
        if not self.model.strip():
            raise ValueError("embedding model is required")
        if self.dimensions < 1:
            raise ValueError("embedding dimensions must be positive")

    @classmethod
    def from_environment(
        cls,
        *,
        endpoint_var: str = "AGENT_KB_EMBEDDING_URL",
        model_var: str = "AGENT_KB_EMBEDDING_MODEL",
        dimensions_var: str = "AGENT_KB_EMBEDDING_DIMENSIONS",
        api_key_var: str = "AGENT_KB_EMBEDDING_API_KEY",
        timeout_var: str = "AGENT_KB_EMBEDDING_TIMEOUT",
    ) -> RemoteJSONEmbeddingProvider:
        endpoint = os.environ.get(endpoint_var, "").strip()
        model = os.environ.get(model_var, "").strip()
        dimensions = int(os.environ.get(dimensions_var, "0") or 0)
        api_key = os.environ.get(api_key_var, "")
        timeout = float(os.environ.get(timeout_var, "30") or 30)
        provider_id = f"remote-json:{model}:{dimensions}"
        return cls(
            endpoint=endpoint,
            model=model,
            dimensions=dimensions,
            api_key=api_key,
            provider_id=provider_id,
            timeout_seconds=timeout,
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        values = [str(text) for text in texts]
        if not values:
            return []
        body = json.dumps({"model": self.model, "input": values}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        outbound = request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(outbound, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
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
