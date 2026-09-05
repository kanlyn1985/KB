from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol, Sequence


class EmbeddingProvider(Protocol):
    """Provider contract used by vector adapters.

    Implementations may call a local model, remote API, or deterministic test
    encoder. Core retrieval depends only on this contract.
    """

    @property
    def provider_id(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class HashEmbeddingProvider:
    """Dependency-free deterministic embedding baseline.

    This is not presented as a learned semantic model. It provides a stable
    vector contract for testing persistence, fusion, and provider replacement.
    """

    dimensions: int = 256
    provider_id: str = "hash-embedding-v1"

    def __post_init__(self) -> None:
        if self.dimensions < 16:
            raise ValueError("dimensions must be at least 16")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = _tokens(text)
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = -1.0 if digest[4] & 1 else 1.0
            weight = 1.0 + min(len(token), 20) / 20.0
            vector[bucket] += sign * weight
        return normalize_vector(vector)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimensions")
    numerator = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def normalize_vector(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(float(value) ** 2 for value in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [float(value) / norm for value in vector]


def _tokens(text: str) -> list[str]:
    normalized = str(text or "").lower().strip()
    latin = re.findall(r"[a-z][a-z0-9_./-]{1,48}|\d+(?:\.\d+)?(?:mvpp|mv|v|a|w|kw|%|ms|s)?", normalized)
    chinese = [char for char in normalized if "\u4e00" <= char <= "\u9fff"]
    bigrams = ["".join(chinese[index : index + 2]) for index in range(max(0, len(chinese) - 1))]
    return latin + chinese + bigrams
