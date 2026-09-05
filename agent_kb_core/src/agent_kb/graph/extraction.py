from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from agent_kb.graph.store import GraphEdge


class RelationExtractor(Protocol):
    @property
    def extractor_id(self) -> str: ...

    def extract(self, index: Any) -> list[GraphEdge]: ...


@dataclass(frozen=True)
class DeterministicRelationExtractor:
    """Evidence-preserving relation baseline for explicit object references.

    It extracts only relations that are already explicit in retrieval cards,
    object properties, or fact values. It does not infer hidden causal links.
    """

    extractor_id: str = "deterministic-relation-v1"

    def extract(self, index: Any) -> list[GraphEdge]:
        object_ids = {item.object_id for item in index.object_projections}
        edges: dict[str, GraphEdge] = {}

        for card in index.retrieval_cards:
            source = str(card.object_id or "").strip()
            if not source:
                continue
            for target in card.related_object_ids:
                target_id = str(target or "").strip()
                if target_id in object_ids and target_id != source:
                    edge = _edge(
                        domain=card.domain,
                        relation_type="related_to",
                        source=source,
                        target=target_id,
                        evidence_ids=list(card.evidence_ids),
                        confidence=max(0.45, min(float(card.confidence), 1.0)),
                        properties={"source": "retrieval_card", "card_id": card.card_id},
                    )
                    edges[edge.edge_id] = edge

        for projection in index.object_projections:
            for property_name, value in projection.properties.items():
                for target_id in _object_references(value, object_ids):
                    if target_id == projection.object_id:
                        continue
                    edge = _edge(
                        domain=projection.domain,
                        relation_type=f"property:{property_name}",
                        source=projection.object_id,
                        target=target_id,
                        evidence_ids=[ref.evidence_id for ref in projection.evidence_refs],
                        confidence=max(0.4, min(float(projection.confidence), 1.0)),
                        properties={"source": "object_property", "property": property_name},
                    )
                    edges[edge.edge_id] = edge

        for fact in index.context_facts:
            source = str(fact.subject or "").strip()
            if source not in object_ids:
                continue
            for target_id in _object_references(fact.object_value, object_ids):
                if target_id == source:
                    continue
                relation_type = str(fact.predicate or fact.fact_type or "related_to").strip().replace(" ", "_")
                edge = _edge(
                    domain=_domain_for(source, index),
                    relation_type=relation_type,
                    source=source,
                    target=target_id,
                    evidence_ids=list(fact.evidence_ids),
                    confidence=max(0.35, min(float(fact.confidence), 1.0)),
                    properties={"source": "fact", "fact_id": fact.fact_id, "fact_type": fact.fact_type},
                )
                edges[edge.edge_id] = edge

        return sorted(edges.values(), key=lambda item: item.edge_id)


def _object_references(value: Any, object_ids: set[str]) -> list[str]:
    values: list[str] = []
    if isinstance(value, str):
        if value in object_ids:
            values.append(value)
        else:
            values.extend(object_id for object_id in object_ids if object_id in value)
    elif isinstance(value, dict):
        for nested in value.values():
            values.extend(_object_references(nested, object_ids))
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            values.extend(_object_references(nested, object_ids))
    return sorted(set(values))


def _domain_for(object_id: str, index: Any) -> str:
    for item in index.object_projections:
        if item.object_id == object_id:
            return item.domain
    return "generic"


def _edge(
    *,
    domain: str,
    relation_type: str,
    source: str,
    target: str,
    evidence_ids: list[str],
    confidence: float,
    properties: dict[str, Any],
) -> GraphEdge:
    digest = hashlib.sha256(f"{domain}:{relation_type}:{source}:{target}".encode("utf-8")).hexdigest()
    return GraphEdge(
        edge_id=f"edge_{digest[:20]}",
        domain=domain,
        relation_type=relation_type,
        source_object_id=source,
        target_object_id=target,
        properties=properties,
        evidence_ids=evidence_ids,
        confidence=confidence,
        status="extracted",
    )
