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
from .query_ambiguity import QueryAmbiguity, detect_query_ambiguity
from .query_rewrite import RewrittenQuery, rewrite_query


def answer_query(
    workspace_root: Path,
    query: str,
    limit: int = 8,
    preferred_doc_id: str | None = None,
) -> dict[str, object]:
    ambiguity = detect_query_ambiguity(query)
    if ambiguity:
        return _clarification_response(query, preferred_doc_id, ambiguity)

    context = build_query_context(workspace_root, query, limit=limit, preferred_doc_id=preferred_doc_id)
    rewritten = _rewritten_from_context(query, context) or rewrite_query(query)
    answer_mode = select_answer_policy(rewritten.query_type, query, rewritten.to_dict())
    intent = "parameter" if answer_mode == "parameter_meaning" else _intent_from_query_type(rewritten.query_type)
    exact_terms = _extract_exact_terms(query)
    if exact_terms and not _context_matches_exact_terms(context, exact_terms, rewritten.to_dict()):
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

    documents = context.get("documents", [])
    facts = _apply_subgraph_fact_signals(context, context.get("facts", []), intent, query)
    facts = _rank_facts(facts, intent, query=query)
    facts = _prioritize_judged_facts(context, facts)
    if not blocked_by_judgement:
        facts = _augment_facts(workspace_root, documents, facts, rewritten.to_dict(), query, intent)
        facts = _prioritize_judged_facts(context, facts)
    evidence = _select_supporting_evidence(workspace_root, facts, query, intent)
    if not evidence:
        evidence = _rank_evidence(context.get("evidence", []), query, intent)[:5]
    wiki_pages = _filter_wiki_pages(context.get("wiki_pages", []), facts, query, intent)

    fact_summaries = _summarize_facts(facts[:5], intent=intent)
    summary_lines = build_summary_lines(
        policy=answer_mode,
        documents=documents,
        facts=facts,
        evidence=evidence,
        fact_summaries=fact_summaries,
    )

    fallback_reason = ""
    warnings: list[str] = []
    for doc in documents:
        if doc.get("quality_status") in {"review_required", "blocked"}:
            warnings.append(
                f"{doc['doc_id']} 质量状态为 {doc['quality_status']}，回答应回看原始证据。"
            )

    evidence_items = [
        {
            "evidence_id": item["evidence_id"],
            "doc_id": item["doc_id"],
            "page_no": item["page_no"],
            "confidence": item["confidence"],
            "snippet": _truncate(item["normalized_text"], 600),
        }
        for item in evidence[:5]
    ]

    answer_facts = _select_answer_facts(
        facts,
        intent,
        query,
        context.get("knowledge_subgraph", {}),
        rewritten.to_dict(),
        answer_mode,
    )
    aligned_topic_objects, aligned_topic_entities = _align_topics_to_answer(
        rewritten.to_dict(),
        answer_facts,
        direct_answer="",
        topic_objects=context.get("topic_objects", []),
        topic_entities=context.get("topic_entities", []),
        all_entities=context.get("entities", []),
    )
    graph_edges = _filter_graph_edges(
        workspace_root,
        context.get("graph_edges", []),
        answer_facts,
        intent,
        primary_doc_id,
        context.get("knowledge_subgraph", {}),
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

    direct_answer = answer_policy.build_direct_answer(
        policy=answer_mode,
        query=query,
        facts=fact_items,
        evidence=evidence_items,
        wiki_pages=wiki_pages,
        standard_normalizer=_normalize_standard_code,
        standard_extractor=_extract_standard_from_query,
        truncate_fn=_truncate,
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
        "context": context,
    }


def _clarification_response(
    query: str,
    preferred_doc_id: str | None,
    ambiguity: QueryAmbiguity,
) -> dict[str, object]:
    clarification = ambiguity.to_dict()
    direct_answer = ambiguity.question + "\n" + "\n".join(
        f"{index}. {option.label}：{option.description}"
        for index, option in enumerate(ambiguity.options, 1)
    )
    return {
        "query": query,
        "rewrite": {
            "original_query": query.strip(),
            "normalized_query": ambiguity.anchor,
            "query_type": "clarification",
            "target_topic": ambiguity.anchor,
            "aliases": [],
            "must_terms": [ambiguity.anchor],
            "should_terms": [],
            "negative_terms": [],
            "protected_anchor_terms": [ambiguity.anchor],
            "rewrite_override_applied": False,
            "semantic_quality_flags": ["ambiguous_short_acronym"],
        },
        "debug_query": {
            "final_query_type": "clarification",
            "final_normalized_query": ambiguity.anchor,
            "final_target_topic": ambiguity.anchor,
            "protected_anchor_terms": [ambiguity.anchor],
            "rewrite_override_applied": False,
            "semantic_quality_flags": ["ambiguous_short_acronym"],
        },
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
        "context": {
            "query": query,
            "hit_count": 0,
            "documents": [],
            "hits": [],
            "evidence": [],
            "facts": [],
            "entities": [],
            "graph_edges": [],
            "wiki_pages": [],
            "evidence_judgement": {
                "sufficient": False,
                "confidence": 0.0,
                "matched_anchors": [],
                "missing_anchors": [ambiguity.anchor],
                "best_evidence_ids": [],
                "best_fact_ids": [],
                "rejected_reasons": [ambiguity.reason],
                "suggested_followup_queries": [option.example_query for option in ambiguity.options],
                "reason": "query requires user clarification before retrieval",
                "judge_source": "ambiguity_detector",
                "used_llm": False,
                "prompt_version": "",
            },
            "clarification_required": True,
            "clarification": clarification,
        },
    }


def _should_block_unconstrained_answer(context: dict[str, object], exact_terms: list[str]) -> bool:
    if not exact_terms:
        return False
    judgement = context.get("evidence_judgement")
    if not isinstance(judgement, dict):
        return False
    if bool(judgement.get("sufficient")):
        return False
    missing = {str(item).upper() for item in judgement.get("missing_anchors") or []}
    requested = {term.upper() for term in exact_terms}
    best_fact_ids = [str(item) for item in judgement.get("best_fact_ids") or [] if item]
    best_evidence_ids = [str(item) for item in judgement.get("best_evidence_ids") or [] if item]
    return bool(missing & requested) or (not best_fact_ids and not best_evidence_ids)


def _empty_context_from_judgement(query: str, context: dict[str, object]) -> dict[str, object]:
    return {
        "query": query,
        "hit_count": 0,
        "documents": [],
        "hits": [],
        "evidence": [],
        "facts": [],
        "entities": [],
        "graph_edges": [],
        "wiki_pages": [],
        "evidence_judgement": context.get("evidence_judgement"),
    }


def _rewritten_from_context(query: str, context: dict[str, object]) -> RewrittenQuery | None:
    payload = context.get("rewrite")
    if not isinstance(payload, dict):
        return None
    try:
        return RewrittenQuery(
            original_query=str(payload.get("original_query") or query).strip(),
            normalized_query=str(payload.get("normalized_query") or query).strip(),
            query_type=str(payload.get("query_type") or "general_search").strip(),
            target_topic=str(payload.get("target_topic") or "").strip(),
            aliases=_string_list(payload.get("aliases")),
            must_terms=_string_list(payload.get("must_terms")),
            should_terms=_string_list(payload.get("should_terms")),
            negative_terms=_string_list(payload.get("negative_terms")),
            protected_anchor_terms=_string_list(payload.get("protected_anchor_terms")),
            rewrite_override_applied=bool(payload.get("rewrite_override_applied")),
            semantic_quality_flags=_string_list(payload.get("semantic_quality_flags")),
        )
    except Exception:
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _intent_from_query_type(query_type: str) -> str:
    if query_type in {"definition"}:
        return "definition"
    if query_type in {"standard_lookup"}:
        return "standard"
    if query_type in {"lifecycle_lookup", "timing_lookup", "test_method_lookup"}:
        return "process"
    if query_type in {"parameter_lookup"}:
        return "parameter"
    if query_type in {"constraint"}:
        return "constraint"
    if query_type in {"comparison"}:
        return "comparison"
    return "general"


def _choose_primary_doc_id(workspace_root: Path, query: str, context: dict[str, object], intent: str) -> str | None:
    documents = context.get("documents", [])
    if not documents:
        return None

    if intent == "standard":
        normalized_query = _normalize_standard_code(_extract_standard_from_query(query))
        paths = AppPaths.from_root(workspace_root)
        connection = connect(paths.db_file)
        try:
            rows = connection.execute(
                """
                SELECT source_doc_id, object_value
                FROM facts
                WHERE fact_type = 'document_standard'
                """
            ).fetchall()
            for row in rows:
                payload = _safe_json(row["object_value"])
                if isinstance(payload, dict):
                    value = _normalize_standard_code(str(payload.get("value", "")))
                    if value and value == normalized_query:
                        return row["source_doc_id"]
            rows = connection.execute(
                """
                SELECT json_extract(source_doc_ids_json, '$[0]') AS doc_id, title
                FROM wiki_pages
                WHERE page_type = 'standard'
                """
            ).fetchall()
            for row in rows:
                if _normalize_standard_code(str(row["title"])) == normalized_query:
                    return row["doc_id"]
        finally:
            connection.close()

    judged_doc_id = _choose_doc_from_evidence_judgement(context)
    if judged_doc_id:
        return judged_doc_id

    routed_doc_id = _choose_doc_from_routed_hits(context)
    if routed_doc_id:
        return routed_doc_id

    normalized_phrase = _normalize_query_phrase(query)
    if normalized_phrase:
        best_doc_id = _choose_doc_by_phrase_match(workspace_root, normalized_phrase, intent)
        if best_doc_id:
            return best_doc_id

    return documents[0]["doc_id"]


def _choose_doc_from_evidence_judgement(context: dict[str, object]) -> str | None:
    judgement = context.get("evidence_judgement")
    if not isinstance(judgement, dict) or not judgement.get("sufficient"):
        return None

    best_fact_ids = [str(item).strip() for item in judgement.get("best_fact_ids") or [] if str(item).strip()]
    if not best_fact_ids:
        return None

    fact_docs: dict[str, str] = {}
    for fact in context.get("facts", []):
        if not isinstance(fact, dict):
            continue
        fact_id = str(fact.get("fact_id") or "").strip()
        doc_id = str(fact.get("source_doc_id") or "").strip()
        if fact_id and doc_id:
            fact_docs[fact_id] = doc_id
    for hit in context.get("hits", []):
        if not isinstance(hit, dict) or hit.get("result_type") != "fact":
            continue
        fact_id = str(hit.get("result_id") or "").strip()
        doc_id = str(hit.get("doc_id") or "").strip()
        if fact_id and doc_id:
            fact_docs.setdefault(fact_id, doc_id)

    doc_scores: dict[str, tuple[int, float]] = {}
    for index, fact_id in enumerate(best_fact_ids):
        doc_id = fact_docs.get(fact_id)
        if not doc_id:
            continue
        count, score = doc_scores.get(doc_id, (0, 0.0))
        rank_bonus = max(0.0, 1.0 - index * 0.1)
        doc_scores[doc_id] = (count + 1, score + rank_bonus)
    if not doc_scores:
        return None
    return sorted(doc_scores.items(), key=lambda pair: (-pair[1][0], -pair[1][1], pair[0]))[0][0]


def _choose_doc_from_routed_hits(context: dict[str, object]) -> str | None:
    routed_hits = _query_specific_doc_hits(context)
    if not routed_hits:
        routed_hits = [
            item for item in context.get("graph_candidates", [])
            if str(item.get("doc_id") or "").strip()
        ]
    if not routed_hits:
        return None

    doc_scores: dict[str, tuple[int, float]] = {}
    for index, item in enumerate(routed_hits[:10]):
        doc_id = str(item.get("doc_id") or "").strip()
        if not doc_id:
            continue
        count, score = doc_scores.get(doc_id, (0, 0.0))
        rank_bonus = max(0.0, 1.0 - index * 0.05)
        doc_scores[doc_id] = (count + 1, score + float(item.get("score") or 0.0) + rank_bonus)
    if not doc_scores:
        return None
    return sorted(doc_scores.items(), key=lambda pair: (-pair[1][0], -pair[1][1], pair[0]))[0][0]


def _query_specific_doc_hits(context: dict[str, object]) -> list[dict[str, object]]:
    hits = [
        item for item in context.get("hits", [])[:10]
        if isinstance(item, dict) and str(item.get("doc_id") or "").strip()
    ]
    direct_hits = [
        item for item in hits
        if item.get("channel") == "routing_summary"
        or "routing_summary" in {str(channel) for channel in item.get("channels", [])}
    ]
    if direct_hits:
        return direct_hits
    return [
        item for item in hits
        if item.get("channel") == "graph"
        or "graph" in {str(channel) for channel in item.get("channels", [])}
    ]


def _restrict_context_to_doc(workspace_root: Path, context: dict[str, object], doc_id: str) -> dict[str, object]:
    filtered = dict(context)
    documents = [item for item in context.get("documents", []) if item.get("doc_id") == doc_id]
    if not documents:
        filtered["documents"] = [_load_document_record(workspace_root, doc_id)]
    else:
        filtered["documents"] = documents
    filtered["hits"] = [item for item in context.get("hits", []) if item.get("doc_id") == doc_id]
    filtered["evidence"] = [item for item in context.get("evidence", []) if item.get("doc_id") == doc_id]
    filtered["facts"] = [item for item in context.get("facts", []) if item.get("source_doc_id") == doc_id]
    filtered["wiki_pages"] = [
        item for item in context.get("wiki_pages", [])
        if item.get("page_id") in {hit["result_id"] for hit in filtered["hits"] if hit.get("result_type") == "wiki"}
        or item.get("entity_id") in {
            fact.get("subject_entity_id") for fact in filtered["facts"] if fact.get("subject_entity_id")
        } | {
            fact.get("object_entity_id") for fact in filtered["facts"] if fact.get("object_entity_id")
        }
    ]
    filtered["entities"] = [
        item for item in context.get("entities", [])
        if item.get("entity_id") in {
            fact.get("subject_entity_id") for fact in filtered["facts"] if fact.get("subject_entity_id")
        } | {
            fact.get("object_entity_id") for fact in filtered["facts"] if fact.get("object_entity_id")
        }
    ]
    filtered["graph_edges"] = [
        item for item in context.get("graph_edges", [])
        if item.get("version_scope") == doc_id
    ]
    filtered["topic_objects"] = [
        item for item in context.get("topic_objects", [])
        if item.get("page_id") in {wiki.get("page_id") for wiki in filtered["wiki_pages"]}
        or str(item.get("page_id") or "").startswith(f"WCONTOP-{doc_id}-")
        or str(item.get("page_id") or "").startswith(f"WCON-{doc_id}-")
        or str(item.get("page_id") or "").startswith(f"WCMP-{doc_id}-")
        or str(item.get("page_id") or "").startswith(f"WPROC-{doc_id}-")
        or str(item.get("page_id") or "").startswith(f"WPAR-{doc_id}-")
    ]
    filtered["knowledge_subgraph"] = {
        **dict(context.get("knowledge_subgraph") or {}),
        "seed_wiki_page_ids": [item.get("page_id") for item in filtered["wiki_pages"][:8] if item.get("page_id")],
        "seed_entity_ids": sorted({
            *(item.get("entity_id") for item in filtered["entities"] if item.get("entity_id")),
        })[:20],
        "seed_fact_ids": [item.get("fact_id") for item in filtered["facts"][:80] if item.get("fact_id")],
        "seed_edge_ids": [item.get("edge_id") for item in filtered["graph_edges"][:80] if item.get("edge_id")],
        "wiki_page_types": sorted({
            str(item.get("page_type") or "").strip()
            for item in filtered["wiki_pages"]
            if str(item.get("page_type") or "").strip()
        }),
        "topic_object_ids": [item.get("page_id") for item in filtered["topic_objects"][:8] if item.get("page_id")],
        "fact_count": len(filtered["facts"]),
        "edge_count": len(filtered["graph_edges"]),
        "wiki_count": len(filtered["wiki_pages"]),
        "topic_count": len(filtered["topic_objects"]),
    }
    filtered["hit_count"] = len(filtered["hits"])
    return filtered


def _load_document_record(workspace_root: Path, doc_id: str) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        row = connection.execute(
            """
            SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        return dict(row) if row else {"doc_id": doc_id}
    finally:
        connection.close()


def _detect_intent(query: str) -> str:
    if re.search(r"\b(?:GB|GBT|GB/T|ISO|IEC|QC|QC/T)\b", query, re.I):
        return "standard"
    if re.search(r"(什么是|是什么|定义|怎么定义|如何定义|是怎么定义的|如何理解|怎么理解)", query):
        return "definition"
    return "general"


def _augment_facts(
    workspace_root: Path,
    documents: list[dict[str, object]],
    facts: list[dict[str, object]],
    rewritten_payload: dict[str, object],
    query: str,
    intent: str,
) -> list[dict[str, object]]:
    if not documents:
        return facts

    doc_id = documents[0]["doc_id"]
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)

    try:
        extra: list[dict[str, object]] = []
        if intent == "standard":
            rows = connection.execute(
                """
                SELECT fact_id, fact_type, predicate, object_value, confidence,
                       source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                FROM facts
                WHERE source_doc_id = ?
                  AND fact_type IN ('document_standard', 'document_versioning', 'document_lifecycle')
                ORDER BY fact_id
                """,
                (doc_id,),
            ).fetchall()
            extra = [_row_to_fact(row) for row in rows]
        elif intent == "definition":
            normalized_query = _normalize_query_phrase(query)
            target_terms = _definition_target_terms(query, rewritten_payload)
            preferred_doc_ids = [item.get("doc_id") for item in documents if item.get("doc_id")]
            search_doc_ids = preferred_doc_ids or [doc_id]
            placeholders = ",".join("?" for _ in search_doc_ids)
            like_clauses = " OR ".join("object_value LIKE ?" for _ in target_terms[:6])
            if not like_clauses:
                like_clauses = "object_value LIKE ?"
                target_terms = [normalized_query]
            rows = connection.execute(
                f"""
                SELECT fact_id, fact_type, predicate, object_value, confidence,
                       source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                FROM facts
                WHERE source_doc_id IN ({placeholders})
                  AND fact_type IN ('term_definition', 'concept_definition', 'document_abstract')
                  AND ({like_clauses})
                ORDER BY confidence DESC, fact_id ASC
                LIMIT 12
                """,
                [*search_doc_ids, *[f"%{term}%" for term in target_terms[:6]]],
            ).fetchall()
            extra = [_row_to_fact(row) for row in rows]
        elif intent == "parameter":
            normalized_query = _normalize_query_phrase(query)
            focus_terms = _parameter_focus_terms(query, rewritten_payload)
            relevant_pages = _find_relevant_pages_for_query(
                connection,
                doc_id,
                focus_terms,
            )
            rows = connection.execute(
                """
                SELECT fact_id, fact_type, predicate, object_value, confidence,
                       source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                FROM facts
                WHERE source_doc_id = ?
                  AND fact_type IN ('parameter_value', 'table_requirement', 'threshold', 'requirement')
                ORDER BY
                    CASE fact_type
                        WHEN 'parameter_value' THEN 0
                        WHEN 'table_requirement' THEN 1
                        WHEN 'threshold' THEN 2
                        ELSE 3
                    END,
                    confidence DESC,
                    fact_id ASC
                LIMIT 240
                """,
                (doc_id,),
            ).fetchall()
            if _is_signal_state_query(query):
                requested_voltage = _requested_voltage_value(query)
                targeted_rows = connection.execute(
                    """
                    SELECT fact_id, fact_type, predicate, object_value, confidence,
                           source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                    FROM facts
                    WHERE source_doc_id = ?
                      AND fact_type = 'table_requirement'
                      AND object_value LIKE '%PWM%'
                      AND object_value LIKE '%状态%'
                      AND object_value LIKE ?
                    ORDER BY confidence DESC, fact_id ASC
                    LIMIT 20
                    """,
                    (doc_id, f"%{requested_voltage}%" if requested_voltage else "%"),
                ).fetchall()
                rows = [*targeted_rows, *rows]
            extra = []
            for row in rows:
                fact = _row_to_fact(row)
                qualifiers = fact.get("qualifiers_json")
                page_no = None
                if isinstance(qualifiers, dict):
                    page_no = int(qualifiers.get("page_no") or 0)
                payload = fact.get("object_value")
                blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
                focus_bonus = _focus_term_bonus(blob, focus_terms)
                if focus_bonus:
                    fact["_focus_term_bonus"] = focus_bonus
                if page_no and page_no in relevant_pages:
                    fact["_page_focus_bonus"] = 2.0
                if any(term and term in blob for term in [normalized_query, *focus_terms]):
                    extra.append(fact)
                    continue
                if page_no and page_no in relevant_pages:
                    extra.append(fact)
        elif intent == "process":
            normalized_query = _normalize_query_phrase(query)
            test_method_query = is_test_method_query(query)
            rows = connection.execute(
                """
                SELECT fact_id, fact_type, predicate, object_value, confidence,
                       source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                FROM facts
                WHERE source_doc_id = ?
                  AND fact_type IN ('process_fact', 'transition_fact', 'table_requirement', 'requirement')
                ORDER BY
                    CASE fact_type
                        WHEN 'transition_fact' THEN 0
                        WHEN 'process_fact' THEN 1
                        WHEN 'table_requirement' THEN 2
                        ELSE 3
                    END,
                    confidence DESC,
                    fact_id ASC
                LIMIT 160
                """,
                (doc_id,),
            ).fetchall()
            extra = []
            focus_terms = [
                normalized_query,
                *[str(item) for item in rewritten_payload.get("must_terms", [])],
                *[str(item) for item in rewritten_payload.get("aliases", [])],
                *[str(item) for item in rewritten_payload.get("should_terms", [])],
            ]
            for row in rows:
                fact = _row_to_fact(row)
                payload = fact.get("object_value")
                blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
                if test_method_query:
                    if looks_like_test_method_blob(query, blob):
                        extra.append(fact)
                    continue
                if any(term and term in blob for term in focus_terms):
                    extra.append(fact)
                    continue
                if any(token in blob for token in ("时序", "状态", "流程", "握手", "预充", "停机")):
                    extra.append(fact)
        elif intent == "comparison":
            normalized_query = _normalize_query_phrase(query)
            rows = connection.execute(
                """
                SELECT fact_id, fact_type, predicate, object_value, confidence,
                       source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                FROM facts
                WHERE source_doc_id = ?
                  AND fact_type IN ('comparison_relation', 'term_definition', 'concept_definition')
                ORDER BY
                    CASE fact_type
                        WHEN 'comparison_relation' THEN 0
                        ELSE 1
                    END,
                    confidence DESC,
                    fact_id ASC
                LIMIT 80
                """,
                (doc_id,),
            ).fetchall()
            extra = []
            comparison_terms = [
                normalized_query,
                *[str(item) for item in rewritten_payload.get("must_terms", [])],
                *[str(item) for item in rewritten_payload.get("aliases", [])],
                *[str(item) for item in rewritten_payload.get("should_terms", [])],
            ]
            for row in rows:
                fact = _row_to_fact(row)
                payload = fact.get("object_value")
                blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
                if any(term and term in blob for term in comparison_terms):
                    extra.append(fact)
                    continue
                if fact.get("fact_type") == "comparison_relation" and any(token in blob.upper() for token in ("V2X", "V2G", "V2V", "V2B", "V2H")):
                    extra.append(fact)
        elif intent == "constraint":
            normalized_query = _normalize_query_phrase(query)
            rows = connection.execute(
                """
                SELECT fact_id, fact_type, predicate, object_value, confidence,
                       source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                FROM facts
                WHERE source_doc_id = ?
                  AND fact_type IN ('threshold', 'requirement', 'table_requirement')
                ORDER BY
                    CASE fact_type
                        WHEN 'threshold' THEN 0
                        WHEN 'requirement' THEN 1
                        ELSE 2
                    END,
                    confidence DESC,
                    fact_id ASC
                LIMIT 120
                """,
                (doc_id,),
            ).fetchall()
            extra = []
            constraint_terms = [
                normalized_query,
                *[str(item) for item in rewritten_payload.get("must_terms", [])],
                *[str(item) for item in rewritten_payload.get("aliases", [])],
                *[str(item) for item in rewritten_payload.get("should_terms", [])],
            ]
            for row in rows:
                fact = _row_to_fact(row)
                payload = fact.get("object_value")
                blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
                if isinstance(payload, dict) and str(payload.get("scope_type") or "") in {"index", "preface"}:
                    continue
                if any(token in blob for token in ("前言", "前    言", "目 次", "目次")):
                    continue
                if any(term and term in blob for term in constraint_terms):
                    extra.append(fact)
                    continue
                if any(token in blob for token in ("要求", "应", "不应", "必须", "切断", "急停", "锁止")):
                    extra.append(fact)
        else:
            normalized_query = _normalize_query_phrase(query)
            if re.search(r"(CC|阻值|电阻|参数值)", query, re.I):
                parameter_rows = connection.execute(
                    """
                    SELECT fact_id, fact_type, predicate, object_value, confidence,
                           source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                    FROM facts
                    WHERE source_doc_id = ?
                      AND fact_type = 'parameter_value'
                    ORDER BY confidence DESC, fact_id ASC
                    LIMIT 20
                    """,
                    (doc_id,),
                ).fetchall()
                supplemental_rows = connection.execute(
                    """
                    SELECT fact_id, fact_type, predicate, object_value, confidence,
                           source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                    FROM facts
                    WHERE source_doc_id = ?
                      AND fact_type IN ('table_requirement', 'requirement', 'threshold')
                    ORDER BY confidence DESC, fact_id ASC
                    LIMIT 30
                    """,
                    (doc_id,),
                ).fetchall()
                rows = [*parameter_rows, *supplemental_rows]
            elif re.search(r"表\s*\d+", query):
                table_rows = connection.execute(
                    """
                    SELECT fact_id, fact_type, predicate, object_value, confidence,
                           source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                    FROM facts
                    WHERE source_doc_id = ?
                      AND fact_type = 'table_requirement'
                    ORDER BY confidence DESC, fact_id ASC
                    LIMIT 8
                    """,
                    (doc_id,),
                ).fetchall()
                other_rows = connection.execute(
                    """
                    SELECT fact_id, fact_type, predicate, object_value, confidence,
                           source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                    FROM facts
                    WHERE source_doc_id = ?
                      AND fact_type IN ('requirement', 'threshold', 'parameter_value')
                    ORDER BY confidence DESC, fact_id ASC
                    LIMIT 12
                    """,
                    (doc_id,),
                ).fetchall()
                rows = [*table_rows, *other_rows]
            else:
                rows = connection.execute(
                    """
                    SELECT fact_id, fact_type, predicate, object_value, confidence,
                           source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                    FROM facts
                    WHERE source_doc_id = ?
                      AND fact_type IN ('requirement', 'table_requirement', 'threshold', 'parameter_value')
                      AND object_value LIKE ?
                    ORDER BY confidence DESC, fact_id ASC
                    LIMIT 12
                    """,
                    (doc_id, f"%{normalized_query}%"),
                ).fetchall()
            extra = [_row_to_fact(row) for row in rows]

        seen = {item["fact_id"] for item in facts}
        for item in extra:
            if item["fact_id"] not in seen:
                facts.append(item)
                seen.add(item["fact_id"])
        return _rank_facts(facts, intent, query=query)
    finally:
        connection.close()


def _row_to_fact(row) -> dict[str, object]:
    return {
        "fact_id": row["fact_id"],
        "fact_type": row["fact_type"],
        "predicate": row["predicate"],
        "object_value": _safe_json(row["object_value"]),
        "confidence": row["confidence"],
        "source_doc_id": row["source_doc_id"],
        "subject_entity_id": row["subject_entity_id"],
        "object_entity_id": row["object_entity_id"],
        "qualifiers_json": _safe_json(row["qualifiers_json"]),
    }


def _safe_json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _build_definition_from_wiki(workspace_root: Path, wiki_pages: list[dict[str, object]]) -> str:
    for item in wiki_pages:
        file_path = str(item.get("file_path") or "").strip()
        if not file_path:
            continue
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = workspace_root / file_path
        if not candidate.exists():
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        title_match = re.search(r"^#\s+(.+)$", content, re.M)
        definition_match = re.search(r"^##\s*定义\s*$\s*(.+?)(?=^\s*##|\Z)", content, re.M | re.S)
        title = title_match.group(1).strip() if title_match else str(item.get("title") or "").strip()
        definition = ""
        if definition_match:
            definition = re.sub(r"\s+", " ", definition_match.group(1)).strip()
        elif title:
            definition = re.sub(r"\s+", " ", content.splitlines()[-1]).strip()
        if title and definition:
            return f"{title}: {definition}"
    return ""


def _build_approximate_definition_fallback(
    workspace_root: Path,
    rewritten_payload: dict[str, object],
    context: dict[str, object],
) -> tuple[str, str]:
    target_topic = str(rewritten_payload.get("target_topic") or "").strip()
    if not target_topic:
        return "", ""
    related = _find_related_definition_entity(workspace_root, target_topic)
    if not related:
        return "", ""
    canonical_name = str(related.get("canonical_name") or "").strip()
    description = str(related.get("description") or "").strip()
    if not canonical_name or not description:
        return "", ""
    answer = (
        f"知识库中未找到 {target_topic} 的直接定义。"
        f" 当前最接近的相关概念是 {canonical_name}：{description}"
        f" 以下内容为近似解释，不是 {target_topic} 的精确定义。"
    )
    return answer, "fallback_to_related_concept"


def _find_related_definition_entity(workspace_root: Path, target_topic: str) -> dict[str, object] | None:
    family_terms = _related_family_terms(target_topic)
    if not family_terms:
        return None
    family_root = _related_family_root(target_topic)
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        rows = connection.execute(
            """
            SELECT entity_id, canonical_name, entity_type, description
            FROM entities
            WHERE entity_type IN ('term', 'comparison_topic')
            ORDER BY canonical_name
            """
        ).fetchall()
    finally:
        connection.close()

    if family_root:
        exact_family = [
            dict(row)
            for row in rows
            if str(row["canonical_name"] or "").strip().upper() == family_root
        ]
        if exact_family:
            exact_family.sort(
                key=lambda item: (
                    0 if str(item.get("entity_type") or "") == "comparison_topic" else 1,
                    str(item.get("canonical_name") or ""),
                )
            )
            return exact_family[0]

    candidates: list[tuple[float, dict[str, object]]] = []
    upper_target = target_topic.upper()
    for row in rows:
        item = dict(row)
        canonical_name = str(item.get("canonical_name") or "").strip()
        description = str(item.get("description") or "").strip()
        blob = f"{canonical_name} {description}".upper()
        score = 0.0
        if canonical_name.strip() in {"摘 要", "摘要", "ABSTRACT"}:
            continue
        if upper_target in blob:
            score += 10.0
        for term in family_terms:
            if term.upper() in blob:
                score += 4.0
        if family_root and canonical_name.upper() == family_root:
            score += 4.5
        if family_root and str(item.get("entity_type") or "") == "comparison_topic":
            score += 2.6
        if str(item.get("entity_type") or "") == "term":
            score += 1.5
        if "V2X" in blob:
            score += 2.0
        if "V2G" in blob:
            score += 1.2
        if score > 0:
            candidates.append((score, item))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: (-pair[0], str(pair[1].get("canonical_name") or "")))
    top = candidates[0][1]
    if str(top.get("canonical_name") or "").strip().upper() == upper_target:
        return None
    return top


def _related_family_terms(target_topic: str) -> list[str]:
    upper = target_topic.upper().strip()
    terms: list[str] = []
    if re.fullmatch(r"V2[A-Z]", upper):
        terms.extend(["V2X", "V2G", "VEHICLE TO", "VEHICLE-TO", "车网", "双向互动"])
    elif re.fullmatch(r"[A-Z]{2,5}", upper):
        terms.append(upper)
    return terms


def _related_family_root(target_topic: str) -> str:
    upper = target_topic.upper().strip()
    if re.fullmatch(r"V2[A-Z]", upper):
        return "V2X"
    return ""


def _definition_answer_needs_section_fallback(
    answer_facts: list[dict[str, object]],
    rewritten_payload: dict[str, object],
) -> bool:
    target_topic = str(rewritten_payload.get("target_topic") or "").strip()
    if not answer_facts:
        return True
    for item in answer_facts[:6]:
        fact_type = str(item.get("fact_type") or "")
        if fact_type == "document_abstract":
            return False
        if fact_type not in {"term_definition", "concept_definition"}:
            continue
        payload = item.get("object_value")
        if not isinstance(payload, dict):
            continue
        term = str(payload.get("term") or "").strip()
        if _is_strong_definition_term_match(target_topic, term):
            return False
    return True


def _build_definition_from_section_intro(
    workspace_root: Path,
    rewritten_payload: dict[str, object],
    preferred_doc_id: str | None,
) -> str:
    target_topic = str(rewritten_payload.get("target_topic") or "").strip()
    if not target_topic:
        return ""

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        rows = connection.execute(
            """
            SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no, object_value
            FROM facts
            WHERE fact_type = 'section_heading'
            ORDER BY fact_id
            """
        ).fetchall()
        candidates: list[tuple[float, str, int, str]] = []
        for row in rows:
            payload = _safe_json(row["object_value"])
            if not isinstance(payload, dict):
                continue
            title = str(payload.get("title") or "").strip()
            if not title:
                continue
            score = _section_heading_match_score(target_topic, title)
            if preferred_doc_id and row["source_doc_id"] == preferred_doc_id:
                score += 1.2
            if score > 0:
                candidates.append((score, str(row["source_doc_id"]), int(row["page_no"] or 0), title))
        if not candidates:
            return ""
        candidates.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))
        _, doc_id, page_no, title = candidates[0]
        intro = _find_section_intro_text(connection, doc_id, page_no, title, target_topic)
        if not intro:
            return ""
        label = target_topic if target_topic in title or title in target_topic else title
        return f"{label}：{intro}"
    finally:
        connection.close()


def _section_heading_match_score(target_topic: str, title: str) -> float:
    target = target_topic.strip()
    current = title.strip()
    if not target or not current:
        return 0.0
    if len(current) < 2 or current.isdigit():
        return 0.0
    if any(token in current for token in ("图", "表", "附录", "附 录", "前言", "引言", "范围", "规范性引用文件")):
        return 0.0
    score = 0.0
    if current == target:
        score += 8.0
    elif target in current or current in target:
        score += 5.0
    if score > 0 and len(current) <= 24:
        score += 1.0
    return score


def _is_strong_definition_term_match(target_topic: str, term: str) -> bool:
    target = _normalize_query_phrase(target_topic)
    current = _normalize_query_phrase(term)
    if not target or not current:
        return False
    if current == target:
        return True
    if current.startswith(target):
        return True
    if _definition_term_has_anchor(target_topic, term):
        return True
    stripped = re.sub(r"^[A-Z]?\d+(?:\.\d+){0,8}", "", term).strip()
    stripped = _normalize_query_phrase(stripped)
    return stripped == target or stripped.startswith(target)


def _definition_term_has_anchor(target_topic: str, term: str) -> bool:
    target = str(target_topic or "").strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9/-]{1,10}", target):
        return False
    # Definitions often keep the Chinese label first and the acronym at the end:
    # "连接确认功能 connection confirm function; CC".
    return bool(re.search(rf"(?<![A-Z0-9]){re.escape(target)}(?![A-Z0-9])", str(term or "")))


def _find_section_intro_text(connection, doc_id: str, page_no: int, title: str, target_topic: str) -> str:
    evidence_rows = connection.execute(
        """
        SELECT normalized_text
        FROM evidence
        WHERE doc_id = ?
          AND page_no BETWEEN ? AND ?
        ORDER BY page_no ASC, evidence_id ASC
        """,
        (doc_id, max(1, page_no), max(1, page_no + 1)),
    ).fetchall()
    for row in evidence_rows:
        text = str(row["normalized_text"] or "")
        intro = _extract_intro_after_heading(text, title, target_topic)
        if intro:
            return intro

    fact_rows = connection.execute(
        """
        SELECT fact_type, object_value
        FROM facts
        WHERE source_doc_id = ?
          AND json_extract(qualifiers_json, '$.page_no') BETWEEN ? AND ?
          AND fact_type IN ('requirement', 'table_requirement')
        ORDER BY fact_id ASC
        """,
        (doc_id, max(1, page_no), max(1, page_no + 1)),
    ).fetchall()
    for row in fact_rows:
        payload = _safe_json(row["object_value"])
        if not isinstance(payload, dict):
            continue
        content = str(payload.get("content") or "").strip()
        if not content:
            continue
        if target_topic in content or title in content:
            return _normalize_definition_intro(content)
    return ""


def _extract_intro_after_heading(text: str, title: str, target_topic: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for anchor in [title, target_topic]:
        anchor = str(anchor or "").strip()
        if not anchor:
            continue
        pattern = re.escape(anchor).replace(r"\ ", r"\s+")
        match = re.search(pattern, normalized, re.S)
        if not match:
            continue
        tail = normalized[match.end():]
        tail = re.sub(r"^[\s:：\-—]+", "", tail)
        lines = [line.strip() for line in tail.splitlines()]
        collected: list[str] = []
        for line in lines:
            if not line:
                if collected:
                    break
                continue
            if _looks_like_heading_line(line):
                if collected:
                    break
                continue
            collected.append(line)
            if len(" ".join(collected)) >= 280:
                break
        intro = _normalize_definition_intro(" ".join(collected))
        if intro:
            return intro
    return ""


def _looks_like_heading_line(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.startswith(("#", "*", "附录", "附 录", "图", "表")):
        return True
    if re.match(r"^[A-Z]\.\d", text):
        return True
    if re.match(r"^\d+(?:\.\d+){1,6}\b", text):
        return True
    return False


def _normalize_definition_intro(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^[，。；:：\-\s]+", "", text)
    return text[:320]


def _align_topics_to_answer(
    rewritten_payload: dict[str, object],
    answer_facts: list[dict[str, object]],
    direct_answer: str,
    topic_objects: list[dict[str, object]],
    topic_entities: list[dict[str, object]],
    all_entities: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not topic_objects:
        return [], []

    query_type = str(rewritten_payload.get("query_type") or "")
    target_topic = str(rewritten_payload.get("target_topic") or "").strip()

    def score_topic(item: dict[str, object]) -> tuple[float, str]:
        title = str(item.get("title") or "").strip()
        entity_id = str(item.get("entity_id") or "").strip()
        page_type = str(item.get("page_type") or "").strip()
        score = 0.0

        if target_topic and title and target_topic in title:
            score += 5.0
        if direct_answer and title and title in direct_answer:
            score += 4.0

        if query_type == "definition":
            if page_type == "term":
                score += 2.0
            if direct_answer and title and title.split(" vehicle", 1)[0] in direct_answer:
                score += 4.0
        elif query_type == "parameter_lookup":
            fact_titles = []
            for fact in answer_facts:
                payload = fact.get("object_value")
                if isinstance(payload, dict):
                    for key in ("table_title", "source_caption", "title"):
                        value = str(payload.get(key) or "").strip()
                        if value:
                            fact_titles.append(value)
            if any(title and title in fact_title for fact_title in fact_titles):
                score += 6.0
            if page_type == "parameter_group":
                score += 1.5
            elif page_type == "parameter":
                score += 5.0
        elif query_type == "timing_lookup":
            fact_titles = []
            for fact in answer_facts:
                payload = fact.get("object_value")
                if isinstance(payload, dict):
                    for key in ("table_title", "title", "process_name"):
                        value = str(payload.get(key) or "").strip()
                        if value:
                            fact_titles.append(value)
            if any(title and title in fact_title for fact_title in fact_titles):
                score += 6.0
            if page_type == "process":
                score += 1.5
        elif query_type == "comparison":
            if page_type == "comparison":
                score += 2.0
        elif query_type == "constraint":
            if page_type == "constraint":
                score += 2.0

        if entity_id and any(str(entity.get("entity_id") or "") == entity_id for entity in topic_entities):
            score += 1.0
        return (score, title)

    ranked_topics = sorted(topic_objects, key=score_topic, reverse=True)
    top_topics = [item for item in ranked_topics if score_topic(item)[0] > 0]
    if not top_topics:
        top_topics = ranked_topics[:5]

    if query_type == "definition":
        target = target_topic.strip()
        if target:
            for entity in all_entities:
                if str(entity.get("entity_type") or "") != "term":
                    continue
                name = str(entity.get("canonical_name") or "").strip()
                if target == name or target in name or name.endswith(target):
                    if not any(str(item.get("entity_id") or "") == str(entity.get("entity_id") or "") for item in top_topics):
                        top_topics.insert(
                            0,
                            {
                                "page_id": f"SYNTH-TERM-{entity.get('entity_id')}",
                                "page_type": "term",
                                "title": name,
                                "entity_id": entity.get("entity_id"),
                                "trust_status": "synthetic",
                                "file_path": "",
                                "source_fact_ids_json": "",
                            },
                        )
        top_topics = [
            item for item in top_topics
            if str(item.get("page_type") or "") == "term"
            and (target in str(item.get("title") or "") or str(item.get("title") or "") in target or target == str(item.get("title") or ""))
        ] or top_topics

    if query_type == "parameter_lookup":
        anchor_terms = {
            term.upper()
            for term in _constraint_target_terms(target_topic, rewritten_payload)
            if re.fullmatch(r"[A-Z]{1,4}\d*", term.upper())
        }
        anchor_topics = [
            item for item in top_topics
            if str(item.get("page_type") or "") == "parameter"
            and str(item.get("title") or "").upper() in anchor_terms
        ]
        if not anchor_topics:
            for entity in topic_entities:
                if str(entity.get("entity_type") or "") != "parameter_topic":
                    continue
                name = str(entity.get("canonical_name") or "").strip()
                if name.upper() in anchor_terms:
                    anchor_topics.append(
                        {
                            "page_id": f"SYNTH-PARAM-TOPIC-{entity.get('entity_id')}",
                            "page_type": "parameter",
                            "title": name,
                            "entity_id": entity.get("entity_id"),
                            "trust_status": "synthetic",
                            "file_path": "",
                            "source_fact_ids_json": "",
                        }
                    )
        fact_titles: list[str] = []
        for fact in answer_facts:
            payload = fact.get("object_value")
            if isinstance(payload, dict):
                for key in ("table_title", "source_caption", "title"):
                    value = str(payload.get(key) or "").strip()
                    if value and "表" in value and value not in fact_titles:
                        fact_titles.append(value)
        for pattern in (
            r"^\*{0,2}(表\s*[A-Z]?\.\d+[^\n：:]{0,80}?)\*{0,2}：",
            r"^\*{0,2}(表\s*[A-Z]?\.\d+[^\n]{0,80}?)\*{0,2}$",
        ):
            match = re.search(pattern, direct_answer)
            if match:
                value = match.group(1).strip()
                if value and value not in fact_titles:
                    fact_titles.append(value)
        primary_table_title = _extract_primary_table_title(direct_answer)
        if primary_table_title and primary_table_title not in fact_titles:
            fact_titles.insert(0, primary_table_title)
        if fact_titles:
            matched_topics: list[dict[str, object]] = []
            matched_entity_ids: set[str] = set()
            for entity in all_entities:
                if str(entity.get("entity_type") or "") != "parameter_group":
                    continue
                name = str(entity.get("canonical_name") or "").strip()
                if any(title and (title == name or title in name or name in title) for title in fact_titles):
                    entity_id = str(entity.get("entity_id") or "").strip()
                    if entity_id not in matched_entity_ids:
                        matched_entity_ids.add(entity_id)
                        matched_topics.append(
                            {
                                "page_id": f"SYNTH-{entity.get('entity_id')}",
                                "page_type": "parameter_group",
                                "title": name,
                                "entity_id": entity.get("entity_id"),
                                "trust_status": "synthetic",
                                "file_path": "",
                                "source_fact_ids_json": "",
                            }
                        )
            existing_titles = {str(item.get("title") or "") for item in matched_topics}
            for title in fact_titles:
                if title and title not in existing_titles:
                    synthetic_page_id = f"SYNTH-PARAM-{title}"
                    matched_topics.append(
                        {
                            "page_id": synthetic_page_id,
                            "page_type": "parameter_group",
                            "title": title,
                            "entity_id": "",
                            "trust_status": "synthetic",
                            "file_path": "",
                            "source_fact_ids_json": "",
                        },
                    )
                    existing_titles.add(title)
            top_topics = matched_topics or top_topics
        top_topics = anchor_topics + [
            item for item in top_topics
            if str(item.get("page_type") or "") == "parameter_group"
            and "表" in str(item.get("title") or "")
        ] or top_topics

    chosen_entity_ids = {
        str(item.get("entity_id") or "").strip()
        for item in top_topics
        if str(item.get("entity_id") or "").strip()
    }
    aligned_entities = [
        entity for entity in all_entities
        if str(entity.get("entity_id") or "").strip() in chosen_entity_ids
    ]
    if query_type == "parameter_lookup":
        aligned_entities = [
            entity for entity in topic_entities
            if str(entity.get("entity_type") or "") == "parameter_topic"
        ] + [
            entity for entity in aligned_entities
            if str(entity.get("entity_type") or "") == "parameter_group"
        ]
    if query_type == "definition":
        aligned_entities = [
            entity for entity in aligned_entities
            if str(entity.get("entity_type") or "") == "term"
        ] or [
            entity for entity in all_entities
            if str(entity.get("entity_type") or "") == "term"
            and (target_topic == str(entity.get("canonical_name") or "") or target_topic in str(entity.get("canonical_name") or ""))
        ]
    if not aligned_entities:
        aligned_entities = topic_entities[:5]

    dedup_topics: list[dict[str, object]] = []
    seen_pages: set[str] = set()
    for item in top_topics:
        page_id = str(item.get("page_id") or "")
        if page_id and page_id not in seen_pages:
            seen_pages.add(page_id)
            dedup_topics.append(item)

    return dedup_topics[:5], aligned_entities[:5]


def _extract_primary_table_title(text: str) -> str:
    lines = str(text or "").splitlines()
    if not lines:
        return ""
    first_line = lines[0].strip()
    if not first_line:
        return ""
    first_line = first_line.strip("*").strip()
    if "：" in first_line:
        first_line = first_line.split("：", 1)[0].strip()
    match = re.search(r"(表\s*[A-Z]?\.\d+[^\n]{0,80})", first_line)
    return match.group(1).strip() if match else ""


def _build_constraint_from_topic_evidence(
    workspace_root: Path,
    rewritten_payload: dict[str, object],
    wiki_pages: list[dict[str, object]],
    doc_id: str | None,
) -> str:
    target_topic = str(rewritten_payload.get("target_topic") or "").strip()
    if not target_topic:
        return ""

    target_terms = _constraint_target_terms(target_topic, rewritten_payload)
    if not target_terms:
        target_terms = [target_topic]

    candidate_pages = [
        item for item in wiki_pages
        if str(item.get("page_type") or "") == "constraint"
        and any(term and term in str(item.get("title") or "") for term in target_terms)
    ]
    if not candidate_pages:
        return ""

    source_fact_ids: list[str] = []
    for item in candidate_pages:
        raw_ids = _safe_json(item.get("source_fact_ids_json"))
        if isinstance(raw_ids, list):
            for fact_id in raw_ids:
                value = str(fact_id).strip()
                if value and value not in source_fact_ids:
                    source_fact_ids.append(value)
    if not source_fact_ids:
        return ""

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        placeholders = ",".join("?" for _ in source_fact_ids)
        fact_rows = connection.execute(
            f"""
            SELECT qualifiers_json
            FROM facts
            WHERE fact_id IN ({placeholders})
            """,
            source_fact_ids,
        ).fetchall()
        page_nos: set[int] = set()
        for row in fact_rows:
            qualifiers = _safe_json(row["qualifiers_json"])
            if isinstance(qualifiers, dict):
                page_no = int(qualifiers.get("page_no") or 0)
                if page_no:
                    for candidate in range(page_no, page_no + 3):
                        page_nos.add(candidate)
        if not page_nos:
            return ""

        placeholders = ",".join("?" for _ in page_nos)
        params: list[object] = [*sorted(page_nos)]
        where_doc = ""
        if doc_id:
            where_doc = " AND doc_id = ? "
            params.append(doc_id)
        rows = connection.execute(
            f"""
            SELECT page_no, normalized_text
            FROM evidence
            WHERE page_no IN ({placeholders})
            {where_doc}
            ORDER BY page_no ASC, confidence DESC
            LIMIT 6
            """,
            params,
        ).fetchall()
        for row in rows:
            text = str(row["normalized_text"] or "").strip()
            for term in target_terms:
                if term and term in text:
                    snippet = _extract_topic_paragraph(text, term)
                    if snippet:
                        return snippet
        return ""
    finally:
        connection.close()


def _extract_topic_paragraph(text: str, topic: str) -> str:
    compact = re.sub(r"\n{2,}", "\n", text)
    pattern = re.compile(rf"(?:#+\s*)?(?:\d+(?:\.\d+){{0,8}}\s*)?{re.escape(topic)}[^\n]*\n(.+?)(?:\n(?:#+\s*|\d+(?:\.\d+){{0,8}}\s)|\Z)", re.S)
    match = pattern.search(compact)
    if match:
        paragraph = match.group(1).strip()
        if paragraph:
            return _truncate(paragraph, 600)
    if topic in compact:
        start = compact.find(topic)
        return _truncate(compact[start:start + 600].strip(), 600)
    return ""


def _constraint_answer_needs_topic_fallback(
    rewritten_payload: dict[str, object],
    answer_facts: list[dict[str, object]],
) -> bool:
    target_topic = str(rewritten_payload.get("target_topic") or "").strip()
    if not target_topic or not answer_facts:
        return False

    target_terms = _constraint_target_terms(target_topic, rewritten_payload)
    if not target_terms:
        return False

    for item in answer_facts[:3]:
        payload = item.get("object_value")
        payload_dict = payload if isinstance(payload, dict) else {}
        topic_scope = " ".join(
            str(payload_dict.get(key) or "").strip()
            for key in ("topic", "subject", "title")
        )
        if any(term and term in topic_scope for term in target_terms):
            return False
    return True


def _normalize_query_phrase(query: str) -> str:
    text = query
    matched_pattern = False
    for pattern in (
        r"^\s*(.+?)\s*是怎么定义的\s*$",
        r"^\s*(.+?)\s*怎么定义\s*$",
        r"^\s*(.+?)\s*如何定义\s*$",
        r"^\s*(.+?)\s*是什么\s*$",
        r"^\s*(.+?)\s*要求是什么\s*$",
        r"^\s*(.+?)\s*有什么要求\s*$",
        r"^\s*(.+?)\s*有哪些字段\s*$",
        r"^\s*(.+?)\s*包括哪些字段\s*$",
        r"^\s*什么是\s*(.+?)\s*$",
        r"^\s*(.+?)\s*如何理解\s*$",
        r"^\s*(.+?)\s*怎么理解\s*$",
    ):
        match = re.match(pattern, text)
        if match:
            captured = next(group for group in match.groups() if group)
            text = captured
            matched_pattern = True
            break
    if not matched_pattern:
        text = re.sub(r"(什么是|是什么|是怎么定义的|怎么定义|如何定义|如何理解|定义|要求是什么|有什么要求|有哪些字段|包括哪些字段)", " ", text)
    text = text.replace("？", " ").replace("?", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_standard_code(value: str) -> str:
    text = value.upper().replace("GBT", "GB/T").replace("GB T", "GB/T").replace("QC T", "QC/T")
    text = text.replace("-", "—")
    text = re.sub(r"\s+", "", text)
    return text


def _extract_standard_from_query(query: str) -> str:
    match = re.search(r"(?:GB/T|GBT|GB|ISO|IEC|QC/T|QC)\s*[\d.]+(?:[—-]\d{2,4})?", query, re.I)
    return match.group(0) if match else query


def _extract_exact_terms(query: str) -> list[str]:
    terms = re.findall(r"[A-Z][A-Z0-9/-]{1,}", query)
    normalized: list[str] = []
    for term in terms:
        if term not in normalized and term not in {"GB", "GBT", "ISO", "IEC", "QC"}:
            normalized.append(term)
    return normalized


def _context_matches_exact_terms(
    context: dict[str, object],
    exact_terms: list[str],
    rewritten_payload: dict[str, object] | None = None,
) -> bool:
    if not exact_terms:
        return True
    corpus_parts: list[str] = []
    for collection_name in ("hits", "evidence", "facts", "wiki_pages", "documents"):
        for item in context.get(collection_name, []):
            corpus_parts.append(json.dumps(item, ensure_ascii=False))
    corpus = "\n".join(corpus_parts).upper()
    if any(term.upper() in corpus for term in exact_terms):
        return True
    return any(
        _context_matches_protected_anchor_alias(corpus, term, rewritten_payload or {})
        for term in exact_terms
    )


def _context_matches_protected_anchor_alias(
    corpus_upper: str,
    exact_term: str,
    rewritten_payload: dict[str, object],
) -> bool:
    term = str(exact_term or "").strip().upper()
    if not term:
        return False
    known_aliases = {
        "OBC": ["车载充电机", "电动汽车用传导式车载充电机", "ON-BOARD CHARGER", "ONBOARD CHARGER"],
    }
    if any(alias.upper() in corpus_upper for alias in known_aliases.get(term, [])):
        return True
    protected = {str(item or "").strip().upper() for item in rewritten_payload.get("protected_anchor_terms") or []}
    if term not in protected:
        return False
    alias_fields = (
        rewritten_payload.get("aliases") or [],
        rewritten_payload.get("must_terms") or [],
        rewritten_payload.get("should_terms") or [],
    )
    candidates: list[str] = []
    target_topic = str(rewritten_payload.get("target_topic") or "").strip()
    if target_topic:
        candidates.append(target_topic)
    for values in alias_fields:
        if isinstance(values, list):
            candidates.extend(str(value or "").strip() for value in values)
    for candidate in candidates:
        if not candidate:
            continue
        normalized = candidate.upper()
        if normalized == term or len(normalized) <= len(term):
            continue
        if normalized in corpus_upper:
            return True
    return False


def _context_has_exact_definition_signal(context: dict[str, object], exact_terms: list[str]) -> bool:
    if not exact_terms:
        return True
    corpus_parts: list[str] = []
    for collection_name in ("hits", "evidence", "facts", "wiki_pages"):
        for item in context.get(collection_name, []):
            corpus_parts.append(json.dumps(item, ensure_ascii=False))
    corpus = "\n".join(corpus_parts).upper()
    for term in exact_terms:
        target = term.upper()
        if target in corpus and any(token in corpus for token in ("TYPE", "V2X", "V2G", "V2V", "VEHICLE TO", "车辆", "电网", "负荷")):
            return True
    return False


def _rank_facts(facts: list[dict[str, object]], intent: str, query: str = "") -> list[dict[str, object]]:
    target_standard = _normalize_standard_code(_extract_standard_from_query(query)) if intent == "standard" else None
    requested_table_no = _extract_table_no_from_query(query)
    def score(item: dict[str, object]) -> tuple[float, float]:
        fact_type = item.get("fact_type")
        confidence = float(item.get("confidence") or 0)
        bonus = 0.0
        if intent == "definition":
            if fact_type in {"term_definition", "concept_definition"}:
                bonus = 4.0
            elif fact_type == "document_abstract":
                bonus = 3.0
            elif fact_type == "section_heading":
                bonus = 1.5
        elif intent == "standard":
            if fact_type in {"document_standard", "document_versioning", "document_lifecycle"}:
                bonus = 3.0
            elif fact_type in {"term_definition", "concept_definition"}:
                bonus = 0.5
            if fact_type == "document_standard" and isinstance(item.get("object_value"), dict):
                value = _normalize_standard_code(str(item["object_value"].get("value", "")))
                if value and target_standard and value == target_standard:
                    bonus += 2.0
        elif intent == "parameter":
            if fact_type == "parameter_value":
                bonus = 4.0
            elif fact_type == "table_requirement":
                bonus = 2.8
            elif fact_type == "threshold":
                bonus = 1.6
            elif fact_type == "requirement":
                bonus = 1.2
            payload = item.get("object_value")
            blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
            if "目 次" in blob or "前    言" in blob or "前言" in blob:
                bonus -= 5.0
            if re.search(r"(阻值|电阻|欧姆|Ω)", query) and re.search(r"(Ω|电阻|阻值|R\d+)", blob, re.I):
                bonus += 3.0
            if re.search(r"\bCC\b|CC1|CC2", query, re.I) and re.search(r"\bCC\b|CC1|CC2", blob, re.I):
                bonus += 2.5
            if re.search(r"(检测点\s*\d)", query) and re.search(r"(检测点\s*\d)", blob):
                bonus += 2.0
            if re.search(r"(控制导引|导引电路)", blob):
                bonus += 1.0
            bonus += float(item.get("_focus_term_bonus") or 0.0)
            bonus += float(item.get("_page_focus_bonus") or 0.0)
            bonus += float(item.get("_subgraph_bonus") or 0.0)
        elif intent == "process":
            if fact_type == "transition_fact":
                bonus = 4.2
            elif fact_type == "process_fact":
                bonus = 4.0
            elif fact_type == "table_requirement":
                bonus = 2.0
            elif fact_type == "requirement":
                bonus = 1.0
            payload = item.get("object_value")
            blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
            if isinstance(payload, dict) and str(payload.get("scope_type") or "") in {"index", "preface"}:
                bonus -= 10.0
            if any(token in blob for token in ("前言", "前    言", "目 次", "目次")):
                bonus -= 10.0
            if _is_timing_query(query) and ("表 A.7" in blob or "控制时序" in blob or "状态转换" in blob):
                bonus += 5.0
            if any(token in blob for token in ("时序", "状态", "握手", "预充", "停机", "控制时序说明")):
                bonus += 2.0
            if "控制导引" in blob or "检测点" in blob or "CP" in blob:
                bonus += 1.2
            bonus += float(item.get("_subgraph_bonus") or 0.0)
        elif intent == "constraint":
            if fact_type == "threshold":
                bonus = 4.4
            elif fact_type == "requirement":
                bonus = 4.0
            elif fact_type == "table_requirement":
                bonus = 2.4
            elif fact_type == "parameter_value":
                bonus = 1.4
            payload = item.get("object_value")
            blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
            if any(token in blob for token in ("要求", "应", "不应", "应满足", "不得")):
                bonus += 1.4
            if any(token in blob for token in ("最大", "最小", "不超过", "不小于", "阈值")):
                bonus += 1.0
            bonus += float(item.get("_subgraph_bonus") or 0.0)
        elif intent == "comparison":
            if fact_type == "comparison_relation":
                bonus = 4.6
            elif fact_type in {"term_definition", "concept_definition"}:
                bonus = 2.0
            else:
                bonus = 0.6
            payload = item.get("object_value")
            blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
            if any(token in blob.upper() for token in ("V2X", "V2G", "V2V", "V2B", "V2H")):
                bonus += 1.2
            bonus += float(item.get("_subgraph_bonus") or 0.0)
        else:
            if fact_type in {"term_definition", "concept_definition"}:
                bonus = 1.0
            elif fact_type == "requirement":
                bonus = 2.0
            elif fact_type == "threshold":
                bonus = 1.8
            elif fact_type == "table_requirement":
                bonus = 1.6
            elif fact_type == "parameter_value":
                bonus = 2.4
            if re.search(r"表\s*\d+", query) and fact_type == "table_requirement":
                bonus += 3.0
                payload = item.get("object_value")
                if isinstance(payload, dict):
                    table_no = str(payload.get("table_no") or "").strip()
                    if requested_table_no and table_no == requested_table_no:
                        bonus += 4.0
                    elif requested_table_no and table_no and table_no != requested_table_no:
                        bonus -= 2.0
            if re.search(r"(字段|表头|参数)", query) and fact_type == "table_requirement":
                bonus += 2.0
            if re.search(r"(阻值|参数|电阻|CC)", query) and fact_type == "parameter_value":
                bonus += 3.0
            bonus += float(item.get("_subgraph_bonus") or 0.0)
        return (bonus + confidence, confidence)

    return sorted(facts, key=score, reverse=True)


def _prioritize_judged_facts(context: dict[str, object], facts: list[dict[str, object]]) -> list[dict[str, object]]:
    judgement = context.get("evidence_judgement")
    if not isinstance(judgement, dict) or not judgement.get("sufficient"):
        return facts
    best_fact_ids = [str(item).strip() for item in judgement.get("best_fact_ids") or [] if str(item).strip()]
    if not best_fact_ids:
        return facts
    rank = {fact_id: index for index, fact_id in enumerate(best_fact_ids)}
    return sorted(
        facts,
        key=lambda item: (
            0 if str(item.get("fact_id") or "") in rank else 1,
            rank.get(str(item.get("fact_id") or ""), len(rank)),
        ),
    )


def _extract_table_no_from_query(query: str) -> str | None:
    match = re.search(r"表\s*(\d+)", query)
    return match.group(1) if match else None


def _is_timing_query(query: str) -> bool:
    return bool(re.search(r"(时序|流程|状态转换|控制时序|握手|预充|启动|停止|停机)", str(query or "")))


def _is_activity_process_query(query: str) -> bool:
    return bool(re.search(r"(活动|任务|步骤|实践|要做|做什么|工作内容|过程域|基本实践)", str(query or "")))


def _special_appendix_c_requested(query: str) -> bool:
    text = str(query or "")
    return bool(re.search(r"(GB/T\s*20234\.4|GBT\s*20234\.4|检测点\s*3|附录\s*C|直流)", text, re.I))


def _select_supporting_evidence(
    workspace_root: Path,
    facts: list[dict[str, object]],
    query: str,
    intent: str,
) -> list[dict[str, object]]:
    fact_ids = [item["fact_id"] for item in facts[:6] if item.get("fact_id")]
    if not fact_ids:
        return []

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        placeholders = ",".join("?" for _ in fact_ids)
        rows = connection.execute(
            f"""
            SELECT DISTINCT e.evidence_id, e.doc_id, e.page_no, e.confidence, e.risk_level, e.normalized_text
            FROM fact_evidence_map m
            JOIN evidence e ON e.evidence_id = m.evidence_id
            WHERE m.fact_id IN ({placeholders})
            """,
            fact_ids,
        ).fetchall()
        evidence = [dict(row) for row in rows]
        return _rank_evidence(evidence, query, intent)
    finally:
        connection.close()


def _rank_evidence(evidence: list[dict[str, object]], query: str, intent: str) -> list[dict[str, object]]:
    def score(item: dict[str, object]) -> tuple[float, float]:
        text = item.get("normalized_text", "")
        confidence = float(item.get("confidence") or 0)
        bonus = 0.0
        if intent == "definition":
            if "##" in text and any(token in text for token in (" control pilot ", "控制导引电路", "定义", "术语")):
                bonus += 2.5
            if "##" in text:
                bonus += 0.5
        elif intent == "standard":
            if re.search(r"\d{4}-\d{2}-\d{2}\s*(发布|实施)", text):
                bonus += 1.5
            if re.search(r"\bGB/T\b", text):
                bonus += 1.0
        elif intent == "parameter":
            if "<table" in text.lower() or "|" in text:
                bonus += 1.5
            if re.search(r"(Ω|电阻|阻值|R\d+|检测点\s*\d|CC1|CC2)", text, re.I):
                bonus += 1.6
            if "目 次" in text or "前    言" in text or "前言" in text:
                bonus -= 2.0
        elif intent == "process":
            if "<table" in text.lower() or "|" in text:
                bonus += 1.3
            if re.search(r"(时序|状态|握手|预充|停机|检测点|控制导引)", text):
                bonus += 1.8
            if "目 次" in text or "前    言" in text or "前言" in text:
                bonus -= 2.2
        else:
            if "<table" in text.lower():
                bonus -= 1.2
            if "##" in text:
                bonus += 0.6
            if any(token in text for token in ("定义", "范围", "适用于")):
                bonus += 0.4
        if query and query.replace("？", "").replace("?", "")[:8] in text:
            bonus += 0.8
        return (bonus + confidence, confidence)

    return sorted(evidence, key=score, reverse=True)


def _find_relevant_pages_for_query(connection, doc_id: str, terms: list[str]) -> set[int]:
    relevant: set[int] = set()
    cleaned_terms = []
    for term in terms:
        normalized = str(term or "").strip()
        if normalized and normalized not in cleaned_terms:
            cleaned_terms.append(normalized)
    for term in cleaned_terms[:12]:
        rows = connection.execute(
            """
            SELECT page_no
            FROM evidence
            WHERE doc_id = ?
              AND normalized_text LIKE ?
            LIMIT 20
            """,
            (doc_id, f"%{term}%"),
        ).fetchall()
        for row in rows:
            page_no = int(row["page_no"])
            for candidate in range(max(1, page_no - 2), page_no + 3):
                relevant.add(candidate)
    return relevant


def _select_answer_facts(
    facts: list[dict[str, object]],
    intent: str,
    query: str,
    knowledge_subgraph: dict[str, object] | None = None,
    rewritten_payload: dict[str, object] | None = None,
    answer_mode: str = "",
) -> list[dict[str, object]]:
    if intent == "standard":
        return _select_standard_answer_facts(facts, knowledge_subgraph, query)
    if intent not in {"parameter", "process", "definition", "constraint", "comparison"}:
        return _prioritize_subgraph_facts(facts, knowledge_subgraph)

    if intent == "process":
        return _select_process_answer_facts(facts, knowledge_subgraph, query)
    if intent == "definition":
        return _select_definition_answer_facts(facts, knowledge_subgraph, query, rewritten_payload or {})
    if intent == "constraint":
        return _select_constraint_answer_facts(facts, knowledge_subgraph, query, rewritten_payload or {})
    if intent == "comparison":
        return _select_comparison_answer_facts(facts, knowledge_subgraph)
    if answer_mode == "parameter_meaning":
        return _select_parameter_meaning_answer_facts(facts, knowledge_subgraph, query, rewritten_payload or {})

    focus_terms = _parameter_focus_terms(query, {"must_terms": [], "aliases": [], "should_terms": []})

    def score(item: dict[str, object]) -> tuple[float, float]:
        fact_type = str(item.get("fact_type") or "")
        confidence = float(item.get("confidence") or 0.0)
        payload = item.get("object_value")
        if not isinstance(payload, dict):
            payload = {}
        focus_tags = [str(tag).upper() for tag in payload.get("focus_tags") or []]
        page_bonus = float(item.get("_page_focus_bonus") or 0.0)
        raw_focus_bonus = float(item.get("_focus_term_bonus") or 0.0)
        wiki_bonus = 2.2 if item.get("_source_from_wiki") else 0.0
        subgraph_bonus = float(item.get("_subgraph_bonus") or 0.0)
        bonus = confidence + page_bonus + raw_focus_bonus + wiki_bonus + subgraph_bonus

        if fact_type == "parameter_value":
            bonus += 6.0
        elif fact_type == "table_requirement":
            bonus += 3.0
        elif fact_type == "threshold":
            bonus += 1.0
        else:
            bonus += 0.2

        if any(term.upper() in focus_tags for term in focus_terms if term):
            bonus += 5.0
        if "CC" in query.upper():
            if "CC1" in focus_tags or "CC2" in focus_tags:
                bonus += 4.0
            elif fact_type == "parameter_value":
                bonus -= 2.5
        if re.search(r"(检测点\s*\d)", query):
            if any("检测点" in tag for tag in focus_tags):
                bonus += 3.0
        return (bonus, confidence)

    ranked = sorted(_prioritize_subgraph_facts(facts, knowledge_subgraph), key=score, reverse=True)
    parameter_first = [item for item in ranked if item.get("fact_type") == "parameter_value"]
    if parameter_first:
        supporting_tables = [item for item in ranked if item.get("fact_type") == "table_requirement"]
        return parameter_first + supporting_tables + [item for item in ranked if item.get("fact_type") not in {"parameter_value", "table_requirement"}]
    return ranked


def _select_parameter_meaning_answer_facts(
    facts: list[dict[str, object]],
    knowledge_subgraph: dict[str, object] | None,
    query: str,
    rewritten_payload: dict[str, object],
) -> list[dict[str, object]]:
    ranked = _prioritize_subgraph_facts(facts, knowledge_subgraph)
    focus_terms = _parameter_focus_terms(query, rewritten_payload)
    target_topic = str(rewritten_payload.get("target_topic") or "").strip()
    signal_state_query = _is_signal_state_query(query)
    requested_voltage = _requested_voltage_value(query)
    preferred_object_entity_ids = {
        str(item)
        for item in (knowledge_subgraph or {}).get("topic_entity_ids", [])
        if str(item).strip()
    }

    def meaning_score(item: dict[str, object]) -> tuple[float, float]:
        confidence = float(item.get("confidence") or 0.0)
        bonus = float(item.get("_subgraph_bonus") or 0.0)
        fact_type = str(item.get("fact_type") or "")
        payload = item.get("object_value")
        if not isinstance(payload, dict):
            payload = {}
        blob = json.dumps(payload, ensure_ascii=False)
        focus_tags = [str(tag).upper() for tag in payload.get("focus_tags") or []]
        row_focus_tags = [str(tag).upper() for tag in payload.get("row_focus_tags") or []]
        symbol = str(payload.get("symbol", "")).strip().upper()
        parameter = str(payload.get("parameter", "")).strip()

        if fact_type == "parameter_value":
            bonus += 5.0
        elif fact_type in {"term_definition", "concept_definition"}:
            bonus += 4.0
        elif fact_type == "table_requirement":
            bonus += 1.5
            if signal_state_query and _table_matches_signal_state(payload, requested_voltage):
                bonus += 14.0

        for term in focus_terms:
            upper_term = term.upper()
            if upper_term and upper_term in blob.upper():
                bonus += 4.0
            if upper_term and upper_term in focus_tags:
                bonus += 4.5
            if upper_term and upper_term in row_focus_tags:
                bonus += 5.0
            if upper_term and upper_term == symbol:
                bonus += 5.0
            if upper_term and upper_term in parameter.upper():
                bonus += 4.0

        if target_topic and target_topic in blob:
            bonus += 5.0
        if preferred_object_entity_ids and str(item.get("object_entity_id") or "") in preferred_object_entity_ids:
            bonus += 2.5
        if "parameter_group" in blob.lower() and fact_type != "parameter_value":
            bonus -= 1.0
        return (bonus + confidence, confidence)

    enriched = sorted(ranked, key=meaning_score, reverse=True)
    parameter_items = [item for item in enriched if item.get("fact_type") == "parameter_value"]
    definition_items = [item for item in enriched if item.get("fact_type") in {"term_definition", "concept_definition"}]
    table_items = [item for item in enriched if item.get("fact_type") == "table_requirement"]
    others = [
        item for item in enriched
        if item.get("fact_type") not in {"parameter_value", "term_definition", "concept_definition", "table_requirement"}
    ]
    if signal_state_query:
        return table_items[:6] + definition_items[:3] + parameter_items[:3] + others[:4]
    return parameter_items[:6] + definition_items[:3] + table_items[:2] + others[:4]


def _is_signal_state_query(query: str) -> bool:
    return bool(
        re.search(r"PWM", query, re.I)
        and re.search(r"[+-]?\d+(?:\.\d+)?\s*V|电压", query, re.I)
        and re.search(r"\bCP\b|控制导引|检测点", query, re.I)
    )


def _requested_voltage_value(query: str) -> str:
    match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*V", query, re.I)
    return match.group(1) if match else ""


def _table_matches_signal_state(payload: dict[str, object], requested_voltage: str) -> bool:
    title = str(payload.get("table_title") or payload.get("title") or "")
    headers = " ".join(str(item) for item in payload.get("headers") or [])
    if "PWM" not in f"{title} {headers}".upper():
        return False
    if "电压" not in f"{title} {headers}" or "状态" not in f"{title} {headers}":
        return False
    if not requested_voltage:
        return True
    for row in payload.get("rows") or []:
        if not isinstance(row, list):
            continue
        values = [str(cell).strip() for cell in row]
        if requested_voltage in values[:3] and len(values) > 3 and values[3] in {"是", "是/否"}:
            return True
    return False


def _apply_subgraph_fact_signals(
    context: dict[str, object],
    facts: list[dict[str, object]],
    intent: str,
    query: str,
) -> list[dict[str, object]]:
    knowledge_subgraph = context.get("knowledge_subgraph")
    if not isinstance(knowledge_subgraph, dict):
        return list(facts)

    seeded_fact_ids = {str(item) for item in knowledge_subgraph.get("seed_fact_ids", []) if str(item).strip()}
    seeded_entity_ids = {str(item) for item in knowledge_subgraph.get("seed_entity_ids", []) if str(item).strip()}
    topic_entity_ids = {str(item) for item in knowledge_subgraph.get("topic_entity_ids", []) if str(item).strip()}
    wiki_page_types = {
        str(item).strip().lower()
        for item in knowledge_subgraph.get("wiki_page_types", [])
        if str(item).strip()
    }

    annotated: list[dict[str, object]] = []
    for item in facts:
        cloned = dict(item)
        bonus = float(cloned.get("_subgraph_bonus") or 0.0)
        if str(cloned.get("fact_id") or "") in seeded_fact_ids:
            bonus += 2.5
        if str(cloned.get("subject_entity_id") or "") in seeded_entity_ids:
            bonus += 1.5
        if str(cloned.get("object_entity_id") or "") in seeded_entity_ids:
            bonus += 1.5
        if str(cloned.get("subject_entity_id") or "") in topic_entity_ids:
            bonus += 2.4
        if str(cloned.get("object_entity_id") or "") in topic_entity_ids:
            bonus += 2.4
        if cloned.get("_source_from_wiki"):
            bonus += 1.2

        fact_type = str(cloned.get("fact_type") or "")
        if intent == "parameter" and "parameter_group" in wiki_page_types:
            if fact_type == "parameter_value":
                bonus += 2.0
            elif fact_type == "table_requirement":
                bonus += 0.8
        elif intent == "process" and "process" in wiki_page_types:
            if fact_type == "transition_fact":
                bonus += 2.0
            elif fact_type == "process_fact":
                bonus += 1.8
            elif fact_type == "table_requirement":
                bonus += 0.6
        elif intent == "definition" and {"term", "concept"} & wiki_page_types:
            if fact_type in {"term_definition", "concept_definition"}:
                bonus += 2.0
        elif intent == "constraint":
            if fact_type in {"requirement", "threshold"}:
                bonus += 1.8
            elif fact_type == "table_requirement":
                bonus += 0.8
            if {"term", "process", "parameter_group"} & wiki_page_types:
                bonus += 0.6
        elif intent == "comparison":
            if fact_type == "comparison_relation":
                bonus += 2.2
            elif {"term", "concept"} & wiki_page_types:
                bonus += 0.6

        if query and any(token in query for token in ("CC", "CP", "V2G", "V2X")):
            payload = cloned.get("object_value")
            blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
            if any(token in blob.upper() for token in re.findall(r"[A-Z][A-Z0-9/-]{1,}", query.upper())):
                bonus += 0.8

        cloned["_subgraph_bonus"] = bonus
        annotated.append(cloned)
    return annotated


def _prioritize_subgraph_facts(
    facts: list[dict[str, object]],
    knowledge_subgraph: dict[str, object] | None,
) -> list[dict[str, object]]:
    if not isinstance(knowledge_subgraph, dict):
        return list(facts)

    seeded_fact_ids = {str(item) for item in knowledge_subgraph.get("seed_fact_ids", []) if str(item).strip()}
    topic_entity_ids = {str(item) for item in knowledge_subgraph.get("topic_entity_ids", []) if str(item).strip()}

    def score(item: dict[str, object]) -> tuple[float, float]:
        confidence = float(item.get("confidence") or 0.0)
        bonus = float(item.get("_subgraph_bonus") or 0.0)
        if str(item.get("fact_id") or "") in seeded_fact_ids:
            bonus += 1.5
        if item.get("_source_from_wiki"):
            bonus += 1.0
        if str(item.get("subject_entity_id") or "") in topic_entity_ids:
            bonus += 1.4
        if str(item.get("object_entity_id") or "") in topic_entity_ids:
            bonus += 1.4
        return (bonus + confidence, confidence)

    return sorted(facts, key=score, reverse=True)


def _select_process_answer_facts(
    facts: list[dict[str, object]],
    knowledge_subgraph: dict[str, object] | None,
    query: str = "",
) -> list[dict[str, object]]:
    ranked = _prioritize_subgraph_facts(facts, knowledge_subgraph)
    if is_test_method_query(query):
        test_methods = [
            item for item in ranked
            if str(item.get("fact_type") or "") == "process_fact"
            and looks_like_test_method_blob(
                query,
                json.dumps(item.get("object_value"), ensure_ascii=False)
                if isinstance(item.get("object_value"), (dict, list))
                else str(item.get("object_value") or ""),
            )
        ]
        if test_methods:
            primary_group = _test_method_group_key(test_methods[0])
            if primary_group:
                grouped = [item for item in test_methods if _test_method_group_key(item) == primary_group]
                if grouped:
                    return grouped
            return test_methods[:6]

    def process_score(item: dict[str, object]) -> tuple[float, float]:
        confidence = float(item.get("confidence") or 0.0)
        bonus = float(item.get("_subgraph_bonus") or 0.0)
        fact_type = str(item.get("fact_type") or "")
        payload = item.get("object_value")
        blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
        if fact_type == "transition_fact":
            bonus += 5.0
        elif fact_type == "process_fact":
            bonus += 4.0
        elif fact_type == "table_requirement":
            bonus += 1.0
        if _is_timing_query(query) and "表 A.7" in blob:
            bonus += 8.0
        elif _is_timing_query(query) and "表 C.3" in blob and not _special_appendix_c_requested(query):
            bonus -= 2.0
        if any(token in blob for token in ("前言", "前    言", "目 次", "目次")):
            bonus -= 10.0
        return (bonus + confidence, confidence)

    transitions = sorted((item for item in ranked if item.get("fact_type") == "transition_fact"), key=process_score, reverse=True)
    processes = sorted((item for item in ranked if item.get("fact_type") == "process_fact"), key=process_score, reverse=True)
    others = sorted(
        (item for item in ranked if item.get("fact_type") not in {"transition_fact", "process_fact"}),
        key=process_score,
        reverse=True,
    )
    if _is_activity_process_query(query) and not _is_timing_query(query):
        return processes + others + transitions
    return transitions + processes + others


def _test_method_group_key(item: dict[str, object]) -> str:
    payload = item.get("object_value")
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("process_name") or payload.get("title") or "").strip()


def _select_standard_answer_facts(
    facts: list[dict[str, object]],
    knowledge_subgraph: dict[str, object] | None,
    query: str,
) -> list[dict[str, object]]:
    ranked = _prioritize_subgraph_facts(facts, knowledge_subgraph)
    target_standard = _normalize_standard_code(_extract_standard_from_query(query))

    def standard_score(item: dict[str, object]) -> tuple[float, float]:
        confidence = float(item.get("confidence") or 0.0)
        bonus = float(item.get("_subgraph_bonus") or 0.0)
        fact_type = str(item.get("fact_type") or "")
        payload = item.get("object_value")
        payload_dict = payload if isinstance(payload, dict) else {}

        if fact_type == "document_standard":
            bonus += 6.0
            value = _normalize_standard_code(str(payload_dict.get("value") or ""))
            if target_standard and value == target_standard:
                bonus += 6.0
        elif fact_type == "document_lifecycle":
            bonus += 5.0
            if str(item.get("predicate") or "") == "effective_date":
                bonus += 1.5
        elif fact_type == "document_versioning":
            bonus += 4.0
        else:
            bonus -= 4.0
        return (bonus + confidence, confidence)

    ordered = sorted(ranked, key=standard_score, reverse=True)
    preferred = [
        item for item in ordered
        if str(item.get("fact_type") or "") in {"document_standard", "document_lifecycle", "document_versioning"}
    ]
    others = [
        item for item in ordered
        if str(item.get("fact_type") or "") not in {"document_standard", "document_lifecycle", "document_versioning"}
    ]
    return preferred + others


def _select_definition_answer_facts(
    facts: list[dict[str, object]],
    knowledge_subgraph: dict[str, object] | None,
    query: str,
    rewritten_payload: dict[str, object],
) -> list[dict[str, object]]:
    ranked = _prioritize_subgraph_facts(facts, knowledge_subgraph)
    target_terms = _definition_target_terms(query, rewritten_payload)

    def definition_score(item: dict[str, object]) -> tuple[float, float]:
        confidence = float(item.get("confidence") or 0.0)
        bonus = float(item.get("_subgraph_bonus") or 0.0)
        fact_type = str(item.get("fact_type") or "")
        payload = item.get("object_value")
        payload_dict = payload if isinstance(payload, dict) else {}
        term = str(payload_dict.get("term") or payload_dict.get("title") or "").strip()
        blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
        normalized_blob = _normalize_query_phrase(blob)

        if fact_type in {"term_definition", "concept_definition"}:
            bonus += 4.0
        elif fact_type == "document_abstract":
            bonus += 2.0
        elif fact_type == "section_heading":
            bonus += 0.4

        normalized_term = _normalize_query_phrase(term)
        for target in target_terms:
            normalized_target = _normalize_query_phrase(target)
            if not normalized_target:
                continue
            if normalized_term == normalized_target:
                bonus += 6.0
            elif _definition_term_has_anchor(target, term):
                bonus += 5.5
            elif normalized_target in normalized_term:
                bonus += 2.5
            elif normalized_target in normalized_blob:
                bonus += 1.2
        return (bonus + confidence, confidence)

    return sorted(ranked, key=definition_score, reverse=True)


def _definition_target_terms(query: str, rewritten_payload: dict[str, object]) -> list[str]:
    values = [
        str(rewritten_payload.get("target_topic") or "").strip(),
        _normalize_query_phrase(query),
        *[str(item).strip() for item in rewritten_payload.get("must_terms", [])],
        *[str(item).strip() for item in rewritten_payload.get("aliases", [])],
    ]
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result[:8]


def _select_constraint_answer_facts(
    facts: list[dict[str, object]],
    knowledge_subgraph: dict[str, object] | None,
    query: str,
    rewritten_payload: dict[str, object],
) -> list[dict[str, object]]:
    ranked = _prioritize_subgraph_facts(facts, knowledge_subgraph)
    query_focus = _normalize_query_phrase(query)
    topic_terms = _constraint_target_terms(query, rewritten_payload)

    def constraint_score(item: dict[str, object]) -> tuple[float, float]:
        confidence = float(item.get("confidence") or 0.0)
        bonus = float(item.get("_subgraph_bonus") or 0.0)
        fact_type = str(item.get("fact_type") or "")
        payload = item.get("object_value")
        blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
        payload_dict = payload if isinstance(payload, dict) else {}
        subject = str(payload_dict.get("subject") or "").strip()
        topic = str(payload_dict.get("topic") or "").strip()
        title = str(payload_dict.get("title") or "").strip()
        scope_type = str(payload_dict.get("scope_type") or "").strip()
        key_scope = f"{subject} {title}".strip()
        if fact_type == "threshold":
            bonus += 5.0
        elif fact_type == "requirement":
            bonus += 4.0
        elif fact_type == "table_requirement":
            bonus += 2.0
        if scope_type == "normative_requirement":
            bonus += 2.0
        elif scope_type == "appendix_rule":
            bonus += 1.2
        elif scope_type in {"overview", "preface", "index"}:
            bonus -= 8.0
        if any(token in blob for token in ("前言", "前    言", "目 次", "目次")):
            bonus -= 10.0
        topic_scope = f"{topic} {key_scope}".strip()
        if any(term and topic_scope and term in topic_scope for term in topic_terms):
            bonus += 7.0
        elif query_focus and topic_scope and query_focus in topic_scope:
            bonus += 5.5
        elif query_focus and query_focus in blob:
            bonus += 1.5
        elif query_focus:
            bonus -= 2.0
        return (bonus + confidence, confidence)

    ranked = sorted(ranked, key=constraint_score, reverse=True)
    if topic_terms:
        strong_matches = []
        for item in ranked:
            payload = item.get("object_value")
            payload_dict = payload if isinstance(payload, dict) else {}
            topic_scope = " ".join(
                str(payload_dict.get(key) or "").strip()
                for key in ("topic", "subject", "title")
            )
            scope_type = str(payload_dict.get("scope_type") or "").strip()
            if scope_type in {"overview", "preface", "index"}:
                continue
            if any(term and term in topic_scope for term in topic_terms):
                strong_matches.append(item)
        if strong_matches:
            ranked = strong_matches + [item for item in ranked if item not in strong_matches]

    constraint_first = [
        item for item in ranked
        if item.get("fact_type") in {"threshold", "requirement", "table_requirement"}
    ]
    if constraint_first:
        return constraint_first + [
            item for item in ranked
            if item.get("fact_type") not in {"threshold", "requirement", "table_requirement"}
        ]
    return ranked


def _constraint_target_terms(query: str, rewritten_payload: dict[str, object]) -> list[str]:
    terms: list[str] = []

    def add(value: str) -> None:
        text = str(value or "").strip()
        if not text:
            return
        if text not in terms:
            terms.append(text)

    add(str(rewritten_payload.get("target_topic") or ""))
    add(_normalize_query_phrase(query))

    for item in rewritten_payload.get("must_terms", []) or []:
        text = str(item or "").strip()
        if text and len(text) <= 16:
            add(text)
    for item in rewritten_payload.get("aliases", []) or []:
        text = str(item or "").strip()
        if text and len(text) <= 24 and not re.search(r"[A-Za-z]{5,}", text):
            add(text)

    cleaned: list[str] = []
    for term in terms:
        normalized = re.sub(r"(有什么要求|要求是什么|应满足什么|应符合什么)$", "", term).strip()
        normalized = normalized.replace("的要求", "").strip()
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned[:8]


def _select_comparison_answer_facts(
    facts: list[dict[str, object]],
    knowledge_subgraph: dict[str, object] | None,
) -> list[dict[str, object]]:
    ranked = _prioritize_subgraph_facts(facts, knowledge_subgraph)

    def comparison_score(item: dict[str, object]) -> tuple[float, float]:
        confidence = float(item.get("confidence") or 0.0)
        bonus = float(item.get("_subgraph_bonus") or 0.0)
        fact_type = str(item.get("fact_type") or "")
        if fact_type == "comparison_relation":
            bonus += 5.0
        elif fact_type in {"term_definition", "concept_definition"}:
            bonus += 2.0
        return (bonus + confidence, confidence)

    return sorted(ranked, key=comparison_score, reverse=True)


def _parameter_focus_terms(query: str, rewritten_payload: dict[str, object]) -> list[str]:
    focus_terms: list[str] = []
    explicit_code_focus = bool(re.search(r"\b(?:CC|CP|CC1|CC2|CP1|CP2)\b", query.upper()))

    def add(value: str) -> None:
        term = str(value or "").strip()
        if term and term not in focus_terms:
            focus_terms.append(term)

    for match in re.finditer(r"\b[A-Z]{1,4}\d*\b", query.upper()):
        add(match.group(0))
    for match in re.finditer(r"([+-]?\d+(?:\.\d+)?)\s*V", query, re.I):
        voltage = match.group(1)
        add(f"{voltage}V")
        add(f"{voltage} V")
        add(voltage)
    for match in re.finditer(r"(检测点\s*\d+)", query):
        add(match.group(1))
    if "PWM" in query.upper():
        add("PWM")
        add("占空比")
    if "CP" in query.upper():
        add("控制导引")
        add("检测点 1")
    for match in re.finditer(r"(表\s*[A-Z]?\d+(?:\.\d+)*)", query):
        add(match.group(1))

    for term in rewritten_payload.get("must_terms", []):
        term = str(term)
        if re.fullmatch(r"[A-Z]{1,4}\d*", term):
            add(term)
        elif re.search(r"(检测点\s*\d+)", term):
            add(term)
        elif (
            not explicit_code_focus
            and any(token in query for token in ("控制导引", "导引电路", "接口", "电阻", "阻值", "参数"))
            and len(term) <= 8
        ):
            add(term)

    for alias in rewritten_payload.get("aliases", []):
        alias = str(alias)
        if re.fullmatch(r"[A-Z]{1,4}\d*", alias):
            add(alias)
        elif re.search(r"(检测点\s*\d+)", alias) and not explicit_code_focus:
            add(alias)
        elif not explicit_code_focus and alias in {"控制导引", "控制导引电路"}:
            add(alias)

    if not focus_terms:
        add(_normalize_query_phrase(query))
    return focus_terms[:10]


def _focus_term_bonus(blob: str, focus_terms: list[str]) -> float:
    if not blob:
        return 0.0
    bonus = 0.0
    for term in focus_terms:
        if not term:
            continue
        if term in blob:
            if re.fullmatch(r"[A-Z]{1,4}\d*", term):
                bonus += 1.8
            elif "检测点" in term:
                bonus += 1.6
            else:
                bonus += 0.8
    return bonus


def _filter_graph_edges(
    workspace_root: Path,
    edges: list[dict[str, object]],
    facts: list[dict[str, object]],
    intent: str,
    doc_id: str | None,
    knowledge_subgraph: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    entity_ids: set[str] = set()
    for item in facts[:8]:
        if item.get("subject_entity_id"):
            entity_ids.add(item["subject_entity_id"])
        if item.get("object_entity_id"):
            entity_ids.add(item["object_entity_id"])
    topic_entity_ids = {
        str(item)
        for item in (knowledge_subgraph or {}).get("topic_entity_ids", [])
        if str(item).strip()
    }
    entity_ids |= topic_entity_ids

    filtered = [
        edge
        for edge in edges
        if edge.get("src_entity_id") in entity_ids or edge.get("dst_entity_id") in entity_ids
    ]
    candidates = filtered or edges
    if not candidates and entity_ids:
        candidates = _load_graph_edges_for_entities(workspace_root, entity_ids, doc_id)

    def score(edge: dict[str, object]) -> tuple[float, float]:
        confidence = float(edge.get("confidence") or 0.0)
        bonus = 0.0
        relation = str(edge.get("relation") or "")
        if intent == "process":
            if relation == "has_process":
                bonus += 3.0
            elif relation == "relates_to_term":
                bonus += 1.0
        elif intent == "parameter":
            if relation == "has_parameter_group":
                bonus += 3.0
            elif relation == "relates_to_term":
                bonus += 1.0
        elif intent == "definition":
            if relation == "defines_term":
                bonus += 3.0
            elif relation == "relates_to_term":
                bonus += 1.0
        elif intent == "constraint":
            if relation == "has_constraint":
                bonus += 3.0
            elif relation == "relates_to_term":
                bonus += 0.8
        elif intent == "comparison":
            if relation == "has_comparison":
                bonus += 3.0
            elif relation == "relates_to_term":
                bonus += 0.8
        if edge.get("src_entity_id") in entity_ids or edge.get("dst_entity_id") in entity_ids:
            bonus += 0.8
        return (bonus + confidence, confidence)

    ranked = sorted(candidates, key=score, reverse=True)
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for edge in ranked:
        edge_id = str(edge.get("edge_id") or "")
        if edge_id and edge_id not in seen:
            seen.add(edge_id)
            deduped.append(edge)
    return deduped[:8]


def _load_graph_edges_for_entities(
    workspace_root: Path,
    entity_ids: set[str],
    doc_id: str | None,
) -> list[dict[str, object]]:
    if not entity_ids:
        return []

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        placeholders = ",".join("?" for _ in entity_ids)
        where_scope = " AND version_scope = ? " if doc_id else ""
        rows = connection.execute(
            f"""
            SELECT edge_id, src_entity_id, relation, dst_entity_id, version_scope, confidence
            FROM graph_edges
            WHERE (src_entity_id IN ({placeholders}) OR dst_entity_id IN ({placeholders}))
            {where_scope}
            ORDER BY confidence DESC, edge_id ASC
            LIMIT 24
            """,
            [*entity_ids, *entity_ids, *([doc_id] if doc_id else [])],
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _filter_wiki_pages(
    wiki_pages: list[dict[str, object]],
    facts: list[dict[str, object]],
    query: str,
    intent: str,
) -> list[dict[str, object]]:
    if intent == "standard":
        target = _normalize_standard_code(_extract_standard_from_query(query))
        exact = [item for item in wiki_pages if _normalize_standard_code(str(item.get("title", ""))) == target]
        if exact:
            return exact + [item for item in wiki_pages if item not in exact]

    entity_ids = {
        item.get("subject_entity_id")
        for item in facts[:8]
        if item.get("subject_entity_id")
    } | {
        item.get("object_entity_id")
        for item in facts[:8]
        if item.get("object_entity_id")
    }
    filtered = [item for item in wiki_pages if item.get("entity_id") in entity_ids]
    return filtered or wiki_pages


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def _summarize_facts(facts: list[dict[str, object]], intent: str = "general") -> list[str]:
    lines: list[str] = []
    for item in facts:
        payload = item.get("object_value")
        if item["fact_type"] == "document_standard" and isinstance(payload, dict):
            lines.append(f"标准号: {payload.get('value', '')}")
        elif item["fact_type"] == "document_versioning" and isinstance(payload, dict):
            lines.append(f"代替标准: {payload.get('value', '')}")
        elif item["fact_type"] == "document_lifecycle" and isinstance(payload, dict):
            label = "发布日期" if item["predicate"] == "publication_date" else "实施日期"
            lines.append(f"{label}: {payload.get('value', '')}")
        elif item["fact_type"] in {"term_definition", "concept_definition"} and isinstance(payload, dict):
            term = payload.get("term", "")
            definition = payload.get("definition", "")
            if term and definition:
                lines.append(f"{term}: {_truncate(str(definition), 120)}")
        elif item["fact_type"] == "document_abstract" and isinstance(payload, dict):
            value = payload.get("value", "")
            if value:
                lines.append(f"摘要: {_truncate(str(value), 120)}")
        elif item["fact_type"] == "section_heading" and isinstance(payload, dict):
            title = payload.get("title", "")
            if title:
                lines.append(f"相关章节: {title}")

    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    if intent == "definition":
        return deduped[:4]
    return deduped[:6]


def _choose_doc_by_phrase_match(workspace_root: Path, normalized_phrase: str, intent: str) -> str | None:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        scores: dict[str, float] = {}

        def bump(doc_id: str | None, score: float) -> None:
            if doc_id:
                scores[doc_id] = scores.get(doc_id, 0.0) + score

        fact_rows = connection.execute(
            """
            SELECT source_doc_id, fact_type, object_value
            FROM facts
            WHERE fact_type IN (
                'term_definition',
                'concept_definition',
                'document_title',
                'document_standard',
                'requirement',
                'table_requirement',
                'threshold'
            )
            """
        ).fetchall()
        for row in fact_rows:
            payload = _safe_json(row["object_value"])
            text_parts: list[str] = []
            if isinstance(payload, dict):
                text_parts.extend(str(value) for value in payload.values())
            elif payload:
                text_parts.append(str(payload))
            haystack = " ".join(text_parts)
            if normalized_phrase and normalized_phrase in haystack:
                weight = 4.0 if row["fact_type"] in {"term_definition", "concept_definition"} else 2.5
                if row["fact_type"] == "requirement":
                    weight = 4.2
                elif row["fact_type"] == "threshold":
                    weight = 4.0
                elif row["fact_type"] == "table_requirement":
                    weight = 4.1
                if intent == "definition" and row["fact_type"] in {"term_definition", "concept_definition"}:
                    weight += 2.0
                bump(row["source_doc_id"], weight)

        wiki_rows = connection.execute(
            """
            SELECT json_extract(source_doc_ids_json, '$[0]') AS doc_id, title, slug, page_type
            FROM wiki_pages
            """
        ).fetchall()
        for row in wiki_rows:
            haystack = f"{row['title']} {row['slug']}"
            if normalized_phrase and normalized_phrase in haystack:
                weight = 3.0 if row["page_type"] == "term" else 1.5
                bump(row["doc_id"], weight)

        evidence_rows = connection.execute(
            """
            SELECT doc_id, normalized_text
            FROM evidence
            WHERE normalized_text LIKE ?
            LIMIT 20
            """,
            (f"%{normalized_phrase}%",),
        ).fetchall()
        for row in evidence_rows:
            bump(row["doc_id"], 1.0)

        if not scores:
            return None
        return max(scores.items(), key=lambda item: item[1])[0]
    finally:
        connection.close()
