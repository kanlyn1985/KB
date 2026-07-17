"""Retrieval cards, multi-channel search, fusion, and result contracts."""

from .card_builder import build_retrieval_card, build_retrieval_cards
from .cards import RetrievalCard, card_search_terms
from .engine import RetrievalIndexView, retrieve
from .models import RetrievalCandidate, RetrievalDiagnostics, RetrievalResult

__all__ = [
    "RetrievalCard",
    "RetrievalCandidate",
    "RetrievalDiagnostics",
    "RetrievalIndexView",
    "RetrievalResult",
    "build_retrieval_card",
    "build_retrieval_cards",
    "card_search_terms",
    "retrieve",
]
