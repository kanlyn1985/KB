from __future__ import annotations

import json
import re
from pathlib import Path

from . import answer_policy
from .answer_policy import build_summary_lines, select_answer_policy
from .confidence import compute_confidence_score
from .config import AppPaths
from .db import connect
from .evidence_shapes import is_test_method_query, looks_like_test_method_blob
from .query_api import build_query_context
from .query_ambiguity import QueryAmbiguity, build_clarification_context, detect_query_ambiguity_with_kb
from .query_rewrite import RewrittenQuery, rewrite_query
from .answer_query_parsing import (
    _normalize_query_phrase,
    _extract_constraint_keywords,
    _normalize_standard_code,
    _extract_standard_from_query,
    _extract_exact_terms,
    _context_matches_exact_terms,
    _context_matches_protected_anchor_alias,
    _context_has_exact_definition_signal,
    _intent_from_query_type,
    _detect_intent,
    _extract_table_no_from_query,
    _is_timing_query,
    _is_activity_process_query,
    _special_appendix_c_requested,
    _rewritten_from_context,
)
from .answer_evidence_selection import _should_block_unconstrained_answer, _empty_context_from_judgement, _should_downgrade_for_insufficient_evidence, _build_insufficient_evidence_answer, _select_supporting_evidence, _rank_evidence
from .answer_utils import _string_list, _row_to_fact, _safe_json, _truncate, _clean_render_artifacts, _summarize_facts, _INTENT_FACT_TYPES
from .answer_context_routing import _choose_primary_doc_id, _restrict_context_to_doc, _load_document_record, _choose_doc_by_phrase_match
from .answer_subgraph import _apply_subgraph_fact_signals, _prioritize_subgraph_facts, _align_topics_to_answer, _filter_graph_edges, _filter_wiki_pages, _load_graph_edges_for_entities
from .answer_fact_ranking import _augment_facts, _rank_facts, _prioritize_judged_facts, _filter_facts_by_intent, _select_answer_facts
from .answer_process import _select_process_answer_facts, _matches_timing_answer_shape, _test_method_group_key
from .answer_standard import _select_standard_answer_facts
from .answer_definition import (
    _definition_answer_needs_section_fallback,
    _build_definition_from_section_intro,
    _build_definition_from_wiki,
    _build_approximate_definition_fallback,
    _definition_target_terms,
)
from .answer_parameter import (
    _select_parameter_meaning_answer_facts,
    _is_signal_state_query,
    _requested_voltage_value,
    _table_matches_signal_state,
    _parameter_focus_terms,
    _supplement_parameter_facts,
)
from .answer_constraint import (
    _constraint_answer_needs_topic_fallback,
    _build_constraint_from_topic_evidence,
    _constraint_target_terms,
)
from .answer_comparison import _select_comparison_answer_facts
from .ontology_adapter import (
    EntityConstraint,
    OntologySignal,
    post_check as _ontology_post_check,
)
from .requirements.router import try_answer_requirement_query


def answer_query(
    workspace_root: Path,
    query: str,
    limit: int = 8,
    preferred_doc_id: str | None = None,
) -> dict[str, object]:
    """Public entrypoint: answer a natural-language query against the KB.

    Orchestrates three stages: (1) resolve intent and prepare context, (2)
    gather and rank candidate facts/evidence/wiki, (3) compose the final
    answer with confidence scoring.
    """
    # requirement_router_mvp: opt-in soft route for customer/project requirement questions.
    requirement_answer = try_answer_requirement_query(workspace_root, query)
    if requirement_answer is not None:
        return requirement_answer

    routed = _resolve_intent_and_context(workspace_root, query, limit, preferred_doc_id)
    if routed is None:
        # Ambiguous query that requires clarification; the routing stage
        # already built the clarification response.
        raise RuntimeError("unreachable: _resolve_intent_and_context returned None without clarification")
    if isinstance(routed, dict) and routed.get("__clarification__"):
        return _clarification_response(query, preferred_doc_id, routed["ambiguity"])
    if not isinstance(routed, tuple):
        raise RuntimeError(f"unexpected routing result: {type(routed).__name__}")

    (
        context,
        rewritten,
        answer_mode,
        intent,
        primary_doc_id,
        blocked_by_judgement,
    ) = routed

    gathered = _gather_candidates(workspace_root, query, context, rewritten, answer_mode, intent, primary_doc_id, blocked_by_judgement)
    return _compose_final_answer(workspace_root, query, preferred_doc_id, context, rewritten, answer_mode, intent, primary_doc_id, blocked_by_judgement, gathered)


