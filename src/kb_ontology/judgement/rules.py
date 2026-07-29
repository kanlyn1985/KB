"""Deterministic structural judgement over QueryResult (ADR-0003).

No LLM. Fast path for "sufficient and clear" queries.
"""

from __future__ import annotations

from kb_ontology.judgement.models import AnswerStrategy, Judgement, SufficiencyStatus
from kb_ontology.query.frame import QueryResult


# Intent → attribute names that strongly support an answer.
_VALUE_ATTRS = frozenset({"value", "unit", "operator", "condition"})
_DESC_ATTRS = frozenset({"description", "text", "definition", "name"})


def _count_attrs(result: QueryResult) -> int:
    return sum(len(h.attributes) for h in result.hits)


def _count_relations(result: QueryResult) -> int:
    from_hits = sum(len(h.relations) for h in result.hits)
    return from_hits + len(result.related)


def _count_evidence(result: QueryResult) -> int:
    ids: set[str] = set()
    for e in result.evidence:
        if isinstance(e, dict) and e.get("id"):
            ids.add(str(e["id"]))
    for h in result.hits:
        for e in h.evidence:
            if isinstance(e, dict) and e.get("id"):
                ids.add(str(e["id"]))
    # Fall back to raw list lengths if ids missing.
    if ids:
        return len(ids)
    return len(result.evidence) + sum(len(h.evidence) for h in result.hits)


def _attr_names(result: QueryResult) -> set[str]:
    names: set[str] = set()
    for h in result.hits:
        for a in h.attributes:
            if isinstance(a, dict) and a.get("name"):
                names.add(str(a["name"]).lower())
    return names


def _has_resolved_target(result: QueryResult) -> bool:
    primary = result.frame.primary_entity()
    if primary is not None and primary.is_resolved:
        return True
    # attribute_search / multi-hit templates may not carry a primary id
    if result.hits and result.intent in {"attribute_search", "relation_query", "hierarchy_traversal"}:
        return True
    if result.intent == "cross_entity":
        src = result.frame.entity_by_role("source") or result.frame.entity_by_role("primary")
        tgt = result.frame.entity_by_role("target") or result.frame.entity_by_role("secondary")
        return bool(src and src.is_resolved and tgt and tgt.is_resolved)
    return False


def _collect_ambiguities(result: QueryResult) -> list[str]:
    items: list[str] = []
    for amb in result.frame.ambiguity:
        label = amb.term
        if amb.candidates:
            label = f"{amb.term}→{','.join(amb.candidates[:3])}"
        items.append(label)
    for w in result.warnings:
        if w.startswith("ambiguity:") or w.startswith("entity_ambiguous:"):
            items.append(w)
    return items


def _collect_conflicts(result: QueryResult) -> list[str]:
    """Detect simple multi-value conflicts on the same attribute name."""
    conflicts: list[str] = []
    # Group by (entity_id, attr_name) → values
    buckets: dict[tuple[str, str], set[str]] = {}
    for h in result.hits:
        eid = str((h.entity or {}).get("id") or "")
        for a in h.attributes:
            if not isinstance(a, dict):
                continue
            name = str(a.get("name") or "")
            if not name:
                continue
            val = a.get("value")
            key = (eid, name)
            buckets.setdefault(key, set()).add(repr(val))
    for (eid, name), values in buckets.items():
        if len(values) > 1:
            conflicts.append(f"attr_conflict:{name}@{eid or '?'}")
    return conflicts


def _intent_missing(result: QueryResult) -> list[str]:
    """Intent-specific structural requirements that are not met."""
    missing: list[str] = []
    intent = result.intent
    empty = result.is_empty or bool(result.empty_reason)

    if intent == "unknown":
        missing.append("unknown_intent")
        return missing

    if empty:
        missing.append(result.empty_reason or "no_hits")

    if intent == "parameter_lookup":
        if not _has_resolved_target(result):
            missing.append("target_entity")
        names = _attr_names(result)
        if not (names & _VALUE_ATTRS) and not (names & _DESC_ATTRS):
            # hit exists but no useful attrs
            if result.hits:
                missing.append("parameter_value_or_description")
        elif "value" not in names and "description" not in names:
            # unit-only is weak
            if names <= {"name", "unit", "operator", "condition"} and "value" not in names:
                if "unit" in names and "value" not in names:
                    missing.append("parameter_value")

    elif intent == "definition":
        if not _has_resolved_target(result):
            missing.append("target_entity")
        names = _attr_names(result)
        if result.hits and not (names & _DESC_ATTRS) and _count_relations(result) == 0:
            missing.append("description_or_relations")

    elif intent == "relation_query":
        if not result.hits and not result.related:
            missing.append("relations")

    elif intent == "hierarchy_traversal":
        child_count = int((result.meta or {}).get("child_count") or 0)
        if child_count == 0 and not result.empty_reason:
            # root hit only
            if len(result.hits) <= 1:
                missing.append("hierarchy_children")

    elif intent == "cross_entity":
        src = result.frame.entity_by_role("source") or result.frame.entity_by_role("primary")
        tgt = result.frame.entity_by_role("target") or result.frame.entity_by_role("secondary")
        if not (src and src.is_resolved):
            missing.append("source_entity")
        if not (tgt and tgt.is_resolved):
            missing.append("target_entity")
        if not result.related:
            missing.append("connecting_relation")

    elif intent == "attribute_search":
        if not result.hits:
            missing.append("attribute_matches")

    return missing


