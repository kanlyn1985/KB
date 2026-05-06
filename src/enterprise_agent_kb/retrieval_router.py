from __future__ import annotations

import json
import re
from pathlib import Path

from .config import AppPaths
from .db import connect
from .query_rewrite import RewrittenQuery
from .retrieval import search_knowledge_base_expanded


CHANNEL_PRIORITY: dict[str, list[str]] = {
    "definition": ["facts", "wiki", "evidence", "document"],
    "standard_lookup": ["document", "facts", "wiki", "evidence"],
    "lifecycle_lookup": ["document", "facts", "wiki", "evidence"],
    "timing_lookup": ["wiki", "facts", "evidence", "document"],
    "test_method_lookup": ["facts", "evidence", "wiki", "document"],
    "parameter_lookup": ["wiki", "facts", "evidence", "document"],
    "section_lookup": ["document", "facts", "evidence", "wiki"],
    "scope": ["document", "evidence", "facts", "wiki"],
    "constraint": ["facts", "evidence", "document", "wiki"],
    "comparison": ["facts", "document", "evidence", "wiki"],
    "general_search": ["evidence", "facts", "wiki", "document"],
    "no_answer_candidate": ["document", "facts"],
}

CHANNEL_BOOST = {
    "facts": 1.0,
    "evidence": 0.96,
    "wiki": 0.98,
    "document": 2.2,
}


def route_retrieval(
    workspace_root: Path,
    rewritten: RewrittenQuery,
    limit: int = 10,
    connection=None,
) -> dict[str, object]:
    own_connection = connection is None
    paths = AppPaths.from_root(workspace_root)
    if own_connection:
        connection = connect(paths.db_file)

    try:
        channels = CHANNEL_PRIORITY.get(rewritten.query_type, CHANNEL_PRIORITY["general_search"])
        limit_per_channel = max(limit * 2, 12)

        channel_hits: dict[str, list[dict[str, object]]] = {}
        for channel in channels:
            if channel == "document":
                hits = _document_hits(connection, rewritten, limit_per_channel)
            else:
                hits = _structured_hits(paths.root, rewritten, channel, limit_per_channel, connection)
            for item in hits:
                item["channel"] = channel
                item["score"] = round(float(item.get("score") or 0) * CHANNEL_BOOST.get(channel, 1.0), 6)
            channel_hits[channel] = hits

        merged = _merge_channel_hits(channel_hits)
        merged.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return {
            "query_type": rewritten.query_type,
            "channels": channels,
            "channel_hits": channel_hits,
            "hits": merged[:limit],
        }
    finally:
        if own_connection:
            connection.close()


def _structured_hits(
    workspace_root: Path,
    rewritten: RewrittenQuery,
    channel: str,
    limit: int,
    connection,
) -> list[dict[str, object]]:
    seeds = [rewritten.normalized_query, *rewritten.must_terms, *rewritten.should_terms]
    merged: dict[tuple[str, str], dict[str, object]] = {}
    allowed_type = {"facts": "fact", "evidence": "evidence", "wiki": "wiki"}[channel]

    for seed in seeds:
        if not seed:
            continue
        hits = search_knowledge_base_expanded(
            workspace_root,
            seed,
            limit=limit,
            connection=connection,
            result_types={allowed_type},
        )
        for hit in hits:
            if hit["result_type"] != allowed_type:
                continue
            key = (hit["result_type"], hit["result_id"])
            existing = merged.get(key)
            if existing is None or float(hit["score"] or 0) > float(existing["score"] or 0):
                merged[key] = dict(hit)

    if channel == "facts" and rewritten.query_type in {
        "constraint",
        "section_lookup",
        "parameter_lookup",
        "test_method_lookup",
        "timing_lookup",
        "lifecycle_lookup",
        "definition",
    }:
        for hit in _direct_fact_hits(connection, rewritten, limit):
            key = (hit["result_type"], hit["result_id"])
            existing = merged.get(key)
            if existing is None or float(hit["score"] or 0) > float(existing["score"] or 0):
                merged[key] = dict(hit)
    merged_hits = list(merged.values())
    merged_hits.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return merged_hits[:limit]


