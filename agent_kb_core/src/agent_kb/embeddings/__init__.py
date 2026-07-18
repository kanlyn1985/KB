"""Embedding-provider contracts and deterministic baseline implementation."""

from .providers import EmbeddingProvider, HashEmbeddingProvider, cosine_similarity, normalize_vector

__all__ = [
    "EmbeddingProvider",
    "HashEmbeddingProvider",
    "cosine_similarity",
    "normalize_vector",
]
