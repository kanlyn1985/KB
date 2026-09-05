"""Retrieval cards, multi-channel search, vector/graph fusion, and reranking."""

from .card_builder import build_retrieval_card, build_retrieval_cards
from .cards import RetrievalCard, card_search_terms
from .engine import RetrievalIndexView, retrieve
from .external_vector import (
    ExternalVectorBackend,
    ExternalVectorBackendError,
    ExternalVectorCandidateProvider,
    HTTPVectorBackend,
    InMemoryVectorBackend,
    VectorRecord,
)
from .hybrid import PersistentCandidateProvider, hybrid_retrieve
from .models import RetrievalCandidate, RetrievalDiagnostics, RetrievalResult
from .production import CandidateProvider, ProductionCandidateProvider
from .qdrant import QdrantVectorBackend
from .reranker import DeterministicReranker, Reranker
from .vector import SQLiteVectorIndex, VectorIndexSummary

__all__ = [
    "CandidateProvider",
    "DeterministicReranker",
    "ExternalVectorBackend",
    "ExternalVectorBackendError",
    "ExternalVectorCandidateProvider",
    "HTTPVectorBackend",
    "InMemoryVectorBackend",
    "PersistentCandidateProvider",
    "ProductionCandidateProvider",
    "QdrantVectorBackend",
    "Reranker",
    "RetrievalCard",
    "RetrievalCandidate",
    "RetrievalDiagnostics",
    "RetrievalIndexView",
    "RetrievalResult",
    "SQLiteVectorIndex",
    "VectorIndexSummary",
    "VectorRecord",
    "build_retrieval_card",
    "build_retrieval_cards",
    "card_search_terms",
    "hybrid_retrieve",
    "retrieve",
]
