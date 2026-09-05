from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agent_kb.query.query_frame import QueryFrame


@dataclass(frozen=True)
class RetrievalCandidate:
    """One candidate emitted by a retrieval channel.

    Candidates remain source-typed so fusion can deduplicate card, object, fact,
    and evidence hits without losing traceability.
    """

    candidate_id: str
    source_type: str
    source_id: str
    channel: str
    score: float
    rank: int = 0
    matched_terms: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalDiagnostics:
    requested_channels: list[str] = field(default_factory=list)
    executed_channels: list[str] = field(default_factory=list)
    skipped_channels: dict[str, str] = field(default_factory=dict)
    channel_candidate_counts: dict[str, int] = field(default_factory=dict)
    query_terms: list[str] = field(default_factory=list)
    target_object_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalResult:
    """Fused, intent-aware retrieval output for one QueryFrame."""

    query_frame: QueryFrame
    candidates: list[RetrievalCandidate]
    selected_object_ids: list[str] = field(default_factory=list)
    selected_card_ids: list[str] = field(default_factory=list)
    selected_fact_ids: list[str] = field(default_factory=list)
    selected_evidence_ids: list[str] = field(default_factory=list)
    diagnostics: RetrievalDiagnostics = field(default_factory=RetrievalDiagnostics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_frame": self.query_frame.to_dict(),
            "candidates": [item.to_dict() for item in self.candidates],
            "selected_object_ids": list(self.selected_object_ids),
            "selected_card_ids": list(self.selected_card_ids),
            "selected_fact_ids": list(self.selected_fact_ids),
            "selected_evidence_ids": list(self.selected_evidence_ids),
            "diagnostics": self.diagnostics.to_dict(),
        }
