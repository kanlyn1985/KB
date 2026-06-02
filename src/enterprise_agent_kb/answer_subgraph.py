from __future__ import annotations

import json
import re
from pathlib import Path

from .config import AppPaths
from .db import connect
from .answer_query_parsing import _normalize_standard_code, _extract_standard_from_query


"""Knowledge subgraph signal application, topic alignment, and graph filtering for answer generation."""


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
        from .answer_api import _constraint_target_terms
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
