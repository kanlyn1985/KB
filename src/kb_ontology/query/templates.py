"""Deterministic query templates (ADR-0004).

Each template is a pure function: (store, frame) → QueryResult.
No LLM calls. No dynamic SQL beyond fixed store APIs.
"""

from __future__ import annotations

from typing import Callable

from kb_ontology.query.frame import HitEntity, QueryFrame, QueryResult
from kb_ontology.storage.models import Attribute, Entity, Evidence, Relation
from kb_ontology.storage.store import OntologyStore

TemplateFn = Callable[[OntologyStore, QueryFrame], QueryResult]


def _entity_dict(e: Entity) -> dict:
    return e.to_dict()


def _attr_dicts(attrs: list[Attribute]) -> list[dict]:
    return [a.to_dict() for a in attrs]


def _rel_dicts(rels: list[Relation]) -> list[dict]:
    return [r.to_dict() for r in rels]


def _evd_dicts(evds: list[Evidence]) -> list[dict]:
    return [e.to_dict() for e in evds]


def _collect_entity_evidence(store: OntologyStore, entity_id: str) -> list[dict]:
    bag: list[Evidence] = []
    bag.extend(store.get_evidence("entity", entity_id))
    for attr in store.get_attributes(entity_id):
        bag.extend(store.get_evidence("attribute", attr.id))
    for rel in store.get_relations(entity_id):
        bag.extend(store.get_evidence("relation", rel.id))
    # de-dupe by id preserving order
    seen: set[str] = set()
    out: list[dict] = []
    for e in bag:
        if e.id in seen:
            continue
        seen.add(e.id)
        out.append(e.to_dict())
    return out


def _filter_attributes(
    attrs: list[Attribute], names: list[str] | None
) -> list[Attribute]:
    if not names:
        return attrs
    wanted = {n.lower() for n in names}
    return [a for a in attrs if a.name.lower() in wanted]


def _unresolved_primary(frame: QueryFrame) -> QueryResult | None:
    primary = frame.primary_entity()
    if primary is None:
        return QueryResult(
            intent=frame.intent,
            template_id=frame.intent,
            frame=frame,
            empty_reason="no_target_entity",
            warnings=["no_target_entity"],
        )
    if not primary.is_resolved:
        return QueryResult(
            intent=frame.intent,
            template_id=frame.intent,
            frame=frame,
            empty_reason="entity_not_found",
            warnings=[f"entity_not_found:{primary.canonical_name or primary.matched_text}"],
        )
    return None


# ── Templates ─────────────────────────────────────────────────────────


def parameter_lookup(store: OntologyStore, frame: QueryFrame) -> QueryResult:
    """Fetch attributes of a target entity (optionally filtered by name)."""
    early = _unresolved_primary(frame)
    if early:
        return early
    primary = frame.primary_entity()
    assert primary is not None and primary.entity_id
    entity = store.get_entity(primary.entity_id)
    if entity is None:
        return QueryResult(
            intent=frame.intent,
            template_id="parameter_lookup",
            frame=frame,
            empty_reason="entity_not_found",
            warnings=[f"entity_id_missing:{primary.entity_id}"],
        )
    attrs = _filter_attributes(
        store.get_attributes(entity.id), frame.target_attributes or None
    )
    evidence = _collect_entity_evidence(store, entity.id)
    hit = HitEntity(
        entity=_entity_dict(entity),
        attributes=_attr_dicts(attrs),
        evidence=evidence,
        matched_by=primary.matched_text or primary.canonical_name,
    )
    empty_reason = None
    warnings: list[str] = []
    if frame.target_attributes and not attrs:
        empty_reason = "attributes_not_found"
        warnings.append(
            "attributes_not_found:" + ",".join(frame.target_attributes)
        )
    return QueryResult(
        intent="parameter_lookup",
        template_id="parameter_lookup",
        frame=frame,
        hits=[hit],
        evidence=evidence,
        warnings=warnings,
        empty_reason=empty_reason if not attrs and frame.target_attributes else None,
        meta={"attribute_count": len(attrs)},
    )


def definition(store: OntologyStore, frame: QueryFrame) -> QueryResult:
    """Return description-like attributes + outgoing/incoming relations."""
    early = _unresolved_primary(frame)
    if early:
        return early
    primary = frame.primary_entity()
    assert primary is not None and primary.entity_id
    entity = store.get_entity(primary.entity_id)
    if entity is None:
        return QueryResult(
            intent="definition",
            template_id="definition",
            frame=frame,
            empty_reason="entity_not_found",
        )
    attrs = store.get_attributes(entity.id)
    # Prefer description-ish attributes first in the payload ordering.
    preferred = {"description", "name", "text", "type", "definition"}
    attrs_sorted = sorted(
        attrs, key=lambda a: (0 if a.name.lower() in preferred else 1, a.name)
    )
    out_rels = store.get_relations(entity.id)
    in_rels = store.get_reverse_relations(entity.id)
    related: list[dict] = []
    for rel in list(out_rels) + list(in_rels):
        other_id = rel.target_id if rel.source_id == entity.id else rel.source_id
        other = store.get_entity(other_id)
        related.append(
            {
                "relation": rel.to_dict(),
                "direction": "out" if rel.source_id == entity.id else "in",
                "other": other.to_dict() if other else {"id": other_id},
            }
        )
    evidence = _collect_entity_evidence(store, entity.id)
    hit = HitEntity(
        entity=_entity_dict(entity),
        attributes=_attr_dicts(attrs_sorted),
        relations=_rel_dicts(list(out_rels) + list(in_rels)),
        evidence=evidence,
        matched_by=primary.matched_text or primary.canonical_name,
    )
    return QueryResult(
        intent="definition",
        template_id="definition",
        frame=frame,
        hits=[hit],
        related=related,
        evidence=evidence,
        meta={"relation_count": len(related)},
    )