def _strategy(
    status: SufficiencyStatus,
    *,
    ambiguities: list[str],
    missing: list[str],
) -> AnswerStrategy:
    if ambiguities and status != "sufficient":
        return "clarify_ambiguity"
    if status == "sufficient":
        return "answer_with_evidence"
    if status == "partial":
        if any(
            m in missing
            for m in (
                "parameter_value",
                "parameter_value_or_description",
                "description_or_relations",
                "connecting_relation",
                "hierarchy_children",
            )
        ):
            return "answer_with_caveat"
        return "answer_with_caveat"
    # insufficient
    if "unknown_intent" in missing or "no_target_entity" in missing or "target_entity" in missing:
        if ambiguities:
            return "clarify_ambiguity"
        return "report_knowledge_gap"
    if any(m.endswith("_not_found") or m in {"no_hits", "entity_not_found", "no_attribute_match"} for m in missing):
        return "report_knowledge_gap"
    return "refuse_insufficient"


def _score(
    *,
    has_target: bool,
    hit_count: int,
    evidence_count: int,
    missing: list[str],
    ambiguities: list[str],
    conflicts: list[str],
) -> float:
    target_s = 1.0 if has_target else 0.0
    hit_s = 1.0 if hit_count > 0 else 0.0
    if hit_count >= 3:
        hit_s = 1.0
    elif hit_count == 2:
        hit_s = 0.9
    elif hit_count == 1:
        hit_s = 0.8
    ev_s = 1.0 if evidence_count > 0 else 0.0
    if evidence_count >= 2:
        ev_s = 1.0
    elif evidence_count == 1:
        ev_s = 0.7

    req_s = 1.0 if not missing else max(0.0, 1.0 - 0.25 * len(missing))
    score = 0.30 * target_s + 0.30 * hit_s + 0.20 * ev_s + 0.20 * req_s
    if ambiguities:
        score = min(score, 0.55)
    if conflicts:
        score = min(score, 0.60)
    if missing and hit_count == 0:
        score = min(score, 0.25)
    return round(max(0.0, min(1.0, score)), 4)


def judge_rules(result: QueryResult) -> Judgement:
    """Run structural rules on a template QueryResult."""
    has_target = _has_resolved_target(result)
    hit_count = len(result.hits)
    evidence_count = _count_evidence(result)
    attribute_count = _count_attrs(result)
    relation_count = _count_relations(result)
    missing = _intent_missing(result)
    ambiguities = _collect_ambiguities(result)
    conflicts = _collect_conflicts(result)

    reasons: list[str] = []
    if result.empty_reason:
        reasons.append(f"empty_reason:{result.empty_reason}")
    for m in missing:
        reasons.append(f"missing:{m}")
    for a in ambiguities:
        reasons.append(f"ambiguity:{a}")
    for c in conflicts:
        reasons.append(f"conflict:{c}")
    if not has_target:
        reasons.append("no_resolved_target")
    if hit_count == 0:
        reasons.append("no_hits")
    if evidence_count == 0 and hit_count > 0:
        reasons.append("no_evidence")

    score = _score(
        has_target=has_target,
        hit_count=hit_count,
        evidence_count=evidence_count,
        missing=missing,
        ambiguities=ambiguities,
        conflicts=conflicts,
    )

    # Status thresholds (aligned with agent_kb_core spirit).
    if score >= 0.75 and not missing and not ambiguities:
        status: SufficiencyStatus = "sufficient"
    elif score >= 0.40 and (hit_count > 0 or has_target):
        status = "partial"
    else:
        status = "insufficient"

    # Downgrade sufficient if soft issues remain.
    if status == "sufficient" and (conflicts or evidence_count == 0):
        status = "partial"
        score = min(score, 0.72)

    knowledge_gaps: list[str] = []
    for m in missing:
        knowledge_gaps.append(m)
    if result.empty_reason and result.empty_reason not in knowledge_gaps:
        knowledge_gaps.append(result.empty_reason)

    # Semantic LLM only when not clearly sufficient.
    needs_semantic = status != "sufficient"

    strategy = _strategy(status, ambiguities=ambiguities, missing=missing)

    return Judgement(
        status=status,
        score=score,
        needs_semantic=needs_semantic,
        has_target=has_target,
        hit_count=hit_count,
        evidence_count=evidence_count,
        attribute_count=attribute_count,
        relation_count=relation_count,
        missing_requirements=list(missing),
        conflicts=list(conflicts),
        ambiguities=list(ambiguities),
        knowledge_gaps=list(dict.fromkeys(knowledge_gaps)),
        reasons=list(dict.fromkeys(reasons)),
        recommended_strategy=strategy,
        used_llm=False,
        semantic_notes=[],
        meta={
            "intent": result.intent,
            "template_id": result.template_id,
            "empty_reason": result.empty_reason,
        },
    )
