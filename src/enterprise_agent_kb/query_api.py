from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from .advanced_query_planner import advanced_terms_for_retrieval, plan_advanced_query
from .config import AppPaths
from .closed_loop_store import record_retrieval_run
from .db import connect
from .evidence_judge import judge_evidence
from .graph_retrieval import retrieve_graph_candidates
from .query_expansion import expand_query, expansion_terms_for_retrieval
from .query_ambiguity import build_clarification_context, detect_query_ambiguity_with_kb
from .query_rewrite import rewrite_query, RewrittenQuery
from .reranker import rerank_candidates
from .retrieval_router import route_retrieval
from .routing_summary import direct_routing_hits
from .topic_resolution import resolve_topic_entities


def _safe_json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _rewrite_with_expansion(rewritten: RewrittenQuery, expansion_terms: list[str]) -> RewrittenQuery:
    if not expansion_terms:
        return rewritten
    must_terms = list(rewritten.must_terms)
    should_terms = list(rewritten.should_terms)
    aliases = list(rewritten.aliases)
    protected = list(rewritten.protected_anchor_terms)
    for term in expansion_terms:
        cleaned = str(term or "").strip()
        if not cleaned:
            continue
        if _is_disallowed_expansion_term(rewritten.original_query, cleaned):
            continue
        if cleaned in protected or cleaned in must_terms or cleaned in should_terms or cleaned in aliases:
            continue
        if _is_hard_anchor_term(cleaned):
            must_terms.append(cleaned)
        elif len(cleaned) <= 48:
            should_terms.append(cleaned)
        else:
            aliases.append(cleaned)
    return replace(
        rewritten,
        must_terms=must_terms[:16],
        should_terms=should_terms[:24],
        aliases=aliases[:16],
    )


def _is_hard_anchor_term(value: str) -> bool:
    text = str(value or "").strip()
    return bool(
        re.fullmatch(r"[A-Z]{1,6}\d*", text)
        or re.fullmatch(r"[+-]?\d+(?:\.\d+)?\s*(?:V|A|Ω|kΩ|Hz|%)", text, re.I)
        or re.fullmatch(r"表\s*[A-Z]?\d+(?:\.\d+)*", text, re.I)
        or re.fullmatch(r"检测点\s*\d+", text)
    )


def _is_disallowed_expansion_term(original_query: str, term: str) -> bool:
    if not _looks_like_cp_control_pilot_context(original_query):
        return False
    normalized = re.sub(r"\s+", "", term).upper()
    return any(
        drift in normalized
        for drift in ("CHARGEPUMP", "CONTROLPIN", "CLOCKPULSE", "CHARGINGPROTOCOL")
    )


def _looks_like_cp_control_pilot_context(query: str) -> bool:
    return bool(
        re.search(r"(?<![A-Za-z0-9])CP(?![A-Za-z0-9])|控制导引", query, re.I)
        and re.search(r"PWM|检测点|电压|时序|流程|状态转换|控制时序|握手|预充|启动|停止|停机", query, re.I)
    )


