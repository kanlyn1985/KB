"""Entity manager for the KB1 ontology system.

Manages **concrete instances** of the classes registered in
``class_registry``. An entity is "a specific thing" — e.g., the
ISO 14229-1 standard, the GB/T 20234 connector, an OBC device
of a particular vendor.

Key capabilities:
- CRUD on entities with class_id + domain
- **Canonical-name normalization** so that
  "ISO 14229-1—2013", "ISO 14229-1:2013", and "ISO 14229-1"
  all collapse to the same entity.
- **De-duplication** keyed on (normalized_name, class_id, domain).
- **Alias merge** so that different spellings accumulate into
  one entity.
- **Document ingestion** records which job roles a document
  is associated with (so e.g. a CAN document can be tagged
  relevant to both systems and software engineers).
"""
from .schema import (
    LAYER_INSTANCE,
    DocumentRole,
    Entity,
    ensure_schema,
)
from .normalization import (
    normalize_canonical_name,
    normalize_for_match,
)
from .crud import (
    EntityManagerError,
    create_entity,
    get_entity,
    find_or_create_entity,
    merge_aliases,
    list_entities,
)
from .document_roles import (
    set_document_roles,
    get_document_roles,
    add_document_role,
    remove_document_role,
)

__all__ = [
    "LAYER_INSTANCE",
    "DocumentRole",
    "Entity",
    "ensure_schema",
    "normalize_canonical_name",
    "normalize_for_match",
    "EntityManagerError",
    "create_entity",
    "get_entity",
    "find_or_create_entity",
    "merge_aliases",
    "list_entities",
    "set_document_roles",
    "get_document_roles",
    "add_document_role",
    "remove_document_role",
]