def _resolve_intent_and_context(
    workspace_root: Path,
    query: str,
    limit: int,
    preferred_doc_id: str | None,
) -> dict[str, object] | tuple[dict[str, object], object, str, str, str | None, bool]:
    """Stage 1: detect ambiguity, build context, choose answer mode and intent.

    Returns a `{"__clarification__": True, "ambiguity": ...}` dict when the
    query is ambiguous (caller should emit a clarification response).
    Otherwise returns a 6-tuple of routing state.
    """
    paths = AppPaths.from_root(workspace_root)
    ambiguity = detect_query_ambiguity_with_kb(query, paths.root / "ambiguity_index.json")
    if ambiguity:
        return {"__clarification__": True, "ambiguity": ambiguity}

    context = build_query_context(workspace_root, query, limit=limit, preferred_doc_id=preferred_doc_id)
    rewritten = _rewritten_from_context(query, context) or rewrite_query(query)
    answer_mode = select_answer_policy(rewritten.query_type, query, rewritten.to_dict())
    if answer_mode == "lifecycle_lookup" and _extract_standard_from_query(query) != query:
        answer_mode = "standard_lookup"
    intent = "parameter" if answer_mode == "parameter_meaning" else _intent_from_query_type(rewritten.query_type)
    if answer_mode == "standard_lookup":
        intent = "standard"
    exact_terms = _extract_exact_terms(query)
    if exact_terms and not _context_matches_exact_terms(context, exact_terms, rewritten.to_dict()):
        # Only zero out if there are truly no hits at all; otherwise keep
        # the context so the ranking layer can still surface relevant facts.
        if not context.get("hits") and not context.get("facts"):
            context = {
                "query": query,
                "hit_count": 0,
                "documents": [],
                "hits": [],
                "evidence": [],
                "facts": [],
                "entities": [],
                "graph_edges": [],
                "wiki_pages": [],
            }
    if rewritten.query_type == "comparison" and exact_terms and not _context_has_exact_definition_signal(context, exact_terms):
        context = {
            "query": query,
            "hit_count": 0,
            "documents": [],
            "hits": [],
            "evidence": [],
            "facts": [],
            "entities": [],
            "graph_edges": [],
            "wiki_pages": [],
        }
    blocked_by_judgement = _should_block_unconstrained_answer(context, exact_terms)
    if blocked_by_judgement:
        context = _empty_context_from_judgement(query, context)
    primary_doc_id = preferred_doc_id or _choose_primary_doc_id(workspace_root, query, context, intent)

    if primary_doc_id:
        context = _restrict_context_to_doc(workspace_root, context, primary_doc_id)

    return context, rewritten, answer_mode, intent, primary_doc_id, blocked_by_judgement


