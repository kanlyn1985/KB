"""Retrieval cards, multi-channel search, fusion, reranking, and result contracts."""

from .card_builder import build_retrieval_card, build_retrieval_cards
from .cards import RetrievalCard, card_search_terms
from .engine import RetrievalIndexView, retrieve
from .hybrid import PersistentCandidateProvider, hybrid_retrieve
from .models import RetrievalCandidate, RetrievalDiagnostics, RetrievalResult
from .reranker import DeterministicReranker, Reranker

__all__ = [
    "DeterministicReranker",
    "PersistentCandidateProvider",
    "Reranker",
    "RetrievalCard",
    "RetrievalCandidate",
    "RetrievalDiagnostics",
    "RetrievalIndexView",
    "RetrievalResult",
    "build_retrieval_card",
    "build_retrieval_cards",
    "card_search_terms",
    "hybrid_retrieve",
    "retrieve",
]
