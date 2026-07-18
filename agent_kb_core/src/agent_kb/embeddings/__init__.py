"""Embedding-provider contracts and local/remote implementations."""

from .providers import EmbeddingProvider, HashEmbeddingProvider, cosine_similarity, normalize_vector
from .remote import EmbeddingProviderError, RemoteJSONEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "HashEmbeddingProvider",
    "RemoteJSONEmbeddingProvider",
    "cosine_similarity",
    "normalize_vector",
]