def _document_hits(connection, rewritten: RewrittenQuery, limit: int) -> list[dict[str, object]]:
    seeds = [rewritten.normalized_query, *rewritten.must_terms, *rewritten.should_terms]
    hits: list[dict[str, object]] = []
    seen: set[str] = set()

    rows = connection.execute(
        """
        SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
        FROM documents
        ORDER BY ingest_time DESC
        """
    ).fetchall()
    for row in rows:
        blob = _normalize_document_blob(json.dumps(dict(row), ensure_ascii=False))
        score = 0.0
        for term in seeds:
            normalized = _normalize_document_blob(str(term or ""))
            if not normalized:
                continue
            if normalized in blob:
                score += 1.0
        if score <= 0:
            continue
        doc_id = row["doc_id"]
        if doc_id in seen:
            continue
        seen.add(doc_id)
        hits.append(
            {
                "result_type": "document",
                "result_id": doc_id,
                "doc_id": doc_id,
                "page_no": 1,
                "score": round(score / max(len(seeds), 1), 6),
                "snippet": row["source_filename"],
            }
        )
        if len(hits) >= limit:
            break
    return hits


def _normalize_document_blob(value: str) -> str:
    text = value.lower()
    text = text.replace("—", "-").replace("_", "").replace("/", "").replace("\\", "")
    text = text.replace("gb t", "gbt").replace("qc t", "qct")
    return "".join(text.split())


