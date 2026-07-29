"""Query understanding + deterministic template engine."""

from kb_ontology.query.engine import execute_frame, query
from kb_ontology.query.frame import (
    KNOWN_INTENTS,
    HitEntity,
    QueryAmbiguity,
    QueryFrame,
    QueryResult,
    TargetEntityRef,
)
from kb_ontology.query.templates import TEMPLATE_REGISTRY, get_template
from kb_ontology.query.understanding import understand_query

__all__ = [
    "KNOWN_INTENTS",
    "TEMPLATE_REGISTRY",
    "HitEntity",
    "QueryAmbiguity",
    "QueryFrame",
    "QueryResult",
    "TargetEntityRef",
    "execute_frame",
    "get_template",
    "query",
    "understand_query",
]
