"""Constraint intent answer generation and fact selection."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .answer_query_parsing import _normalize_query_phrase
from .answer_subgraph import _prioritize_subgraph_facts
from .answer_utils import _safe_json, _truncate
from .config import AppPaths
from .db import connect


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
