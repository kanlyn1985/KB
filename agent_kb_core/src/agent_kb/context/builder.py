from __future__ import annotations

from agent_kb.context.context_pack import AgentContextPack, AnswerContract, ContextEvidence, ContextFact
from agent_kb.domains.schema import DomainPack
from agent_kb.projection.models import ObjectProjection, ObjectRelation
from agent_kb.query.query_frame import QueryFrame
from agent_kb.retrieval.cards import RetrievalCard


def build_context_pack(
    *,
    query_frame: QueryFrame,
    domain_pack: DomainPack | None = None,
    objects: list[ObjectProjection] | None = None,
    relations: list[ObjectRelation] | None = None,
    retrieval_cards: list[RetrievalCard] | None = None,
    facts: list[ContextFact] | None = None,
    evidence: list[ContextEvidence] | None = None,
) -> AgentContextPack:
    """Assemble the structured context supplied to an agent.

    This is not a final answer generator. It selects relevant objects, cards,
    evidence, hidden context, warnings, and knowledge gaps so a downstream agent
    can answer with domain-aware evidence constraints.
    """

    all_objects = list(objects or [])
    all_relations = list(relations or [])
    all_cards = list(retrieval_cards or [])
    all_facts = list(facts or [])
    all_evidence = list(evidence or [])

    target_object_ids = {target.object_id for target in query_frame.target_objects}
    selected_objects = _select_objects(all_objects, target_object_ids)
    selected_cards = _select_cards(all_cards, target_object_ids, query_frame)
    selected_relations = _select_relations(all_relations, target_object_ids)
    selected_facts = _select_facts(all_facts, target_object_ids, query_frame)
    selected_evidence = _select_evidence(all_evidence, selected_cards, selected_facts)
    hidden_context = _hidden_context(domain_pack, target_object_ids)
    answer_contract = _answer_contract(domain_pack, query_frame.answer_contract)
    warnings = _warnings(query_frame, selected_objects, selected_cards, selected_evidence)
    knowledge_gaps = _knowledge_gaps(query_frame, selected_objects, selected_evidence)

    return AgentContextPack(
        query_frame=query_frame,
        answer_contract=answer_contract,
        target_objects=selected_objects,
        object_relations=selected_relations,
        retrieval_cards=selected_cards,
        facts=selected_facts,
        evidence=selected_evidence,
        hidden_context=hidden_context,
        warnings=warnings,
        knowledge_gaps=knowledge_gaps,
        recommended_answer_strategy=query_frame.answer_strategy,
    )


def _select_objects(objects: list[ObjectProjection], target_object_ids: set[str]) -> list[ObjectProjection]:
    if not target_object_ids:
        return objects[:8]
    return [obj for obj in objects if obj.object_id in target_object_ids][:8]


def _select_cards(cards: list[RetrievalCard], target_object_ids: set[str], frame: QueryFrame) -> list[RetrievalCard]:
    selected: list[RetrievalCard] = []
    for card in cards:
        if target_object_ids and card.object_id in target_object_ids:
            selected.append(card)
            continue
        if frame.intent in card.answer_shapes:
            selected.append(card)
            continue
        if any(term and term in card.search_text for term in frame.must_terms):
            selected.append(card)
    return _dedupe_cards(selected)[:8]


def _select_relations(relations: list[ObjectRelation], target_object_ids: set[str]) -> list[ObjectRelation]:
    if not target_object_ids:
        return relations[:12]
    return [
        relation
        for relation in relations
        if relation.source_object_id in target_object_ids or relation.target_object_id in target_object_ids
    ][:12]


def _select_facts(facts: list[ContextFact], target_object_ids: set[str], frame: QueryFrame) -> list[ContextFact]:
    selected: list[ContextFact] = []
    preferred = set(frame.preferred_fact_types)
    for fact in facts:
        object_match = not target_object_ids or fact.subject in target_object_ids or str(fact.object_value) in target_object_ids
        type_match = not preferred or fact.fact_type in preferred
        if object_match and type_match:
            selected.append(fact)
    if not selected and preferred:
        selected = [fact for fact in facts if fact.fact_type in preferred]
    return selected[:16]


def _select_evidence(
    evidence: list[ContextEvidence],
    cards: list[RetrievalCard],
    facts: list[ContextFact],
) -> list[ContextEvidence]:
    wanted = set()
    for card in cards:
        wanted.update(card.evidence_ids)
    for fact in facts:
        wanted.update(fact.evidence_ids)
    if not wanted:
        return evidence[:8]
    return [item for item in evidence if item.evidence_id in wanted][:12]


def _hidden_context(domain_pack: DomainPack | None, target_object_ids: set[str]) -> list[str]:
    if not domain_pack:
        return []
    result: list[str] = []
    for rule in domain_pack.hidden_context_rules:
        trigger_object_id = str(rule.trigger.get("object_id") or "")
        if trigger_object_id and trigger_object_id in target_object_ids:
            for line in rule.inject:
                if line not in result:
                    result.append(line)
    return result[:12]


def _answer_contract(domain_pack: DomainPack | None, contract_name: str | None) -> AnswerContract | None:
    if not domain_pack or not contract_name:
        return None
    spec = domain_pack.answer_contracts.get(contract_name)
    if not spec:
        return None
    return AnswerContract(
        contract_id=spec.name,
        intent=spec.intent,
        required_sections=list(spec.required_sections),
        optional_sections=list(spec.optional_sections),
        output_policy="evidence_grounded",
    )


def _warnings(
    frame: QueryFrame,
    objects: list[ObjectProjection],
    cards: list[RetrievalCard],
    evidence: list[ContextEvidence],
) -> list[str]:
    warnings: list[str] = []
    if frame.ambiguity:
        warnings.append("query has domain ambiguity; clarification may be required")
    if frame.missing_slots:
        warnings.append("query is missing slots: " + ", ".join(frame.missing_slots))
    if frame.target_objects and not objects:
        warnings.append("target objects were linked but no object projection was available")
    if frame.target_objects and not cards:
        warnings.append("target objects were linked but no retrieval card was available")
    if frame.intent != "general_search" and not evidence:
        warnings.append("no supporting evidence selected for non-general intent")
    return warnings


def _knowledge_gaps(frame: QueryFrame, objects: list[ObjectProjection], evidence: list[ContextEvidence]) -> list[str]:
    gaps: list[str] = []
    for slot in frame.missing_slots:
        gaps.append(f"missing_slot:{slot}")
    if not frame.target_objects and frame.intent != "general_search":
        gaps.append("target_object_not_identified")
    if frame.target_objects and not objects:
        gaps.append("object_projection_missing")
    if frame.intent != "general_search" and not evidence:
        gaps.append("supporting_evidence_missing")
    return gaps


def _dedupe_cards(cards: list[RetrievalCard]) -> list[RetrievalCard]:
    result: list[RetrievalCard] = []
    seen: set[str] = set()
    for card in cards:
        if card.card_id in seen:
            continue
        seen.add(card.card_id)
        result.append(card)
    return result
