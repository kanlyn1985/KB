"""Unified response format for the combined ontology + legacy system.

This module defines a single dataclass ``UnifiedResponse`` that
normalizes the output of both the ontology system and the legacy
system into a single, UI-friendly structure.

The goal: the frontend (CLI, web, or API consumer) sees ONE
shape, regardless of which system produced the answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TypedAnswer:
    """A structured answer from the ontology system.

    Examples:
      - value="50.0 ms", type="typed_value"
      - value=["ISO 14229-1", "ISO 14229-2"], type="structured_set"
      - value=["DiagnosticSessionControl: 0x10"], type="structured_list"
    """
    value: Any
    type: str  # e.g., "typed_value", "structured_set", "structured_list"


@dataclass
class SourceSnippet:
    """A piece of evidence from the legacy system."""
    text: str
    doc_id: str | None = None
    page_no: int | None = None
    confidence: float | None = None


@dataclass
class UnifiedResponse:
    """The single response format exposed to the UI.

    Both ``combined_query()`` (ontology + legacy) and
    ``answer_query()`` (legacy only) return a dict that is
    converted into this shape.
    """
    # The original user query
    query: str

    # What kind of question this was (parameter, reference, etc.)
    category: str = "free_form"

    # The ontology's structured answer (None if ontology couldn't answer)
    ontology_answer: TypedAnswer | None = None

    # The legacy system's prose answer (None if legacy wasn't queried)
    legacy_answer: str = ""

    # Evidence snippets from the legacy system
    sources: list[SourceSnippet] = field(default_factory=list)

    # Confidence score (0.0-1.0), if available
    confidence: float | None = None

    # Human-readable explanation of how the answer was derived
    explanation: str = ""

    # Any warnings (e.g., "evidence insufficient")
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "category": self.category,
            "ontology_answer": {
                "value": self.ontology_answer.value,
                "type": self.ontology_answer.type,
            } if self.ontology_answer else None,
            "legacy_answer": self.legacy_answer,
            "sources": [
                {
                    "text": s.text,
                    "doc_id": s.doc_id,
                    "page_no": s.page_no,
                    "confidence": s.confidence,
                }
                for s in self.sources
            ],
            "confidence": self.confidence,
            "explanation": self.explanation,
            "warnings": self.warnings,
        }


def from_combined_answer(combined: Any) -> UnifiedResponse:
    """Convert an ``Answer`` (from combined_query.py) into a ``UnifiedResponse``.

    Works with the rewritten Answer dataclass that exposes:
      query, category, structured, display, source, legacy_context, warnings.
    """
    ontology = None
    structured = getattr(combined, "structured", None)
    display = getattr(combined, "display", "") or ""
    if structured is not None:
        ontology = TypedAnswer(
            value=structured,
            type=getattr(combined, "source", "") or "structured",
        )
    elif display:
        ontology = TypedAnswer(value=display, type="text")

    legacy_context = getattr(combined, "legacy_context", "") or ""
    sources: list[SourceSnippet] = []
    if isinstance(legacy_context, dict):
        for item in legacy_context.get("supporting_evidence", []) or []:
            if isinstance(item, dict):
                sources.append(SourceSnippet(
                    text=item.get("snippet", ""),
                    doc_id=item.get("doc_id"),
                    page_no=item.get("page_no"),
                    confidence=item.get("confidence"),
                ))

    return UnifiedResponse(
        query=getattr(combined, "query", ""),
        category=getattr(combined, "category", "free_form"),
        ontology_answer=ontology,
        legacy_answer=legacy_context if isinstance(legacy_context, str) else "",
        sources=sources,
        warnings=getattr(combined, "warnings", []) or [],
        explanation=f"Routed to {getattr(combined, 'category', 'unknown')} via {getattr(combined, 'source', '') or 'no source'}.",
    )


def from_legacy_answer(query: str, legacy: dict[str, Any]) -> UnifiedResponse:
    """Convert a legacy ``answer_query()`` result into a ``UnifiedResponse``.

    Used when the ontology system is unavailable or the query is
    purely free-form.
    """
    sources: list[SourceSnippet] = []
    for item in legacy.get("supporting_evidence", []) or []:
        if isinstance(item, dict):
            sources.append(SourceSnippet(
                text=item.get("snippet", ""),
                doc_id=item.get("doc_id"),
                page_no=item.get("page_no"),
                confidence=item.get("confidence"),
            ))

    confidence = legacy.get("confidence_score")
    if isinstance(confidence, dict):
        confidence = confidence.get("score")

    return UnifiedResponse(
        query=query,
        category=legacy.get("answer_mode", "free_form"),
        legacy_answer=legacy.get("direct_answer", ""),
        sources=sources,
        confidence=confidence,
        warnings=legacy.get("warnings", []),
        explanation="Answered by legacy system (ontology not available).",
    )
