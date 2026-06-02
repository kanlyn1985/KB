"""Local corpus and network-metadata context builders for case generation.

Extracted from `generated_tests._impl` to isolate the per-document
context assembly (local facts/evidence/wiki, network search metadata)
from the case-construction and orchestration logic.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from ..db import connect
from ._case_builders import MAX_CASE_COUNT, MIN_CASE_COUNT
from ._case_helpers import _safe_identifier, _safe_json

def _active_document_ids(paths: AppPaths) -> list[str]:
    connection = connect(paths.db_file)
    try:
        rows = connection.execute(
            """
            SELECT doc_id
            FROM documents
            WHERE is_active = 1
            ORDER BY doc_id
            """
        ).fetchall()
    finally:
        connection.close()
    return [str(row["doc_id"]) for row in rows]
def _target_case_count(page_count: int, fact_count: int, evidence_count: int) -> int:
    content_factor = min(20, max(0, fact_count // 8) + max(0, evidence_count // 6))
    proportional = max(MIN_CASE_COUNT, math.ceil(page_count * 0.55) + content_factor)
    return max(MIN_CASE_COUNT, min(MAX_CASE_COUNT, max(page_count, proportional)))
def _build_local_context(document, facts, evidence_rows, wiki_rows) -> dict[str, object]:
    fact_items = []
    for row in facts:
        fact_items.append(
            {
                "fact_type": row["fact_type"],
                "predicate": row["predicate"],
                "object_value": _safe_json(row["object_value"]),
                "qualifiers_json": _safe_json(row["qualifiers_json"]),
            }
        )

    evidence_items = [dict(row) for row in evidence_rows]
    wiki_items = [dict(row) for row in wiki_rows]

    standard_code = ""
    title = ""
    publication_date = ""
    effective_date = ""
    term_definitions: list[dict[str, str]] = []
    section_headings: list[dict[str, object]] = []

    for item in fact_items:
        payload = item["object_value"]
        if not isinstance(payload, dict):
            continue
        if item["fact_type"] == "document_standard" and not standard_code:
            candidate_standard = str(payload.get("value", "")).strip()
            if _is_valid_standard_code(candidate_standard):
                standard_code = candidate_standard
        elif item["fact_type"] == "document_title" and not title:
            title = str(payload.get("value", "")).strip()
        elif item["fact_type"] == "document_lifecycle" and item["predicate"] == "publication_date" and not publication_date:
            publication_date = str(payload.get("value", "")).strip()
        elif item["fact_type"] == "document_lifecycle" and item["predicate"] == "effective_date" and not effective_date:
            effective_date = str(payload.get("value", "")).strip()
        elif item["fact_type"] in {"term_definition", "concept_definition"}:
            term = str(payload.get("term", "")).strip()
            definition = str(payload.get("definition", "")).strip()
            if term and definition:
                term_definitions.append({"term": term, "definition": definition})
        elif item["fact_type"] == "section_heading":
            title_value = str(payload.get("title", "")).strip()
            if title_value:
                section_headings.append(
                    {
                        "title": title_value,
                        "page_no": int(item["qualifiers_json"].get("page_no", 0))
                        if isinstance(item["qualifiers_json"], dict)
                        else 0,
                    }
                )

    normalized_texts = [
        document["source_filename"],
        standard_code,
        title,
        publication_date,
        effective_date,
        *[json.dumps(item["object_value"], ensure_ascii=False) for item in fact_items],
        *[str(item["normalized_text"]) for item in evidence_items],
        *[str(item["title"]) for item in wiki_items],
    ]
    local_corpus = "\n".join(part for part in normalized_texts if part)

    return {
        "doc_id": document["doc_id"],
        "source_filename": document["source_filename"],
        "page_count": int(document["page_count"] or 0),
        "standard_code": standard_code,
        "title": title,
        "publication_date": publication_date,
        "effective_date": effective_date,
        "facts": fact_items,
        "evidence": evidence_items,
        "wiki": wiki_items,
        "term_definitions": term_definitions,
        "section_headings": section_headings,
        "local_corpus": local_corpus,
        "pages_with_evidence": sorted({int(item["page_no"]) for item in evidence_items if int(item.get("page_no") or 0) > 0}),
    }
def _network_cases_from_metadata(
    local_context: dict[str, object],
    metadata: dict[str, list[str]],
    source_url: str,
) -> list[dict[str, str]]:
    standard_code = str(local_context.get("standard_code", "")).strip()
    title = str(local_context.get("title", "")).strip()
    publication_date = str(local_context.get("publication_date", "")).strip()
    effective_date = str(local_context.get("effective_date", "")).strip()

    cases: list[dict[str, str]] = []
    if standard_code and _is_valid_standard_code(standard_code):
        cases.append(
            _case(
                "network_standard",
                f"{standard_code} 的标准号是什么？",
                standard_code,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )
    if publication_date:
        cases.append(
            _case(
                "network_publication_date",
                f"{standard_code or title} 的发布日期是什么？",
                publication_date,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )
    if effective_date:
        cases.append(
            _case(
                "network_effective_date",
                f"{standard_code or title} 的实施日期是什么？",
                effective_date,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )
    if title:
        cases.append(
            _case(
                "network_title",
                f"{standard_code or title} 的中文名称是什么？",
                title,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )

    for value in metadata.get("titles", [])[:3]:
        if value != title:
            cases.append(
                _case(
                    "network_title_variant",
                    f"{standard_code or title} 的名称或公开标题是什么？",
                    value,
                    source="network",
                    assert_mode="rich_answer",
                    source_url=source_url,
                )
            )

    for value in metadata.get("organizations", [])[:4]:
        cases.append(
            _case(
                "network_org",
                f"{standard_code or title} 的发布或起草信息中是否包含 {value}？",
                value,
                source="network",
                assert_mode="context_contains",
                source_url=source_url,
            )
        )

    for value in metadata.get("scope", [])[:4]:
        cases.append(
            _case(
                "network_scope",
                f"{standard_code or title} 适用于什么对象或范围？",
                value,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )

    return cases
def _doc_scope_label(local_context: dict[str, object]) -> str:
    standard_code = str(local_context.get("standard_code", "")).strip()
    if standard_code and _is_valid_standard_code(standard_code):
        return standard_code
    title = str(local_context.get("title", "")).strip()
    if title:
        return title
    source_filename = str(local_context.get("source_filename", "")).strip()
    if source_filename:
        return Path(source_filename).stem
    return str(local_context.get("doc_id", "")).strip()
def _scope_query(local_context: dict[str, object], query: str) -> str:
    scope = _doc_scope_label(local_context)
    query = re.sub(r"\s+", " ", query).strip()
    if not scope:
        return query
    if scope in query:
        return query
    return f"{scope}：{query}"