def relation_query(store: OntologyStore, frame: QueryFrame) -> QueryResult:
    """Outgoing (and if none, incoming) relations, optionally type-filtered."""
    early = _unresolved_primary(frame)
    if early:
        return early
    primary = frame.primary_entity()
    assert primary is not None and primary.entity_id
    entity = store.get_entity(primary.entity_id)
    if entity is None:
        return QueryResult(
            intent="relation_query",
            template_id="relation_query",
            frame=frame,
            empty_reason="entity_not_found",
        )
    rel_type = frame.relation_type
    out_rels = store.get_relations(entity.id, rel_type)
    in_rels = store.get_reverse_relations(entity.id, rel_type)
    hits: list[HitEntity] = []
    related: list[dict] = []
    for rel, direction in [(r, "out") for r in out_rels] + [(r, "in") for r in in_rels]:
        other_id = rel.target_id if direction == "out" else rel.source_id
        other = store.get_entity(other_id)
        if other is None:
            continue
        other_attrs = store.get_attributes(other.id)
        hits.append(
            HitEntity(
                entity=_entity_dict(other),
                attributes=_attr_dicts(other_attrs),
                relations=[rel.to_dict()],
                evidence=_collect_entity_evidence(store, other.id),
                matched_by=f"{direction}:{rel.relation_type}",
            )
        )
        related.append(
            {
                "relation": rel.to_dict(),
                "direction": direction,
                "other": other.to_dict(),
            }
        )
    empty_reason = None if hits else "relations_not_found"
    return QueryResult(
        intent="relation_query",
        template_id="relation_query",
        frame=frame,
        hits=hits,
        related=related,
        empty_reason=empty_reason,
        meta={
            "relation_type": rel_type,
            "out_count": len(out_rels),
            "in_count": len(in_rels),
        },
    )


def hierarchy_traversal(store: OntologyStore, frame: QueryFrame) -> QueryResult:
    """Recursive part_of (or frame.relation_type) walk."""
    early = _unresolved_primary(frame)
    if early:
        return early
    primary = frame.primary_entity()
    assert primary is not None and primary.entity_id
    rel_type = frame.relation_type or "part_of"
    direction = frame.hierarchy_direction if frame.hierarchy_direction in ("up", "down") else "down"
    tree = store.get_entity_tree(
        primary.entity_id,
        direction=direction,
        relation_type=rel_type,
        max_depth=max(1, int(frame.max_depth or 5)),
    )
    root_entity = store.get_entity(primary.entity_id)
    if root_entity is None:
        return QueryResult(
            intent="hierarchy_traversal",
            template_id="hierarchy_traversal",
            frame=frame,
            empty_reason="entity_not_found",
        )

    def _flatten(node: dict, acc: list[HitEntity], depth: int = 0) -> None:
        ent_payload = node.get("entity")
        if not ent_payload or depth == 0:
            # skip root in children list; root is the hit itself
            pass
        eid = node.get("entity_id")
        if eid and depth > 0 and ent_payload:
            acc.append(
                HitEntity(
                    entity=ent_payload,
                    children=[],
                    matched_by=f"hierarchy:{direction}:{rel_type}:d{depth}",
                )
            )
        for child in node.get("children") or []:
            _flatten(child, acc, depth + 1)

    children_hits: list[HitEntity] = []
    _flatten(tree, children_hits, 0)
    hit = HitEntity(
        entity=_entity_dict(root_entity),
        attributes=_attr_dicts(store.get_attributes(root_entity.id)),
        children=tree.get("children") or [],
        evidence=_collect_entity_evidence(store, root_entity.id),
        matched_by=primary.matched_text or primary.canonical_name,
    )
    empty_reason = None if children_hits or (tree.get("children")) else "hierarchy_empty"
    return QueryResult(
        intent="hierarchy_traversal",
        template_id="hierarchy_traversal",
        frame=frame,
        hits=[hit] + children_hits,
        empty_reason=empty_reason,
        meta={
            "direction": direction,
            "relation_type": rel_type,
            "depth_limit": frame.max_depth,
            "child_count": len(children_hits),
            "tree": tree,
        },
    )


