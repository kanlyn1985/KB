from __future__ import annotations

from agent_kb.context.context_pack import ContextEvidence, ContextFact
from agent_kb.projection.models import ObjectProjection, ObjectRelation
from agent_kb.retrieval.cards import RetrievalCard


_DEFAULT_ANSWER_SHAPES_BY_OBJECT_TYPE: dict[str, list[str]] = {
    "Parameter": ["definition", "constraint_lookup", "test_method"],
    "ParameterConstraint": ["constraint_lookup", "evidence_lookup"],
    "StandardClause": ["definition", "constraint_lookup", "evidence_lookup"],
    "TestMethod": ["test_method", "procedure"],
    "TestResult": ["test_result", "compliance_check"],
}


def build_retrieval_card(
    projection: ObjectProjection,
    *,
    relations: list[ObjectRelation] | None = None,
    facts: list[ContextFact] | None = None,
    evidence: list[ContextEvidence] | None = None,
) -> RetrievalCard:
    """Build one recall-optimized object card.

    The card aggregates object names, aliases, nearby relations, facts, and
    evidence ids into a single search surface. This is the first implementation
    of object-centered recall.
    """

    related_object_ids = _related_object_ids(projection.object_id, relations or [])
    evidence_ids = _evidence_ids(projection, facts or [], evidence or [])
    answer_shapes = _answer_shapes(projection)
    search_text = _build_search_text(
        projection=projection,
        related_object_ids=related_object_ids,
        facts=facts or [],
        answer_shapes=answer_shapes,
    )
    return RetrievalCard(
        card_id=f"card:{projection.domain}:{projection.object_id}",
        domain=projection.domain,
        object_id=projection.object_id,
        card_type=projection.object_type,
        title=projection.canonical_name,
        search_text=search_text,
        aliases=list(projection.aliases),
        related_object_ids=related_object_ids,
        evidence_ids=evidence_ids,
        answer_shapes=answer_shapes,
        structured_payload={
            "object": projection.to_dict(),
            "related_object_ids": related_object_ids,
            "fact_ids": [fact.fact_id for fact in facts or [] if _fact_mentions_object(fact, projection.object_id)],
        },
        confidence=projection.confidence,
    )


def build_retrieval_cards(
    projections: list[ObjectProjection],
    *,
    relations: list[ObjectRelation] | None = None,
    facts: list[ContextFact] | None = None,
    evidence: list[ContextEvidence] | None = None,
) -> list[RetrievalCard]:
    return [
        build_retrieval_card(
            projection,
            relations=relations,
            facts=facts,
            evidence=evidence,
        )
        for projection in projections
    ]


def _related_object_ids(object_id: str, relations: list[ObjectRelation]) -> list[str]:
    related: list[str] = []
    for relation in relations:
        if relation.source_object_id == object_id:
            candidate = relation.target_object_id
        elif relation.target_object_id == object_id:
            candidate = relation.source_object_id
        else:
            continue
        if candidate and candidate not in related:
            related.append(candidate)
    return related[:16]


def _evidence_ids(
    projection: ObjectProjection,
    facts: list[ContextFact],
    evidence: list[ContextEvidence],
) -> list[str]:
    ids: list[str] = []
    for ref in projection.evidence_refs:
        if ref.evidence_id and ref.evidence_id not in ids:
            ids.append(ref.evidence_id)
    for fact in facts:
        if _fact_mentions_object(fact, projection.object_id):
            for evidence_id in fact.evidence_ids:
                if evidence_id and evidence_id not in ids:
                    ids.append(evidence_id)
    for item in evidence:
        if item.evidence_id and item.evidence_id not in ids and projection.canonical_name in item.snippet:
            ids.append(item.evidence_id)
    return ids[:24]


def _answer_shapes(projection: ObjectProjection) -> list[str]:
    return list(_DEFAULT_ANSWER_SHAPES_BY_OBJECT_TYPE.get(projection.object_type, ["definition", "general_search"]))


def _build_search_text(
    *,
    projection: ObjectProjection,
    related_object_ids: list[str],
    facts: list[ContextFact],
    answer_shapes: list[str],
) -> str:
    parts: list[str] = [
        projection.object_id,
        projection.canonical_name,
        projection.object_type,
        *projection.aliases,
        *related_object_ids,
        *answer_shapes,
    ]
    for key, value in projection.properties.items():
        parts.append(str(key))
        parts.append(str(value))
    for fact in facts:
        if _fact_mentions_object(fact, projection.object_id):
            parts.extend([fact.fact_type, fact.predicate, str(fact.object_value)])
    deduped: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return " ".join(deduped)


def _fact_mentions_object(fact: ContextFact, object_id: str) -> bool:
    if fact.subject == object_id:
        return True
    if str(fact.object_value) == object_id:
        return True
    return object_id in " ".join(str(value) for value in fact.qualifiers.values())