def _merge_channel_hits(channel_hits: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for channel, hits in channel_hits.items():
        for hit in hits:
            key = (hit["result_type"], hit["result_id"])
            existing = merged.get(key)
            if existing is None or float(hit["score"] or 0) > float(existing["score"] or 0):
                merged[key] = dict(hit)
                merged[key]["channels"] = [channel]
            elif channel not in existing.get("channels", []):
                existing["channels"].append(channel)
    return list(merged.values())


def _direct_fact_hits(connection, rewritten: RewrittenQuery, limit: int) -> list[dict[str, object]]:
    search_terms = [
        *rewritten.must_terms,
        *_test_method_variant_terms(rewritten),
        *rewritten.should_terms,
        rewritten.normalized_query,
        *_process_alias_terms(rewritten),
    ]
    search_terms = [term for term in search_terms if term]
    hits: list[dict[str, object]] = []
    seen: set[str] = set()

    for term in search_terms[:6]:
        rows = connection.execute(
            """
            SELECT fact_id, fact_type, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                   object_value, confidence
            FROM facts
            WHERE fact_type IN ('requirement', 'table_requirement', 'threshold', 'parameter_value', 'process_fact', 'transition_fact', 'section_heading')
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
            fact_type = str(row["fact_type"] or "")
            score = _direct_fact_score(rewritten, fact_type, str(row["object_value"] or ""), term, float(row["confidence"] or 0))
            hits.append(
                {
                    "result_type": "fact",
                    "result_id": row["fact_id"],
                    "doc_id": row["source_doc_id"],
                    "page_no": row["page_no"],
                    "score": score,
                    "snippet": f"knowledge_unit_fact {row['object_value']}",
                }
            )
    if rewritten.query_type in {"lifecycle_lookup", "timing_lookup"}:
        hits = _augment_process_code_siblings(connection, hits, limit)
    hits.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return hits[:limit]


def _process_alias_terms(rewritten: RewrittenQuery) -> list[str]:
    if rewritten.query_type not in {"lifecycle_lookup", "definition", "timing_lookup", "test_method_lookup"}:
        return []
    values = [rewritten.normalized_query, rewritten.target_topic, *rewritten.must_terms, *rewritten.aliases]
    terms: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        for suffix in ("有哪些活动", "有哪些任务", "有哪些步骤", "过程域", "过程", "活动", "任务", "步骤", "定义"):
            if text.endswith(suffix) and len(text) > len(suffix) + 1:
                text = text[: -len(suffix)].strip()
        candidates = [text]
        if "测试" in text:
            candidates.append(text.replace("测试", "验证"))
        if "验证" in text:
            candidates.append(text.replace("验证", "测试"))
        if text.endswith("集成测试") or text.endswith("集成验证"):
            candidates.append(text.replace("集成测试", "集成").replace("集成验证", "集成"))
        for candidate in candidates:
            candidate = candidate.strip()
            if candidate and candidate not in terms:
                terms.append(candidate)
    return terms[:8]


def _direct_fact_score(
    rewritten: RewrittenQuery,
    fact_type: str,
    blob: str,
    term: str,
    confidence: float,
) -> float:
    score = max(0.85, confidence)
    if rewritten.query_type in {"lifecycle_lookup", "timing_lookup"}:
        if fact_type == "process_fact":
            score += 1.25
            if rewritten.query_type == "lifecycle_lookup" and not re.search(
                r"\b(?:SYS|SWE|SUP|MAN|HWE|VAL|REU|PIM)\.\d+\.BP\d+\b",
                blob,
                re.I,
            ):
                score -= 0.75
        elif fact_type == "table_requirement":
            score += 0.85
        elif fact_type == "section_heading":
            score += 0.65
    elif rewritten.query_type == "definition" and re.search(r"(过程域|过程|活动|任务|步骤)", str(rewritten.original_query or "")):
        if fact_type in {"table_requirement", "section_heading"}:
            score += 0.9
        elif fact_type == "process_fact":
            score += 0.65
    elif rewritten.query_type == "test_method_lookup":
        if fact_type == "process_fact":
            score += 1.15
            if _looks_like_test_method_blob(blob):
                score += 0.75
        elif fact_type == "section_heading":
            score += 0.25

    compact_blob = _normalize_document_blob(blob)
    compact_term = _normalize_document_blob(term)
    if compact_term and compact_term in compact_blob:
        score += 0.35
    for term in _test_method_variant_terms(rewritten):
        if _normalize_document_blob(term) in compact_blob:
            score += 0.25
    if re.search(r"\b(?:SYS|SWE|SUP|MAN|HWE|VAL|REU|PIM)\.\d+\b", blob, re.I):
        score += 0.25
    return round(score, 6)


def _looks_like_test_method_blob(blob: str) -> bool:
    compact = _normalize_document_blob(blob)
    return (
        ("试验" in compact or "测试" in compact or "测量" in compact or "检测" in compact)
        and any(token in compact for token in ("试验方法及步骤", "按照图", "接好试验电路", "调节", "测量", "观察"))
    )


def _test_method_variant_terms(rewritten: RewrittenQuery) -> list[str]:
    text = " ".join(
        str(item or "")
        for item in [rewritten.original_query, rewritten.normalized_query, rewritten.target_topic, *rewritten.must_terms, *rewritten.should_terms, *rewritten.aliases]
    )
    terms: list[str] = []
    if "输入过压" in text:
        terms.extend(["输入过压", "输入过、欠压", "交流输入过、欠压", "过压保护试验"])
    if re.search(r"\bOBC\b|车载充电机|on-?board charger", text, re.I):
        terms.extend(["车载充电机", "电动汽车用传导式车载充电机", "on-board charger"])
    return [term for index, term in enumerate(terms) if term and term not in terms[:index]][:8]


def _augment_process_code_siblings(connection, hits: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    codes: list[str] = []
    for hit in hits[: max(limit, 12)]:
        blob = str(hit.get("snippet") or "")
        for match in re.finditer(r"\b((?:SYS|SWE|SUP|MAN|HWE|VAL|REU|PIM)\.\d+)\.BP\d+\b", blob, re.I):
            code = match.group(1).upper()
            if code not in codes:
                codes.append(code)
    if not codes:
        return hits

    merged: dict[str, dict[str, object]] = {str(hit.get("result_id")): dict(hit) for hit in hits if hit.get("result_id")}
    for code in codes[:3]:
        rows = connection.execute(
            """
            SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                   object_value, confidence
            FROM facts
            WHERE fact_type = 'process_fact'
              AND object_value LIKE ?
            ORDER BY fact_id ASC
            LIMIT ?
            """,
            (f"%{code}.BP%", max(limit * 2, 12)),
        ).fetchall()
        for row in rows:
            fact_id = str(row["fact_id"])
            score = max(0.85, float(row["confidence"] or 0.0)) + 1.45
            if re.search(r"[\u4e00-\u9fff]", str(row["object_value"] or "")):
                score += 0.2
            score = round(score, 6)
            hit = {
                "result_type": "fact",
                "result_id": fact_id,
                "doc_id": row["source_doc_id"],
                "page_no": row["page_no"],
                "score": score,
                "snippet": f"process_sibling_fact {row['object_value']}",
                "channel": "facts",
            }
            existing = merged.get(fact_id)
            if existing is None or score > float(existing.get("score") or 0.0):
                merged[fact_id] = hit
    return list(merged.values())