def cross_entity(store: OntologyStore, frame: QueryFrame) -> QueryResult:
    """Find relations connecting two entities (either direction, any/ filtered type)."""
    source = frame.entity_by_role("source") or frame.entity_by_role("primary")
    target = frame.entity_by_role("target") or frame.entity_by_role("secondary")
    warnings: list[str] = []
    if source is None or target is None:
        return QueryResult(
            intent="cross_entity",
            template_id="cross_entity",
            frame=frame,
            empty_reason="need_two_entities",
            warnings=["need_two_entities"],
        )
    if not source.is_resolved or not target.is_resolved:
        if not source.is_resolved:
            warnings.append(f"entity_not_found:{source.canonical_name or source.matched_text}")
        if not target.is_resolved:
            warnings.append(f"entity_not_found:{target.canonical_name or target.matched_text}")
        return QueryResult(
            intent="cross_entity",
            template_id="cross_entity",
            frame=frame,
            empty_reason="entity_not_found",
            warnings=warnings,
        )

    rel_type = frame.relation_type
    # Collect edges source→* and *→source, keep those touching target.
    edges: list[tuple[Relation, str]] = []
    for rel in store.get_relations(source.entity_id, rel_type):
        if rel.target_id == target.entity_id:
            edges.append((rel, "source→target"))
    for rel in store.get_reverse_relations(source.entity_id, rel_type):
        if rel.source_id == target.entity_id:
            edges.append((rel, "target→source"))
    # Also scan target side in case of multi-hop absence (direct only here).
    if not edges:
        for rel in store.get_relations(target.entity_id, rel_type):
            if rel.target_id == source.entity_id:
                edges.append((rel, "target→source"))
        for rel in store.get_reverse_relations(target.entity_id, rel_type):
            if rel.source_id == source.entity_id:
                edges.append((rel, "source→target"))

    src_ent = store.get_entity(source.entity_id)
    tgt_ent = store.get_entity(target.entity_id)
    hits: list[HitEntity] = []
    if src_ent:
        hits.append(
            HitEntity(
                entity=_entity_dict(src_ent),
                attributes=_attr_dicts(store.get_attributes(src_ent.id)),
                matched_by="source",
            )
        )
    if tgt_ent:
        hits.append(
            HitEntity(
                entity=_entity_dict(tgt_ent),
                attributes=_attr_dicts(store.get_attributes(tgt_ent.id)),
                matched_by="target",
            )
        )
    related = [
        {"relation": rel.to_dict(), "direction": direction}
        for rel, direction in edges
    ]
    return QueryResult(
        intent="cross_entity",
        template_id="cross_entity",
        frame=frame,
        hits=hits,
        related=related,
        empty_reason=None if edges else "no_direct_relation",
        warnings=warnings,
        meta={"edge_count": len(edges), "relation_type": rel_type},
    )


def attribute_search(store: OntologyStore, frame: QueryFrame) -> QueryResult:
    """Reverse lookup entities whose attribute values match a substring."""
    needle = (frame.attribute_value_query or "").strip()
    if not needle:
        # Fall back to first target attribute name used as value query, or aliases.
        if frame.target_attributes:
            needle = frame.target_attributes[0]
        elif frame.aliases:
            needle = frame.aliases[0]
        elif frame.normalized_query:
            needle = frame.normalized_query
        else:
            needle = frame.original_query
    needle = needle.strip()
    if not needle:
        return QueryResult(
            intent="attribute_search",
            template_id="attribute_search",
            frame=frame,
            empty_reason="no_value_query",
            warnings=["no_value_query"],
        )

    attr_name = None
    if len(frame.target_attributes) == 1:
        # When exactly one attribute name is specified, constrain the search.
        # (Multiple names → search any attribute by value only.)
        attr_name = frame.target_attributes[0]

    pairs = store.find_entities_by_attribute(
        attr_name=attr_name,
        value_query=needle,
        domain=frame.domain,
        limit=50,
    )
    hits: list[HitEntity] = []
    for entity, attr in pairs:
        hits.append(
            HitEntity(
                entity=_entity_dict(entity),
                attributes=[attr.to_dict()],
                evidence=_collect_entity_evidence(store, entity.id),
                matched_by=f"attr:{attr.name}={attr.value}",
            )
        )
    return QueryResult(
        intent="attribute_search",
        template_id="attribute_search",
        frame=frame,
        hits=hits,
        empty_reason=None if hits else "no_attribute_match",
        meta={"value_query": needle, "attr_name": attr_name, "match_count": len(hits)},
    )


# Registry — intent → template
TEMPLATE_REGISTRY: dict[str, TemplateFn] = {
    "parameter_lookup": parameter_lookup,
    "definition": definition,
    "relation_query": relation_query,
    "hierarchy_traversal": hierarchy_traversal,
    "cross_entity": cross_entity,
    "attribute_search": attribute_search,
}


def get_template(intent: str) -> TemplateFn | None:
    return TEMPLATE_REGISTRY.get(intent)