def _gather_candidates(
    workspace_root: Path,
    query: str,
    context: dict[str, object],
    rewritten: object,
    answer_mode: str,
    intent: str,
    primary_doc_id: str | None,
    blocked_by_judgement: bool,
) -> dict[str, object]:
    """Stage 2: rank facts, select evidence/wiki, derive summary lines.

    Returns a dict with all the intermediate state needed for stage 3.
    """
    documents = context.get("documents", [])
    facts = _apply_subgraph_fact_signals(context, context.get("facts", []), intent, query)
    facts = _rank_facts(facts, intent, query=query)
    facts = _prioritize_judged_facts(context, facts)
    if not blocked_by_judgement:
        facts = _augment_facts(workspace_root, documents, facts, rewritten.to_dict(), query, intent)
        facts = _prioritize_judged_facts(context, facts)
        # Re-rank after augment to incorporate _topic_match_bonus and _focus_term_bonus
        facts = _rank_facts(facts, intent, query=query)
    facts = _filter_facts_by_intent(facts, intent)
    facts = facts[:20]
    evidence = _select_supporting_evidence(workspace_root, facts, query, intent)
    if not evidence:
        evidence = _rank_evidence(context.get("evidence", []), query, intent)[:5]
    wiki_pages = _filter_wiki_pages(context.get("wiki_pages", []), facts, query, intent)

    fact_summaries = _summarize_facts(facts[:5], intent=intent)
    summary_lines = [_clean_render_artifacts(line) for line in build_summary_lines(
        policy=answer_mode,
        documents=documents,
        facts=facts,
        evidence=evidence,
        fact_summaries=fact_summaries,
    )]

    answer_facts = _select_answer_facts(
        facts,
        intent,
        query,
        context.get("knowledge_subgraph", {}),
        rewritten.to_dict(),
        answer_mode,
    )
    fact_items = [
        {
            "fact_id": item["fact_id"],
            "fact_type": item["fact_type"],
            "predicate": item["predicate"],
            "object": item["object_value"],
            "confidence": item["confidence"],
            "doc_id": item["source_doc_id"],
            "page_no": item.get("qualifiers_json", {}).get("page_no") if isinstance(item.get("qualifiers_json"), dict) else None,
        }
        for item in answer_facts[:12]
    ]
    evidence_items = [
        {
            "evidence_id": item["evidence_id"],
            "doc_id": item["doc_id"],
            "page_no": item["page_no"],
            "confidence": item["confidence"],
            "snippet": _truncate(_clean_render_artifacts(str(item["normalized_text"] or "")), 600),
        }
        for item in evidence[:5]
    ]
    graph_edges = _filter_graph_edges(
        workspace_root,
        context.get("graph_edges", []),
        answer_facts,
        intent,
        primary_doc_id,
        context.get("knowledge_subgraph", {}),
    )

    return {
        "documents": documents,
        "facts": facts,
        "evidence": evidence,
        "wiki_pages": wiki_pages,
        "summary_lines": summary_lines,
        "answer_facts": answer_facts,
        "fact_items": fact_items,
        "evidence_items": evidence_items,
        "graph_edges": graph_edges,
    }


