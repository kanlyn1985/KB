from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievalCard:
    """Object-centered retrieval unit.

    A retrieval card is not a source chunk. It is a recall-optimized object card
    that aggregates aliases, evidence, relations, and answer shapes for one
    domain object or one important semantic unit.
    """

    card_id: str
    domain: str
    object_id: str | None
    card_type: str
    title: str
    search_text: str
    aliases: list[str] = field(default_factory=list)
    related_object_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    answer_shapes: list[str] = field(default_factory=list)
    structured_payload: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def card_search_terms(card: RetrievalCard) -> list[str]:
    """Return deduplicated terms useful for keyword/semantic indexing."""

    terms: list[str] = []
    for value in [card.title, card.search_text, *card.aliases, *card.answer_shapes]:
        text = str(value or "").strip()
        if text and text not in terms:
            terms.append(text)
    return terms
