"""Attribute store for the KB1 ontology system.

Attributes are **typed properties** of entities or classes, stored
in a (subject, attribute_name, value) triple form. Per the design
in docs/ontology/CONTEXT.md, the value is one of four types:

* ``string``  — a free-text value
* ``number``  — a single numeric value
* ``range``   — {min, max, unit, tolerance}
* ``reference`` — a pointer to another entity (or class)

The attribute store is the mechanism that supports
**attribute-value queries** like "what is the P2 timing value?",
which is a different kind of question from relation-traversal
queries (Phase 3) or class-hierarchy queries (Phase 1).
"""
from .schema import (
    VALUE_TYPE_STRING,
    VALUE_TYPE_NUMBER,
    VALUE_TYPE_RANGE,
    VALUE_TYPE_REFERENCE,
    Attribute,
    ensure_schema,
)
from .range_parser import parse_range_value
from .crud import (
    AttributeStoreError,
    set_attribute,
    get_attribute,
    list_attributes,
    delete_attribute,
    query_attributes,
)

__all__ = [
    "VALUE_TYPE_STRING",
    "VALUE_TYPE_NUMBER",
    "VALUE_TYPE_RANGE",
    "VALUE_TYPE_REFERENCE",
    "Attribute",
    "ensure_schema",
    "parse_range_value",
    "AttributeStoreError",
    "set_attribute",
    "get_attribute",
    "list_attributes",
    "delete_attribute",
    "query_attributes",
]