def _compose_final_answer(
    workspace_root: Path,
    query: str,
    preferred_doc_id: str | None,
    context: dict[str, object],
    rewritten: object,
    answer_mode: str,
    intent: str,
    primary_doc_id: str | None,
    blocked_by_judgement: bool,
    gathered: dict[str, object],
) -> dict[str, object]:
    """Stage 3: build direct_answer, apply fallbacks, score, return the result envelope."""
    documents: list[dict[str, object]] = gathered["documents"]  # type: ignore[assignment]
    facts: list[dict[str, object]] = gathered["facts"]  # type: ignore[assignment]
    evidence: list[dict[str, object]] = gathered["evidence"]  # type: ignore[assignment]
    wiki_pages: list[dict[str, object]] = gathered["wiki_pages"]  # type: ignore[assignment]
    summary_lines: list[str] = list(gathered["summary_lines"])  # type: ignore[arg-type]
    answer_facts: list[dict[str, object]] = gathered["answer_facts"]  # type: ignore[assignment]
    fact_items: list[dict[str, object]] = list(gathered["fact_items"])  # type: ignore[assignment]
    evidence_items: list[dict[str, object]] = list(gathered["evidence_items"])  # type: ignore[assignment]
    graph_edges: list[dict[str, object]] = list(gathered["graph_edges"])  # type: ignore[assignment]

    fallback_reason = ""
    warnings: list[str] = []
    for doc in documents:
        if doc.get("quality_status") in {"review_required", "blocked"}:
            warnings.append(
                f"{doc['doc_id']} 质量状态为 {doc['quality_status']}，回答应回看原始证据。"
            )

    direct_answer = answer_policy.build_direct_answer(
        answer_policy.DirectAnswerContext(
            policy=answer_mode,
            query=query,
            facts=fact_items,
            evidence=evidence_items,
            wiki_pages=wiki_pages,
            standard_normalizer=_normalize_standard_code,
            standard_extractor=_extract_standard_from_query,
            truncate_fn=_truncate,
        )
    )
    if intent == "definition" and _definition_answer_needs_section_fallback(answer_facts, rewritten.to_dict()):
        section_answer = _build_definition_from_section_intro(
            workspace_root,
            rewritten.to_dict(),
            primary_doc_id,
        )
        if section_answer:
            direct_answer = section_answer
    if direct_answer == "没有找到足够的结构化结果。" and intent == "definition":
        wiki_fallback = _build_definition_from_wiki(workspace_root, wiki_pages)
        if wiki_fallback:
            direct_answer = wiki_fallback
            fallback_reason = "fallback_to_wiki_definition"
    if direct_answer == "没有找到足够的结构化结果。" and intent == "definition":
        approximate_answer, approximate_reason = _build_approximate_definition_fallback(
            workspace_root,
            rewritten.to_dict(),
            context,
        )
        if approximate_answer:
            direct_answer = approximate_answer
            fallback_reason = approximate_reason
    if blocked_by_judgement:
        fallback_reason = "insufficient_evidence_for_exact_anchor"
    if intent == "constraint" and (
        direct_answer == "没有找到足够的结构化结果。"
        or direct_answer.startswith("最相关的结构化结果是章节")
        or _constraint_answer_needs_topic_fallback(rewritten.to_dict(), answer_facts)
    ):
        topic_evidence_answer = _build_constraint_from_topic_evidence(
            workspace_root,
            rewritten.to_dict(),
            context.get("wiki_pages", []),
            primary_doc_id,
        )
        if topic_evidence_answer:
            direct_answer = topic_evidence_answer
    direct_answer = _clean_render_artifacts(direct_answer)
    # When no hits at all and answer is generic fallback, surface a clear "not found" message
    if not fact_items and not evidence_items and direct_answer == "没有找到足够的结构化结果。":
        direct_answer = "知识库中未找到与该查询相关的信息。"
    # Parameter intent: supplement missing requirement/threshold facts when parameter_value
    # doesn't cover the query topic (e.g., "效率" has no parameter_value, only requirement)
    if intent == "parameter" and workspace_root:
        _supplement_parameter_facts(query, fact_items, workspace_root)
    if _should_downgrade_for_insufficient_evidence(context, answer_mode, fallback_reason, rewritten.query_type):
        direct_answer = _build_insufficient_evidence_answer(context)
        summary_lines = [direct_answer]
        fact_items = []
        evidence_items = []
        graph_edges = []
        wiki_pages = []
        aligned_topic_objects: list[dict[str, object]] = []
        aligned_topic_entities: list[dict[str, object]] = []
        fallback_reason = "insufficient_evidence"
        warnings.append("证据裁判判定当前候选不足，已阻断确定性答案输出。")
    else:
        aligned_topic_objects, aligned_topic_entities = _align_topics_to_answer(
            rewritten.to_dict(),
            answer_facts,
            direct_answer=direct_answer,
            topic_objects=context.get("topic_objects", []),
            topic_entities=context.get("topic_entities", []),
            all_entities=context.get("entities", []),
        )
    confidence_score = compute_confidence_score(
        answer_mode=answer_mode,
        direct_answer=direct_answer,
        supporting_facts=fact_items[:3],
        supporting_evidence=evidence_items[:2],
        warnings=warnings,
    )

    # --- Ontology guard post-check (Sprint 2 WP4) ---
    # Read-only consistency audit of the produced answer. Runs ONLY in guard
    # mode. It produces warnings but MUST NOT mutate direct_answer; the
    # answer_changed_by_ontology flag stays False for the whole of Sprint 2.
    ontology_signal_raw = context.get("ontology_signal") or {}
    ontology_mode = str(ontology_signal_raw.get("mode") or "off")
    ontology_post_checks: list[dict[str, object]] = []
    answer_changed_by_ontology = False
    ontology_post_check_status = "skipped"
    if ontology_mode == "guard":
        try:
            signal = OntologySignal(
                mode=ontology_mode,
                query_entities=[
                    EntityConstraint(
                        mention=str(e.get("mention") or ""),
                        class_id=e.get("class_id"),
                        class_name=e.get("class_name"),
                        confidence=float(e.get("confidence") or 0.0),
                    )
                    for e in ontology_signal_raw.get("query_entities", [])
                ],
            )
            checks = _ontology_post_check(
                query, direct_answer, signal, workspace_root=workspace_root
            )
            ontology_post_checks = [
                {"type": c.type, "severity": c.severity, "message": c.message}
                for c in checks
            ]
            ontology_post_check_status = "completed"
            # Sprint 3 WP6: surface guard post-checks into the answer warnings
            # array as observable entries (source=ontology_guard). These are
            # observation-only: changed_answer stays False and direct_answer is
            # never mutated. Existing string warnings are preserved alongside.
            for c in checks:
                warnings.append(
                    {
                        "source": "ontology_guard",
                        "type": c.type,
                        "severity": c.severity,
                        "message": c.message,
                        "changed_answer": False,
                    }
                )
        except Exception as exc:  # pragma: no cover - defensive, never blocks
            ontology_post_check_status = f"error: {exc}"

    return {
        "query": query,
        "rewrite": rewritten.to_dict(),
        "debug_query": {
            "final_query_type": rewritten.query_type,
            "final_normalized_query": rewritten.normalized_query,
            "final_target_topic": rewritten.target_topic,
            "protected_anchor_terms": rewritten.protected_anchor_terms,
            "rewrite_override_applied": rewritten.rewrite_override_applied,
            "semantic_quality_flags": rewritten.semantic_quality_flags,
        },
        "preferred_doc_id": preferred_doc_id,
        "answer_mode": answer_mode,
        "confidence_score": confidence_score,
        "direct_answer": direct_answer,
        "summary": summary_lines,
        "supporting_facts": fact_items[:3],
        "supporting_evidence": evidence_items[:2],
        "related_graph_edges": graph_edges[:4],
        "related_wiki_pages": wiki_pages[:3],
        "topic_objects": aligned_topic_objects[:5],
        "topic_entities": aligned_topic_entities[:5],
        "warnings": warnings,
        "fallback_reason": fallback_reason,
        "ontology_post_check_status": ontology_post_check_status,
        "ontology_post_checks": ontology_post_checks,
        "answer_changed_by_ontology": answer_changed_by_ontology,
        "hit_count": len(fact_items) + len(evidence_items),
        "facts": fact_items,
        "evidence": evidence_items,
        "context": context,
    }


def _clarification_response(
    query: str,
    preferred_doc_id: str | None,
    ambiguity: QueryAmbiguity,
) -> dict[str, object]:
    clarification = ambiguity.to_dict()
    context = build_clarification_context(query, preferred_doc_id, ambiguity)
    direct_answer = ambiguity.question + "\n" + "\n".join(
        f"{index}. {option.label}：{option.description}"
        for index, option in enumerate(ambiguity.options, 1)
    )
    return {
        "query": query,
        "rewrite": context["rewrite"],
        "debug_query": context["debug_query"],
        "preferred_doc_id": preferred_doc_id,
        "answer_mode": "clarification",
        "confidence_score": {
            "score": 0.0,
            "level": "needs_clarification",
            "reasons": [ambiguity.reason],
        },
        "direct_answer": direct_answer,
        "summary": [ambiguity.question],
        "supporting_facts": [],
        "supporting_evidence": [],
        "related_graph_edges": [],
        "related_wiki_pages": [],
        "topic_objects": [],
        "topic_entities": [],
        "warnings": [],
        "fallback_reason": "clarification_required",
        "clarification_required": True,
        "clarification": clarification,
        "context": context,
    }



