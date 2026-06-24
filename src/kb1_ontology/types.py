"""Standardized data types for the ontology query system.

Every component communicates through these dataclasses only.
No component depends on another's internal implementation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---- Routing -------------------------------------------------------

@dataclass(frozen=True)
class RouteResult:
    """Output of the Router. The canonical classification of a query."""
    category: str       # parameter | definition | reference | service | traversal | free_form
    entity: str | None  # e.g. "GB/T 18487.4", "CCU", "V2L"
    target: str | None  # e.g. "额定电压", "唤醒源"


# ---- Decomposition -------------------------------------------------

# target_artifact values — each maps 1:1 to an ingestion table/column:
#   entity    → entity table
#   term      → term / term_alias
#   param     → param / param_alias
#   attribute → attribute (incl. service_* when target_artifact=service)
#   service   → attribute WHERE attribute_name LIKE 'service_%'
#   relation  → relation table
_ARTIFACTS = ("entity", "term", "param", "attribute", "service", "relation")


@dataclass(frozen=True)
class QueryDecomposition:
    """A query broken into parts that each match an ingestion artifact.

    The decomposition is expressed in the vocabulary of what was ingested:
      - target_artifact: which table/column family to query
      - operation:       lookup (one artifact) vs enumerate (all matching)
      - scope:           the entity the query is scoped to (CCU, GB/T 18487.1)
      - tokens:          concept words / identifiers to match against names
    This replaces the earlier verb-based intent (definition/parameter/...)
    because the real distinction between queries is the operation (find-one vs
    list-all), not the noun.
    """
    target_artifact: str           # entity | term | param | attribute | service | relation
    operation: str                 # lookup | enumerate
    scope: str | None              # entity anchor (CCU, GB/T 18487.1) or None
    tokens: tuple[str, ...]        # concept words / identifiers to match

    @property
    def category(self) -> str:
        """Map onto the handler category vocabulary for the formatter/API."""
        if self.target_artifact == "service":
            return "service"
        if self.target_artifact == "relation":
            return "traversal" if self.operation == "enumerate" else "reference"
        if self.target_artifact == "term":
            return "definition"
        if self.target_artifact == "attribute":
            return "parameter"
        return "definition"

    # Legacy compatibility shims (used while category handlers coexist) ----
    @property
    def entity_anchor(self) -> str | None:
        return self.scope

    @property
    def intent(self) -> str:
        return self.target_artifact

    @property
    def target_field(self) -> str | None:
        return self.tokens[0] if self.tokens else None


# ---- Handler -------------------------------------------------------

@dataclass(frozen=True)
class HandlerResult:
    """Output of a Handler. Raw query result with metadata."""
    data: Any                   # The query result: str, list, dict, etc.
    data_type: str              # value | list | dict | path_list
    source: str                 # attribute | param | term | relation
    query: str                  # Original query


# ---- Answer --------------------------------------------------------

@dataclass
class Answer:
    """Final output presented to the user or API."""
    query: str
    category: str
    structured: Any = None      # HandlerResult.data
    display: str = ""           # Human-readable text
    source: str = ""            # Where the answer came from
    legacy_context: str = ""    # Prose context from legacy system
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "category": self.category,
            "structured": self.structured,
            "display": self.display,
            "source": self.source,
            "legacy_context": self.legacy_context,
            "warnings": self.warnings,
        }
