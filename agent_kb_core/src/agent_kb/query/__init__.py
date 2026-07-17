"""Query understanding contracts and deterministic frame builder."""

from .query_frame import QueryAmbiguity, QueryFrame, TargetObject
from .understanding import UnderstandingOptions, understand_query

__all__ = [
    "QueryAmbiguity",
    "QueryFrame",
    "TargetObject",
    "UnderstandingOptions",
    "understand_query",
]