def _merge_runtime_hits(hits: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for hit in hits:
        key = (str(hit.get("result_type") or ""), str(hit.get("result_id") or ""))
        if not key[0] or not key[1]:
            continue
        existing = merged.get(key)
        if existing is None or float(hit.get("score") or 0) > float(existing.get("score") or 0):
            merged[key] = dict(hit)
            if existing is not None:
                _merge_hit_metadata(merged[key], existing)
            continue
        _merge_hit_metadata(existing, hit)
        existing_channels = list(existing.get("channels") or [])
        for channel in hit.get("channels") or [hit.get("channel")]:
            if channel and channel not in existing_channels:
                existing_channels.append(channel)
        if existing_channels:
            existing["channels"] = existing_channels
    result = list(merged.values())
    result.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return result


def _merge_hit_metadata(target: dict[str, object], source: dict[str, object]) -> None:
    for key in ("graph_source", "graph_path", "edge_id", "relation", "trust_tier", "evidence_ids", "fact_id"):
        if key not in target and key in source:
            target[key] = source[key]
    if source.get("graph_source"):
        target["graph_source"] = True
    channels = list(target.get("channels") or [])
    for channel in source.get("channels") or [source.get("channel")]:
        if channel and channel not in channels:
            channels.append(channel)
    if channels:
        target["channels"] = channels


def _merge_injected_hits(
    hits: list[dict[str, object]],
    injected_hits: list[dict[str, object]],
    limit: int,
    *,
    force_injected: bool = False,
    minimum_limit: int | None = None,
) -> list[dict[str, object]]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for hit in hits:
        key = (str(hit.get("result_type") or ""), str(hit.get("result_id") or ""))
        if key[0] and key[1]:
            merged[key] = dict(hit)

    for hit in injected_hits:
        key = (str(hit.get("result_type") or ""), str(hit.get("result_id") or ""))
        if not key[0] or not key[1]:
            continue
        existing = merged.get(key)
        should_replace = (
            existing is None
            or force_injected
            or float(hit.get("score") or 0) > float(existing.get("score") or 0)
        )
        if should_replace:
            merged[key] = dict(hit)
            if existing is not None:
                _merge_hit_metadata(merged[key], existing)
            continue
        _merge_hit_metadata(existing, hit)

    merged_hits = list(merged.values())
    merged_hits.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return merged_hits[: max(limit, minimum_limit or 0)]


def build_query_context(
    workspace_root: Path,
    query: str,
    limit: int = 8,
    preferred_doc_id: str | None = None,
) -> dict[str, object]:
    """Build a retrieval-augmented context for *query* against the KB.

    Detects ambiguity, runs FTS5 search, gathers facts/evidence/wiki/graph
    hits, and returns a flat dict suitable for ranking layers and direct
    answering. The returned dict is mutable by callers for further filtering
    (e.g. restricting to a primary document).
    """
    query = query.strip()
    paths = AppPaths.from_root(workspace_root)
    ambiguity = detect_query_ambiguity_with_kb(query, paths.root / "ambiguity_index.json")
    if ambiguity:
        return build_clarification_context(query, preferred_doc_id, ambiguity)

    rewritten = rewrite_query(query)
    expansion = expand_query(query)
    advanced_plan = plan_advanced_query(
        query,
        json.dumps(rewritten.to_dict(), ensure_ascii=False),
        json.dumps(expansion.to_dict(), ensure_ascii=False),
    )
    retrieval_terms = [
        *expansion_terms_for_retrieval(expansion),
        *advanced_terms_for_retrieval(advanced_plan),
    ]
    retrieval_rewritten = _rewrite_with_expansion(rewritten, retrieval_terms)
    if not query:
        return {
            "query": query,
            "rewrite": rewritten.to_dict(),
            "query_expansion": expansion.to_dict(),
            "advanced_query_plan": advanced_plan.to_dict(),
            "hit_count": 0,
            "documents": [],
            "hits": [],
            "evidence": [],
            "facts": [],
            "entities": [],
            "graph_edges": [],
            "wiki_pages": [],
        }

    connection = connect(paths.db_file)

    try:
        topic_resolution = resolve_topic_entities(
            paths.root,
            rewritten,
            preferred_doc_id=preferred_doc_id,
            limit=max(limit, 8),
        )
        graph_candidates = retrieve_graph_candidates(
            connection,
            rewritten,
            topic_resolution.candidate_entity_ids,
            limit=max(limit * 2, 16),
        )
        graph_hits = [candidate.to_hit() for candidate in graph_candidates]
        routed = route_retrieval(paths.root, retrieval_rewritten, limit=max(limit * 3, 20), connection=connection)
        routed_hits = routed["hits"]
        routing_hits = direct_routing_hits(
            paths.root,
            query,
            expansion.to_dict(),
            limit=max(limit, 8),
            connection=connection,
        )
        routed_hits = _merge_runtime_hits([*graph_hits, *routing_hits, *routed_hits])
        if preferred_doc_id:
            scoped_routed_hits = [hit for hit in routed_hits if hit.get("doc_id") == preferred_doc_id]
            if scoped_routed_hits:
                routed_hits = scoped_routed_hits
        reranked_hits = rerank_candidates(paths.root, retrieval_rewritten, routed_hits, limit=max(limit * 3, 20), connection=connection)
        hits = [hit for hit in reranked_hits if hit["result_type"] != "document"]
        if preferred_doc_id:
            preferred_doc_id = preferred_doc_id.strip()
            filtered_hits = [hit for hit in hits if hit.get("doc_id") == preferred_doc_id]
            if filtered_hits:
                hits = filtered_hits
        hits = _filter_hits_for_exact_terms(retrieval_rewritten, hits)
        hits = _inject_exact_standard_hits(connection, query, hits, max(limit * 3, 20))
        hits = _inject_direct_term_definition_hits(connection, retrieval_rewritten, hits, max(limit * 3, 20))
        hits = _inject_direct_requirement_hits(connection, retrieval_rewritten, hits, max(limit * 3, 20))
        hits = _inject_direct_test_method_hits(connection, retrieval_rewritten, hits, max(limit * 3, 20))
        hits = _inject_direct_wiki_hits(connection, retrieval_rewritten, hits, max(limit * 3, 20))
        if preferred_doc_id:
            scoped_hits = [hit for hit in hits if hit.get("doc_id") == preferred_doc_id]
            if scoped_hits:
                hits = scoped_hits
        hits.sort(key=lambda item: float(item["score"] or 0), reverse=True)
        hits = hits[:limit]
        graph_hit_by_fact_id = {
            str(hit.get("result_id")): hit
            for hit in hits
            if hit.get("result_type") == "fact" and hit.get("graph_source")
        }
        graph_hit_by_evidence_id = {
            str(hit.get("result_id")): hit
            for hit in hits
            if hit.get("result_type") == "evidence" and hit.get("graph_source")
        }
        doc_ids = sorted({
            *(hit["doc_id"] for hit in hits if hit.get("doc_id")),
            *(hit["doc_id"] for hit in reranked_hits if hit.get("result_type") == "document" and hit.get("doc_id")),
            *([preferred_doc_id] if preferred_doc_id else []),
        })
        evidence_ids = [hit["result_id"] for hit in hits if hit["result_type"] == "evidence"]
        fact_ids = [hit["result_id"] for hit in hits if hit["result_type"] == "fact"]
        wiki_page_ids = [hit["result_id"] for hit in hits if hit["result_type"] == "wiki"]
        wiki_chunk_ids = [hit["result_id"] for hit in hits if hit["result_type"] == "wiki_chunk"]

        evidence_items: list[dict[str, object]] = []
        entity_ids: set[str] = set()

        if evidence_ids:
            placeholders = ",".join("?" for _ in evidence_ids)
            rows = connection.execute(
                f"""
                SELECT evidence_id, doc_id, page_no, confidence, risk_level, normalized_text
                FROM evidence
                WHERE evidence_id IN ({placeholders})
                ORDER BY confidence DESC, page_no ASC
                """,
                evidence_ids,
            ).fetchall()
            evidence_items = [dict(row) for row in rows]
            for item in evidence_items:
                graph_hit = graph_hit_by_evidence_id.get(str(item.get("evidence_id")))
                if graph_hit:
                    item["graph_path"] = graph_hit.get("graph_path")
                    item["graph_relation"] = graph_hit.get("relation")
                    item["graph_trust_tier"] = graph_hit.get("trust_tier")

        fact_items: list[dict[str, object]] = []
        if fact_ids:
            fact_rank = {fact_id: index for index, fact_id in enumerate(fact_ids)}
            placeholders = ",".join("?" for _ in fact_ids)
            rows = connection.execute(
                f"""
                SELECT fact_id, fact_type, predicate, object_value, confidence,
                       source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                FROM facts
                WHERE fact_id IN ({placeholders})
                ORDER BY confidence DESC, fact_id ASC
                """,
                fact_ids,
            ).fetchall()
            for row in rows:
                item = dict(row)
                item["object_value"] = _safe_json(item["object_value"])
                item["qualifiers_json"] = _safe_json(item["qualifiers_json"])
                graph_hit = graph_hit_by_fact_id.get(str(item.get("fact_id")))
                if graph_hit:
                    item["graph_path"] = graph_hit.get("graph_path")
                    item["graph_relation"] = graph_hit.get("relation")
                    item["graph_trust_tier"] = graph_hit.get("trust_tier")
                    item["graph_evidence_ids"] = graph_hit.get("evidence_ids")
                fact_items.append(item)
                if item.get("subject_entity_id"):
                    entity_ids.add(item["subject_entity_id"])
                if item.get("object_entity_id"):
                    entity_ids.add(item["object_entity_id"])
            fact_items.sort(key=lambda item: fact_rank.get(item.get("fact_id"), 9999))

        fact_items = _augment_standard_facts(connection, query, fact_items)
        fact_items = _augment_parameter_facts(connection, rewritten, fact_items)
        for item in fact_items:
            if item.get("subject_entity_id"):
                entity_ids.add(item["subject_entity_id"])
            if item.get("object_entity_id"):
                entity_ids.add(item["object_entity_id"])

        wiki_items: list[dict[str, object]] = []
        if wiki_page_ids:
            placeholders = ",".join("?" for _ in wiki_page_ids)
            rows = connection.execute(
                f"""
                SELECT w.page_id, w.page_type, w.title, w.slug, w.entity_id, w.trust_status,
                       w.file_path, w.source_fact_ids_json
                FROM wiki_pages w
                LEFT JOIN entities e ON e.entity_id = w.entity_id
                WHERE w.page_id IN ({placeholders})
                  AND (w.entity_id IS NULL OR e.entity_status = 'ready')
                ORDER BY trust_status DESC, title ASC
                """,
                wiki_page_ids,
            ).fetchall()
            wiki_items = [dict(row) for row in rows]
            for item in wiki_items:
                if item.get("entity_id"):
                    entity_ids.add(item["entity_id"])

        # Phase F: also hydrate wiki_chunks
        wiki_chunk_items: list[dict[str, object]] = []
        if wiki_chunk_ids:
            placeholders = ",".join("?" for _ in wiki_chunk_ids)
            rows = connection.execute(
                f"""
                SELECT chunk_id, doc_id, source_standard, section_title, body_text
                FROM wiki_chunks
                WHERE chunk_id IN ({placeholders})
                """,
                wiki_chunk_ids,
            ).fetchall()
            wiki_chunk_items = [dict(row) for row in rows]
        if topic_resolution.confidence < 0.8 or not topic_resolution.candidate_wiki_pages:
            wiki_items = _augment_query_wiki_items(connection, rewritten, wiki_items, doc_ids, limit)
        candidate_page_ids = {str(item.get("page_id") or "") for item in topic_resolution.candidate_wiki_pages}
        candidate_wiki_items = [dict(item) for item in topic_resolution.candidate_wiki_pages]
        residual_wiki_items = [
            item for item in wiki_items
            if str(item.get("page_id") or "") not in candidate_page_ids
        ]
        if candidate_wiki_items:
            wiki_items = candidate_wiki_items + residual_wiki_items
            if topic_resolution.confidence >= 0.8:
                wiki_items = wiki_items[:max(limit, len(candidate_wiki_items))]
        for item in wiki_items:
            if item.get("entity_id"):
                entity_ids.add(item["entity_id"])

        for entity_id in topic_resolution.candidate_entity_ids:
            if entity_id:
                entity_ids.add(entity_id)

        topic_objects = _hydrate_topic_object_entities(connection, candidate_wiki_items)
        if not topic_objects:
            topic_objects = _resolve_topic_objects(rewritten, wiki_items)
            topic_objects = _hydrate_topic_object_entities(connection, topic_objects)
        topic_objects = _compact_topic_objects(rewritten, topic_objects)
        topic_entity_ids = {
            str(item.get("entity_id") or "").strip()
            for item in topic_objects
            if str(item.get("entity_id") or "").strip()
        }
        topic_entity_ids |= set(topic_resolution.candidate_entity_ids)
        for item in topic_objects:
            if item.get("entity_id"):
                entity_ids.add(item["entity_id"])

        fact_items = _augment_facts_from_wiki(connection, fact_items, wiki_items, doc_ids)
        for item in fact_items:
            if item.get("subject_entity_id"):
                entity_ids.add(item["subject_entity_id"])
            if item.get("object_entity_id"):
                entity_ids.add(item["object_entity_id"])
        linked_evidence_ids = _linked_evidence_ids_for_facts(
            connection,
            [str(item.get("fact_id") or "") for item in fact_items if item.get("fact_id")],
        )

        entity_items: list[dict[str, object]] = []
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            rows = connection.execute(
                f"""
                SELECT entity_id, canonical_name, entity_type, description, source_confidence
                FROM entities
                WHERE entity_id IN ({placeholders})
                  AND entity_status = 'ready'
                ORDER BY entity_type, canonical_name
                """,
                list(entity_ids),
            ).fetchall()
            entity_items = [dict(row) for row in rows]

        topic_entity_items = [
            item for item in entity_items
            if str(item.get("entity_id") or "") in topic_entity_ids
        ]
        topic_entity_items = _order_topic_entities(topic_entity_items, topic_objects)

        edge_items: list[dict[str, object]] = []
        edge_seed_ids = topic_entity_ids or entity_ids
        if edge_seed_ids:
            placeholders = ",".join("?" for _ in edge_seed_ids)
            rows = connection.execute(
                f"""
                SELECT edge_id, src_entity_id, relation, dst_entity_id, version_scope, confidence
                FROM graph_edges
                WHERE src_entity_id IN ({placeholders}) OR dst_entity_id IN ({placeholders})
                ORDER BY confidence DESC, edge_id ASC
                LIMIT ?
                """,
                [*edge_seed_ids, *edge_seed_ids, limit * 3],
            ).fetchall()
            edge_items = [dict(row) for row in rows]

        knowledge_subgraph = {
            "seed_wiki_page_ids": [item["page_id"] for item in wiki_items[:8]],
            "seed_entity_ids": sorted(entity_ids)[:20],
            "seed_fact_ids": [item["fact_id"] for item in fact_items[:80] if item.get("fact_id")],
            "seed_edge_ids": [item["edge_id"] for item in edge_items[:80] if item.get("edge_id")],
            "wiki_page_types": sorted({
                str(item.get("page_type") or "").strip()
                for item in wiki_items
                if str(item.get("page_type") or "").strip()
            }),
            "topic_object_ids": [item["page_id"] for item in topic_objects[:8] if item.get("page_id")],
            "topic_entity_ids": sorted(topic_entity_ids)[:12],
            "fact_count": len(fact_items),
            "edge_count": len(edge_items),
            "wiki_count": len(wiki_items),
            "topic_count": len(topic_objects),
        }
        evidence_judgement = judge_evidence(query, {
            "facts": fact_items,
            "evidence": evidence_items,
            "rewrite": rewritten.to_dict(),
            "retrieval_plan": {"query_type": routed["query_type"]},
        }, expansion.to_dict())

        document_items: list[dict[str, object]] = []
        if doc_ids:
            placeholders = ",".join("?" for _ in doc_ids)
            rows = connection.execute(
                f"""
                SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
                FROM documents
                WHERE doc_id IN ({placeholders})
                ORDER BY doc_id
                """,
                doc_ids,
            ).fetchall()
            document_items = [dict(row) for row in rows]

        retrieval_plan = {
            "query_type": routed["query_type"],
            "channels": [
                *(["graph"] if graph_hits else []),
                *(["routing_summary"] if routing_hits else []),
                *routed["channels"],
            ],
            "routing_summary_hit_count": len(routing_hits),
            "graph_candidate_count": len(graph_hits),
            "advanced_query_plan_used": advanced_plan.enabled and advanced_plan.used_llm,
        }
        rerank_explanations = [
            {
                "result_type": hit["result_type"],
                "result_id": hit["result_id"],
                "doc_id": hit.get("doc_id"),
                "graph_source": bool(hit.get("graph_source")),
                "graph_relation": hit.get("graph_relation") or hit.get("relation"),
                "rerank": hit.get("rerank", {}),
            }
            for hit in hits[: min(8, len(hits))]
        ]
        direct_evidence_hit_ids = [
            hit["result_id"]
            for hit in hits
            if hit.get("result_type") == "evidence" and hit.get("result_id")
        ]
        retrieval_run_id = record_retrieval_run(
            connection,
            query=query,
            query_type=rewritten.query_type,
            doc_scope=preferred_doc_id or "global",
            retrieved_evidence_ids=direct_evidence_hit_ids,
            reranked_ids=[
                f"{hit.get('result_type')}:{hit.get('result_id')}"
                for hit in hits
                if hit.get("result_type") and hit.get("result_id")
            ],
            scores={
                f"{hit.get('result_type')}:{hit.get('result_id')}": hit.get("score")
                for hit in hits
                if hit.get("result_type") and hit.get("result_id")
            },
            metadata={
                "limit": limit,
                "retrieval_plan": retrieval_plan,
                "topic_resolution": topic_resolution.to_dict(),
                "hit_count": len(hits),
                "candidate_count_before_limit": len(reranked_hits),
                "direct_routing_hit_count": len(routing_hits),
                "graph_hit_count": len(graph_hits),
                "direct_evidence_hit_ids": direct_evidence_hit_ids,
                "linked_evidence_ids": linked_evidence_ids,
                "linked_evidence_count": len(linked_evidence_ids),
                "rewrite": rewritten.to_dict(),
                "retrieval_rewrite": retrieval_rewritten.to_dict(),
                "rerank_explanations": rerank_explanations,
            },
        )
        connection.commit()

        return {
            "query": query,
            "rewrite": rewritten.to_dict(),
            "query_expansion": expansion.to_dict(),
            "advanced_query_plan": advanced_plan.to_dict(),
            "retrieval_rewrite": retrieval_rewritten.to_dict(),
            "debug_query": {
                "final_query_type": rewritten.query_type,
                "final_normalized_query": rewritten.normalized_query,
                "final_target_topic": rewritten.target_topic,
                "protected_anchor_terms": rewritten.protected_anchor_terms,
                "rewrite_override_applied": rewritten.rewrite_override_applied,
                "semantic_quality_flags": rewritten.semantic_quality_flags,
                "expansion_used_llm": expansion.used_llm,
                "expansion_intent_candidates": expansion.intent_candidates,
                "expansion_confidence": expansion.confidence,
                "advanced_planner_enabled": advanced_plan.enabled,
                "advanced_planner_used_llm": advanced_plan.used_llm,
                "advanced_planner_confidence": advanced_plan.confidence,
                "advanced_planner_skip_reason": advanced_plan.skip_reason,
            },
            "preferred_doc_id": preferred_doc_id,
            "topic_resolution": topic_resolution.to_dict(),
            "retrieval_run_id": retrieval_run_id,
            "retrieval_plan": retrieval_plan,
            "rerank_explanations": rerank_explanations,
            "hit_count": len(hits),
            "documents": document_items,
            "hits": hits,
            "evidence": evidence_items,
            "facts": fact_items,
            "entities": entity_items,
            "topic_entities": topic_entity_items,
            "graph_edges": edge_items,
            "graph_candidates": [candidate.to_hit() for candidate in graph_candidates],
            "wiki_pages": wiki_items,
            "wiki_chunks": wiki_chunk_items,
            "topic_objects": topic_objects,
            "knowledge_subgraph": knowledge_subgraph,
            "evidence_judgement": evidence_judgement.to_dict(),
        }
    finally:
        connection.close()


def _inject_exact_standard_hits(connection, query: str, hits: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    standard = _extract_standard_from_query(query)
    if not standard:
        return hits

    normalized = _normalize_standard_code(standard)
    rows = connection.execute(
        """
        SELECT fact_id, source_doc_id, object_value, confidence
        FROM facts
        WHERE fact_type = 'document_standard'
        """
    ).fetchall()

    exact_hits: list[dict[str, object]] = []
    for row in rows:
        payload = _safe_json(row["object_value"])
        if isinstance(payload, dict):
            value = str(payload.get("value", ""))
            normalized_value = _normalize_standard_code(value)
            # Match by prefix so "QC/T1036" matches "QC/T1036—2016"
            if normalized_value == normalized or normalized_value.startswith(normalized + "—") or normalized_value.startswith(normalized + "-"):
                exact_hits.append(
                    {
                        "result_type": "fact",
                        "result_id": row["fact_id"],
                        "doc_id": row["source_doc_id"],
                        "page_no": 1,
                        "score": max(0.99, float(row["confidence"] or 0)),
                        "snippet": f"standard_code {row['object_value']}",
                    }
                )

    return _merge_injected_hits(hits, exact_hits, limit, force_injected=True, minimum_limit=len(exact_hits))


def _safe_json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _doc_title_matches(connection, doc_id: str, terms: list[str]) -> bool:
    """Check if any search term appears in the document title."""
    if not doc_id or not terms:
        return False
    row = connection.execute(
        "SELECT source_filename FROM documents WHERE doc_id = ?",
        (doc_id,),
    ).fetchone()
    if not row:
        return False
    title = str(row["source_filename"] or "").lower()
    for term in terms:
        if len(term) >= 2 and term.lower() in title:
            return True
    return False


def _extract_standard_from_query(query: str) -> str | None:
    match = re.search(r"(?:GB/T|GBT|GB|ISO/IEC|ISO|IEC|QC/T|QCT|QC)\s*[\d.]+(?:[.\-—:]\d+)*", query, re.I)
    return match.group(0) if match else None


def _normalize_standard_code(value: str) -> str:
    text = value.upper().replace("GBT", "GB/T").replace("GB T", "GB/T").replace("QC T", "QC/T")
    text = text.replace("-", "—")
    text = re.sub(r"\s+", "", text)
    return text


def _augment_standard_facts(connection, query: str, fact_items: list[dict[str, object]]) -> list[dict[str, object]]:
    standard = _extract_standard_from_query(query)
    if not standard:
        return fact_items

    normalized = _normalize_standard_code(standard)
    rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value, confidence,
               source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
        FROM facts
        WHERE fact_type IN ('document_standard', 'document_lifecycle', 'document_versioning')
        ORDER BY fact_id
        """
    ).fetchall()

    matched_doc_ids: set[str] = set()
    existing_ids = {item["fact_id"] for item in fact_items}
    augmented = list(fact_items)

    for row in rows:
        if row["fact_type"] != "document_standard":
            continue
        payload = _safe_json(row["object_value"])
        if not isinstance(payload, dict):
            continue
        value = _normalize_standard_code(str(payload.get("value", "")))
        if value == normalized or value.startswith(normalized + "—") or value.startswith(normalized + "-"):
            matched_doc_ids.add(row["source_doc_id"])
            if row["fact_id"] not in existing_ids:
                augmented.append(_row_to_fact(row))
                existing_ids.add(row["fact_id"])

    if not matched_doc_ids:
        return augmented

    for row in rows:
        if row["source_doc_id"] not in matched_doc_ids:
            continue
        if row["fact_type"] not in {"document_lifecycle", "document_versioning"}:
            continue
        if row["fact_id"] in existing_ids:
            continue
        augmented.append(_row_to_fact(row))
        existing_ids.add(row["fact_id"])

    return augmented


def _augment_parameter_facts(connection, rewritten, fact_items: list[dict[str, object]]) -> list[dict[str, object]]:
    """Inject parameter_value facts for parameter_lookup queries."""
    if getattr(rewritten, "query_type", "") != "parameter_lookup":
        return fact_items
    existing_ids = {item["fact_id"] for item in fact_items}
    # Check if we already have parameter_value facts
    if any(item.get("fact_type") == "parameter_value" for item in fact_items):
        return fact_items
    rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value, confidence,
               source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
        FROM facts
        WHERE fact_type = 'parameter_value'
        ORDER BY fact_id
        """
    ).fetchall()
    augmented = list(fact_items)
    for row in rows:
        if row["fact_id"] not in existing_ids:
            augmented.append(_row_to_fact(row))
            existing_ids.add(row["fact_id"])
    return augmented


def _inject_direct_term_definition_hits(connection, rewritten, hits: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    if rewritten.query_type != "definition":
        return hits
    acronyms = _short_definition_acronyms(rewritten)
    # Only fall back to full CJK term matching when there is no short acronym.
    # An acronym (CP, CC) is a stronger signal and is handled by the acronym
    # branch; term matching here is specifically for definition queries whose
    # subject is a full Chinese term (e.g. '控制导引电路') that yields no
    # acronym. Injecting term_definition candidates alongside an acronym
    # would dilute the acronym's authoritative definition.
    terms = [] if acronyms else _definition_term_candidates(rewritten)
    if not acronyms and not terms:
        return hits

    direct_hits: list[dict[str, object]] = []
    for acronym in acronyms[:4]:
        rows = connection.execute(
            """
            SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                   object_value, confidence
            FROM facts
            WHERE fact_type IN ('term_definition', 'concept_definition')
              AND (
                object_value LIKE ?
                OR object_value LIKE ?
                OR object_value LIKE ?
              )
            ORDER BY confidence DESC, fact_id ASC
            LIMIT ?
            """,
            (
                f"%; {acronym}%",
                f"%；{acronym}%",
                f"% {acronym}%定义%",
                limit,
            ),
        ).fetchall()
        for row in rows:
            payload = _safe_json(row["object_value"])
            blob = json.dumps(payload, ensure_ascii=False)
            score = 2.4
            if acronym == "CC" and "连接确认" in blob:
                score += 1.2
            direct_hits.append(
                {
                    "result_type": "fact",
                    "result_id": row["fact_id"],
                    "doc_id": row["source_doc_id"],
                    "page_no": row["page_no"],
                    "score": score,
                    "snippet": f"direct_term_definition {blob[:1200]}",
                    "channel": "direct_term_definition",
                    "channels": ["direct_term_definition"],
                }
            )

    for term in terms[:6]:
        rows = connection.execute(
            """
            SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                   object_value, confidence
            FROM facts
            WHERE fact_type IN ('term_definition', 'concept_definition')
              AND object_value LIKE ?
            ORDER BY confidence DESC, fact_id ASC
            LIMIT ?
            """,
            (f"%{term}%", limit),
        ).fetchall()
        for row in rows:
            fact_id = row["fact_id"]
            if any(h.get("result_id") == fact_id for h in direct_hits if isinstance(h, dict)):
                continue
            payload = _safe_json(row["object_value"])
            blob = json.dumps(payload, ensure_ascii=False)
            # Prefer authoritative dictionary terms: the `term` field that
            # *starts with* the query term (after stripping markdown **) is the
            # canonical definition, not a long sentence that merely contains it.
            term_text = str((payload or {}).get("term") or "")
            stripped_term = term_text.replace("*", "").strip()
            if term and stripped_term.startswith(term):
                score = 3.6
            elif term and term in term_text and len(stripped_term) <= 40:
                score = 3.2
            elif term and term in term_text:
                score = 3.0
            else:
                score = 2.6
            direct_hits.append(
                {
                    "result_type": "fact",
                    "result_id": fact_id,
                    "doc_id": row["source_doc_id"],
                    "page_no": row["page_no"],
                    "score": score,
                    "snippet": f"direct_term_definition {blob[:1200]}",
                    "channel": "direct_term_definition",
                    "channels": ["direct_term_definition"],
                }
            )

    return _merge_injected_hits(hits, direct_hits, limit)


def _inject_direct_requirement_hits(connection, rewritten, hits: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    if rewritten.query_type not in {"constraint", "parameter_lookup"}:
        return hits
    search_terms = [
        str(getattr(rewritten, "target_topic", "") or "").strip(),
        str(getattr(rewritten, "normalized_query", "") or "").strip(),
        *[str(item).strip() for item in getattr(rewritten, "must_terms", [])],
    ]
    terms: list[str] = []
    for term in search_terms:
        if not term or term in terms:
            continue
        if len(term) < 2:
            continue
        if term.casefold() in {"requirement", "requirements", "shall", "要求"}:
            continue
        terms.append(term)

    # Extract short keywords (2-4 chars) from terms for better matching
    short_keywords: list[str] = []
    for term in terms:
        # Extract Chinese keywords (2-4 chars)
        chars = re.findall(r"[一-鿿]{2,4}", term)
        for kw in chars:
            if kw not in short_keywords and kw not in terms:
                short_keywords.append(kw)
        # Extract English acronyms (2-6 uppercase chars)
        acronyms = re.findall(r"[A-Z]{2,6}", term)
        for acr in acronyms:
            if acr not in short_keywords and acr not in terms:
                short_keywords.append(acr)

    # Combine terms with short keywords for search
    all_search_terms = terms + short_keywords
    if not all_search_terms:
        return hits

    # Extract 2-char Chinese fragments for fine-grained LIKE matching
    cjk_frags: list[str] = []
    for term in terms:
        chars = re.findall(r"[一-鿿]", term)
        for i in range(len(chars) - 1):
            frag = chars[i] + chars[i + 1]
            if frag not in cjk_frags and frag not in terms:
                cjk_frags.append(frag)

    direct_hits: list[dict[str, object]] = []
    seen: set[str] = set()
    # Search with full terms first (higher priority)
    for term in all_search_terms[:6]:
        rows = connection.execute(
            """
            SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                   object_value, confidence
            FROM facts
            WHERE fact_type IN ('requirement', 'threshold', 'table_requirement')
              AND object_value LIKE ?
            ORDER BY confidence DESC, fact_id ASC
            LIMIT ?
            """,
            (f"%{term}%", limit),
        ).fetchall()
        for row in rows:
            if row["fact_id"] in seen:
                continue
            seen.add(row["fact_id"])
            payload = _safe_json(row["object_value"])
            blob = json.dumps(payload, ensure_ascii=False)
            # Boost score if document title matches query terms
            doc_title_match = _doc_title_matches(connection, row["source_doc_id"], terms)
            score = 2.2 + (0.3 if doc_title_match else 0.0)
            direct_hits.append(
                {
                    "result_type": "fact",
                    "result_id": row["fact_id"],
                    "doc_id": row["source_doc_id"],
                    "page_no": row["page_no"],
                    "score": score,
                    "snippet": f"direct_requirement {blob[:1200]}",
                    "channel": "direct_requirement",
                    "channels": ["direct_requirement"],
                }
            )

    # Supplement with 2-char CJK fragment matches when full terms miss.
    # Filter out overly-generic fragments (matching too many rows) to ensure
    # specific fragments like "保护重启" are not drowned by generic ones like "逆变".
    # Phase 1: Search with selective (low-frequency) fragments only.
    # Phase 2: If still insufficient, search with all fragments.
    MAX_GENERIC_MATCH_COUNT = 20
    selective_frags = []
    generic_frags = []
    for frag in cjk_frags[:6]:
        frag_count = connection.execute(
            "SELECT count(*) FROM facts WHERE fact_type IN ('requirement', 'threshold', 'table_requirement') AND object_value LIKE ?",
            (f"%{frag}%",),
        ).fetchone()[0]
        if frag_count <= MAX_GENERIC_MATCH_COUNT:
            selective_frags.append(frag)
        else:
            generic_frags.append(frag)

    for phase_frags in (selective_frags, cjk_frags[:6]):
        if not phase_frags or len(direct_hits) >= limit:
            continue
        like_clauses = " OR ".join(f"object_value LIKE ?" for _ in phase_frags[:6])
        frag_params = [f"%{frag}%" for frag in phase_frags[:6]]
        rows = connection.execute(
            f"""
            SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                   object_value, confidence
            FROM facts
            WHERE fact_type IN ('requirement', 'threshold', 'table_requirement')
              AND ({like_clauses})
            ORDER BY confidence DESC, fact_id ASC
            LIMIT ?
            """,
            [*frag_params, min(limit * 3, 30)],
        ).fetchall()
        # Score each row by how many fragments it matches
        frag_scored: list[tuple[float, dict]] = []
        for row in rows:
            if row["fact_id"] in seen:
                continue
            blob = str(row["object_value"] or "")
            match_count = sum(1 for frag in cjk_frags[:6] if frag in blob)
            score = 1.5 + 0.2 * match_count  # more matching frags = higher score
            payload = _safe_json(row["object_value"])
            frag_blob = json.dumps(payload, ensure_ascii=False)
            frag_scored.append((score, {
                "result_type": "fact",
                "result_id": row["fact_id"],
                "doc_id": row["source_doc_id"],
                "page_no": row["page_no"],
                "score": score,
                "snippet": f"direct_requirement_frag {frag_blob[:1200]}",
                "channel": "direct_requirement",
                "channels": ["direct_requirement"],
            }))
        # Sort by fragment-match score (descending) then take top results
        frag_scored.sort(key=lambda x: x[0], reverse=True)
        for _, hit in frag_scored[:limit]:
            seen.add(hit["result_id"])
            direct_hits.append(hit)

    return _merge_injected_hits(hits, direct_hits, limit, force_injected=True, minimum_limit=limit)


def _inject_direct_test_method_hits(connection, rewritten, hits: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    if rewritten.query_type != "test_method_lookup":
        return hits

    query_text = " ".join(
        str(item or "")
        for item in [
            getattr(rewritten, "original_query", ""),
            getattr(rewritten, "normalized_query", ""),
            getattr(rewritten, "target_topic", ""),
            *getattr(rewritten, "must_terms", []),
            *getattr(rewritten, "aliases", []),
        ]
    )
    required_terms = ["试验"]
    if "过压" in query_text:
        required_terms.append("过压")
    if "欠压" in query_text:
        required_terms.append("欠压")
    if "输入" in query_text:
        required_terms.append("输入")
    if "输出" in query_text:
        required_terms.append("输出")
    object_terms: list[str] = []
    if re.search(r"\bOBC\b|车载充电机|on-?board charger", query_text, re.I):
        object_terms.extend(["车载充电机", "电动汽车用传导式车载充电机"])
    if not required_terms:
        return hits

    where_parts = ["fact_type = 'process_fact'"]
    params: list[object] = []
    for term in required_terms:
        where_parts.append("object_value LIKE ?")
        params.append(f"%{term}%")
    if object_terms:
        where_parts.append("(" + " OR ".join("object_value LIKE ?" for _ in object_terms) + ")")
        params.extend(f"%{term}%" for term in object_terms)
    params.append(limit)
    rows = connection.execute(
        f"""
        SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
               object_value, confidence
        FROM facts
        WHERE {' AND '.join(where_parts)}
        ORDER BY confidence DESC, fact_id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()

    direct_hits: list[dict[str, object]] = []
    for row in rows:
        payload = _safe_json(row["object_value"])
        blob = json.dumps(payload, ensure_ascii=False)
        direct_hits.append(
            {
                "result_type": "fact",
                "result_id": row["fact_id"],
                "doc_id": row["source_doc_id"],
                "page_no": row["page_no"],
                "score": 5.2,
                "snippet": f"direct_test_method {blob[:1200]}",
                "channel": "direct_test_method",
                "channels": ["direct_test_method"],
            }
        )

    return _merge_injected_hits(hits, direct_hits, limit, force_injected=True, minimum_limit=limit)


def _short_definition_acronyms(rewritten) -> list[str]:
    values = [
        str(getattr(rewritten, "target_topic", "") or ""),
        str(getattr(rewritten, "normalized_query", "") or ""),
        *[str(item) for item in getattr(rewritten, "must_terms", [])],
        *[str(item) for item in getattr(rewritten, "protected_anchor_terms", [])],
    ]
    acronyms: list[str] = []
    for value in values:
        cleaned = value.strip().upper()
        if re.fullmatch(r"[A-Z]{2,6}", cleaned) and cleaned not in {"GB", "GBT", "ISO", "IEC", "QC"}:
            if cleaned not in acronyms:
                acronyms.append(cleaned)
    return acronyms


def _definition_term_candidates(rewritten) -> list[str]:
    """Non-acronym (CJK / multi-word) terms for definition queries.

    `_short_definition_acronyms` only captures pure-Latin acronyms (CC, CP).
    Definition queries with full Chinese terms (e.g. '控制导引电路') return
    no acronyms, so the authoritative `term_definition` fact is never
    injected. This collects the substantive CJK terms from the rewritten
    query so they can be matched against `term_definition` / `concept_definition`
    facts and injected as high-confidence hits.
    """
    raw = [
        str(getattr(rewritten, "target_topic", "") or "").strip(),
        str(getattr(rewritten, "normalized_query", "") or "").strip(),
        *[str(item).strip() for item in getattr(rewritten, "aliases", []) or []],
        *[str(item).strip() for item in getattr(rewritten, "should_terms", []) or []],
        *[str(item).strip() for item in getattr(rewritten, "must_terms", []) or []],
    ]
    terms: list[str] = []
    seen_lower: set[str] = set()
    for value in raw:
        if not value:
            continue
        # Strip punctuation / question marks and whitespace.
        cleaned = re.sub(r"[\s\?\!_，.,;:：；()（）*]+", "", value)
        if not cleaned:
            continue
        # Skip pure-Latin acronyms (already handled) and overly short tokens.
        if re.fullmatch(r"[A-Za-z0-9/\-]+", cleaned):
            continue
        # Keep only tokens that contain at least one CJK run of length >= 2.
        cjk_runs = re.findall(r"[一-鿿]{2,}", cleaned)
        if not cjk_runs:
            continue
        for run in cjk_runs:
            key = run.lower()
            if key in seen_lower:
                continue
            # Skip generic noise fragments.
            if run in {"是什么", "是什么意思", "是什么意思吗", "指的是"}:
                continue
            seen_lower.add(key)
            terms.append(run)
    return terms


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


def _filter_hits_for_exact_terms(rewritten, hits: list[dict[str, object]]) -> list[dict[str, object]]:
    exact_terms = [term for term in rewritten.must_terms if re.fullmatch(r"[A-Z][A-Z0-9/-]{1,}", str(term or ""))]
    if not exact_terms:
        return hits
    if rewritten.query_type not in {"definition", "comparison", "general_search"}:
        return hits

    filtered = [hit for hit in hits if _hit_matches_exact_terms(hit, exact_terms)]
    return filtered or hits


def _hit_matches_exact_terms(hit: dict[str, object], exact_terms: list[str]) -> bool:
    blob = json.dumps(hit, ensure_ascii=False).upper()
    return any(term.upper() in blob for term in exact_terms)


def _inject_direct_wiki_hits(connection, rewritten, hits: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    if rewritten.query_type not in {"definition", "parameter_lookup", "timing_lookup", "comparison", "constraint"}:
        return hits

    search_terms = [
        rewritten.normalized_query,
        *rewritten.must_terms,
        *rewritten.aliases,
        *rewritten.should_terms,
    ]
    search_terms = [str(term).strip() for term in search_terms if str(term).strip()]

    wiki_hits: list[dict[str, object]] = []
    for term in search_terms[:10]:
        rows = connection.execute(
            """
            SELECT w.page_id, w.page_type, w.title, w.slug, json_extract(w.source_doc_ids_json, '$[0]') AS doc_id
            FROM wiki_pages w
            LEFT JOIN entities e ON e.entity_id = w.entity_id
            WHERE (w.title LIKE ? OR w.slug LIKE ?)
              AND (w.entity_id IS NULL OR e.entity_status = 'ready')
            LIMIT ?
            """,
            (f"%{term}%", f"%{term}%", limit),
        ).fetchall()
        for row in rows:
            bonus = 0.88
            if rewritten.query_type == "timing_lookup" and row["page_type"] == "process":
                bonus = 1.08
            elif rewritten.query_type == "parameter_lookup" and row["page_type"] == "parameter_group":
                bonus = 1.08
            elif rewritten.query_type == "parameter_lookup" and row["page_type"] == "parameter":
                bonus = 1.16
            elif rewritten.query_type == "definition" and row["page_type"] in {"term", "concept", "document"}:
                bonus = 1.02
            elif rewritten.query_type == "definition":
                bonus = 0.18
            elif rewritten.query_type == "comparison" and row["page_type"] in {"term", "concept"}:
                bonus = 1.0
            elif rewritten.query_type == "comparison" and row["page_type"] == "comparison":
                bonus = 1.08
            elif rewritten.query_type == "constraint" and row["page_type"] == "constraint":
                bonus = 1.08
            elif rewritten.query_type == "constraint" and row["page_type"] in {"term", "process", "parameter_group"}:
                bonus = 0.96
            title = str(row["title"] or "").strip()
            if rewritten.query_type == "constraint":
                target_terms = _query_topic_terms(rewritten)
                if any(term and title == term for term in target_terms):
                    bonus += 0.4
                elif any(term and term in title for term in target_terms):
                    bonus += 0.2
            wiki_hits.append(
                {
                    "result_type": "wiki",
                    "result_id": row["page_id"],
                    "doc_id": row["doc_id"],
                    "page_no": 1,
                    "score": bonus,
                    "snippet": f"{row['title']} {row['slug']}",
                }
            )

    return _merge_injected_hits(hits, wiki_hits, limit)


def _augment_query_wiki_items(connection, rewritten, wiki_items: list[dict[str, object]], doc_ids: list[str], limit: int) -> list[dict[str, object]]:
    if rewritten.query_type not in {"definition", "parameter_lookup", "timing_lookup", "comparison", "constraint"}:
        return wiki_items

    search_terms = [
        rewritten.normalized_query,
        *rewritten.must_terms,
        *rewritten.aliases,
        *rewritten.should_terms,
    ]
    search_terms = [str(term).strip() for term in search_terms if str(term).strip()]

    allowed_doc_ids = set(doc_ids)
    existing_ids = {item["page_id"] for item in wiki_items}
    extra_items: list[dict[str, object]] = []
    for term in search_terms[:10]:
        rows = connection.execute(
            """
            SELECT w.page_id, w.page_type, w.title, w.slug, w.entity_id, w.trust_status,
                   w.file_path, w.source_fact_ids_json,
                   json_extract(w.source_doc_ids_json, '$[0]') AS doc_id
            FROM wiki_pages w
            LEFT JOIN entities e ON e.entity_id = w.entity_id
            WHERE (w.title LIKE ? OR w.slug LIKE ?)
              AND (w.entity_id IS NULL OR e.entity_status = 'ready')
            LIMIT ?
            """,
            (f"%{term}%", f"%{term}%", limit),
        ).fetchall()
        for row in rows:
            if row["page_id"] in existing_ids:
                continue
            if allowed_doc_ids and row["doc_id"] not in allowed_doc_ids:
                continue
            payload = dict(row)
            payload.pop("doc_id", None)
            extra_items.append(payload)
            existing_ids.add(row["page_id"])
    if rewritten.query_type == "constraint":
        topic_terms = _query_topic_terms(rewritten)
        extra_items.sort(
            key=lambda item: (
                0 if any(term and str(item.get("title") or "") == term for term in topic_terms) else
                1 if any(term and term in str(item.get("title") or "") for term in topic_terms) else
                2,
                str(item.get("title") or ""),
            )
        )
    elif rewritten.query_type == "parameter_lookup":
        topic_terms = _query_topic_terms(rewritten)
        extra_items.sort(
            key=lambda item: (
                0 if str(item.get("page_type") or "") == "parameter" and any(term and str(item.get("title") or "") == term for term in topic_terms) else
                1 if str(item.get("page_type") or "") == "parameter" else
                2 if str(item.get("page_type") or "") == "parameter_group" else
                3,
                str(item.get("title") or ""),
            )
        )
    return wiki_items + extra_items


def _augment_facts_from_wiki(connection, fact_items: list[dict[str, object]], wiki_items: list[dict[str, object]], doc_ids: list[str]) -> list[dict[str, object]]:
    allowed_doc_ids = set(doc_ids)
    existing_ids = {item["fact_id"] for item in fact_items}
    extra_fact_ids: list[str] = []
    for item in wiki_items:
        source_fact_ids = _safe_json(item.get("source_fact_ids_json"))
        if isinstance(source_fact_ids, list):
            for fact_id in source_fact_ids:
                value = str(fact_id).strip()
                if value and value not in existing_ids and value not in extra_fact_ids:
                    extra_fact_ids.append(value)
    # Cap augmentation to avoid flooding context with hundreds of facts
    extra_fact_ids = extra_fact_ids[:40]
    if not extra_fact_ids:
        return fact_items

    placeholders = ",".join("?" for _ in extra_fact_ids)
    rows = connection.execute(
        f"""
        SELECT fact_id, fact_type, predicate, object_value, confidence,
               source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
        FROM facts
        WHERE fact_id IN ({placeholders})
        ORDER BY confidence DESC, fact_id ASC
        """,
        extra_fact_ids,
    ).fetchall()
    augmented = list(fact_items)
    for row in rows:
        if allowed_doc_ids and row["source_doc_id"] not in allowed_doc_ids:
            continue
        item = _row_to_fact(row)
        item["_source_from_wiki"] = True
        if item["fact_id"] not in existing_ids:
            augmented.append(item)
            existing_ids.add(item["fact_id"])
    return augmented


def _linked_evidence_ids_for_facts(connection, fact_ids: list[str]) -> list[str]:
    cleaned = sorted({str(fact_id).strip() for fact_id in fact_ids if str(fact_id).strip()})
    if not cleaned:
        return []
    placeholders = ",".join("?" for _ in cleaned)
    rows = connection.execute(
        f"""
        SELECT DISTINCT evidence_id
        FROM fact_evidence_map
        WHERE fact_id IN ({placeholders})
        ORDER BY evidence_id ASC
        """,
        cleaned,
    ).fetchall()
    return [str(row["evidence_id"]) for row in rows if row["evidence_id"]]


def _query_topic_terms(rewritten) -> list[str]:
    values = [
        str(getattr(rewritten, "target_topic", "") or "").strip(),
        str(getattr(rewritten, "normalized_query", "") or "").strip(),
        *[str(item).strip() for item in getattr(rewritten, "must_terms", [])],
        *[str(item).strip() for item in getattr(rewritten, "aliases", [])],
    ]
    terms: list[str] = []
    for value in values:
        if not value:
            continue
        cleaned = re.sub(r"(有什么要求|要求是什么|应满足什么|应符合什么)$", "", value).strip()
        cleaned = cleaned.replace("的要求", "").replace("功能要求", "").replace("功能", "").strip()
        if cleaned and cleaned not in terms:
            terms.append(cleaned)
    return terms[:10]


def _resolve_topic_objects(rewritten, wiki_items: list[dict[str, object]]) -> list[dict[str, object]]:
    topic_terms = _query_topic_terms(rewritten)
    if not topic_terms:
        return []

    parameter_anchor_terms = {
        term.upper()
        for term in topic_terms
        if re.fullmatch(r"[A-Z]{1,4}\d*", term.upper())
    }
    scored: list[tuple[tuple[int, int], dict[str, object]]] = []
    for item in wiki_items:
        title = str(item.get("title") or "").strip()
        page_type = str(item.get("page_type") or "").strip()
        entity_id = str(item.get("entity_id") or "").strip()
        if not title:
            continue
        score = 0
        priority = 2
        if any(term and title == term for term in topic_terms):
            score += 4
        if any(term and term in title for term in topic_terms):
            score += 2
        if rewritten.query_type == "constraint" and page_type == "constraint":
            score += 2
            priority = min(priority, 0)
        elif rewritten.query_type == "comparison" and page_type == "comparison":
            score += 2
            priority = min(priority, 0)
        elif rewritten.query_type == "timing_lookup" and page_type == "process":
            score += 2
            priority = min(priority, 0)
        elif rewritten.query_type == "parameter_lookup" and page_type == "parameter_group":
            score += 2
            priority = min(priority, 1)
        elif rewritten.query_type == "parameter_lookup" and page_type == "parameter":
            score += 4
            priority = min(priority, 0)
        elif rewritten.query_type == "parameter_lookup" and page_type == "term":
            if title.upper() in parameter_anchor_terms:
                score += 5
                priority = min(priority, 0)
            elif any(term and term in title for term in topic_terms):
                score += 2
                priority = min(priority, 1)
        elif rewritten.query_type == "definition" and page_type in {"term", "concept"}:
            score += 2
            priority = min(priority, 0)
        if entity_id and rewritten.query_type == "parameter_lookup" and title.upper() in parameter_anchor_terms:
            score += 2
            priority = min(priority, 0)
        if score > 0:
            scored.append(((priority, -score), item))

    scored.sort(key=lambda pair: (pair[0][0], pair[0][1], str(pair[1].get("title") or "")))
    topic_objects: list[dict[str, object]] = []
    seen: set[str] = set()
    for _, item in scored:
        page_id = str(item.get("page_id") or "")
        if page_id and page_id not in seen:
            seen.add(page_id)
            topic_objects.append(item)
    return topic_objects[:8]


def _hydrate_topic_object_entities(connection, topic_objects: list[dict[str, object]]) -> list[dict[str, object]]:
    hydrated: list[dict[str, object]] = []
    for item in topic_objects:
        cloned = dict(item)
        if not cloned.get("entity_id"):
            title = str(cloned.get("title") or "").strip()
            page_type = str(cloned.get("page_type") or "").strip()
            if title:
                entity_type = None
                if page_type == "constraint":
                    entity_type = "constraint_topic"
                elif page_type == "comparison":
                    entity_type = "comparison_topic"
                elif page_type == "process":
                    entity_type = "process"
                elif page_type == "parameter":
                    entity_type = "parameter_topic"
                elif page_type == "parameter_group":
                    entity_type = "parameter_group"
                elif page_type in {"term", "concept"}:
                    entity_type = "term"
                if entity_type:
                    row = connection.execute(
                        """
                        SELECT entity_id
                        FROM entities
                        WHERE entity_type = ? AND (canonical_name = ? OR canonical_name LIKE ?)
                        LIMIT 1
                        """,
                        (entity_type, title, f"%{title}%"),
                    ).fetchone()
                    if row:
                        cloned["entity_id"] = row["entity_id"]
        hydrated.append(cloned)
    return hydrated


def _compact_topic_objects(rewritten, topic_objects: list[dict[str, object]]) -> list[dict[str, object]]:
    page_type_priority_by_query = {
        "definition": {"term": 0, "concept": 1, "document": 2},
        "comparison": {"comparison": 0, "term": 1},
        "constraint": {"constraint": 0, "term": 1, "process": 2},
        "timing_lookup": {"process": 0, "term": 1, "parameter_group": 2},
        "parameter_lookup": {"parameter": 0, "parameter_group": 1, "term": 2},
    }
    priority_map = page_type_priority_by_query.get(rewritten.query_type, {})

    deduped_by_entity: dict[str, dict[str, object]] = {}
    passthrough: list[dict[str, object]] = []
    for item in topic_objects:
        entity_id = str(item.get("entity_id") or "").strip()
        if not entity_id:
            passthrough.append(item)
            continue
        existing = deduped_by_entity.get(entity_id)
        if existing is None:
            deduped_by_entity[entity_id] = item
            continue
        current_priority = priority_map.get(str(item.get("page_type") or ""), 9)
        existing_priority = priority_map.get(str(existing.get("page_type") or ""), 9)
        if current_priority < existing_priority:
            deduped_by_entity[entity_id] = item

    ordered = list(deduped_by_entity.values()) + passthrough
    ordered.sort(
        key=lambda item: (
            priority_map.get(str(item.get("page_type") or ""), 9),
            str(item.get("title") or ""),
        )
    )
    return ordered[:8]


def _order_topic_entities(topic_entities: list[dict[str, object]], topic_objects: list[dict[str, object]]) -> list[dict[str, object]]:
    entity_order = [
        str(item.get("entity_id") or "").strip()
        for item in topic_objects
        if str(item.get("entity_id") or "").strip()
    ]
    order_index = {entity_id: index for index, entity_id in enumerate(entity_order)}
    return sorted(
        topic_entities,
        key=lambda item: (
            order_index.get(str(item.get("entity_id") or "").strip(), 99),
            str(item.get("canonical_name") or ""),
        ),
    )
