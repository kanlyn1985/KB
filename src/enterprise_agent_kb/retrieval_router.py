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
        if rewritten.query_type == "lifecycle_lookup":
            merged = _diversify_bp_hits(merged, rewritten)
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
    seeds = _structured_search_seeds(rewritten)
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
    seeds = _structured_search_seeds(rewritten)
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


def _structured_search_seeds(rewritten: RewrittenQuery) -> list[str]:
    raw_seeds = [
        rewritten.normalized_query,
        *rewritten.must_terms,
        *rewritten.should_terms,
    ]
    seeds: list[str] = []
    for seed in raw_seeds:
        text = str(seed or "").strip()
        if not text:
            continue
        if rewritten.query_type == "constraint" and _is_constraint_generic_seed(text):
            continue
        if text not in seeds:
            seeds.append(text)
    return seeds[:8]


def _is_constraint_generic_seed(seed: str) -> bool:
    compact = _normalize_document_blob(seed)
    return compact in {"要求", "requirement", "requirements", "shall", "must", "should"}


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
    # Add short keyword fragments from long must_terms for better LIKE matching
    for term in list(rewritten.must_terms):
        # Extract overlapping 2-char Chinese fragments for fine-grained LIKE matching
        chars = re.findall(r"[一-鿿]", term)
        for i in range(len(chars) - 1):
            frag = chars[i] + chars[i + 1]
            if frag not in search_terms:
                search_terms.append(frag)
        # Also keep longer 3-4 char fragments
        for frag in re.findall(r"[一-鿿]{3,4}", term):
            if frag not in search_terms:
                search_terms.append(frag)
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
              AND (fact_status IS NULL OR fact_status != 'quarantined_orphan')
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
    if rewritten.query_type == "parameter_lookup":
        hit_index = {str(hit.get("result_id")): index for index, hit in enumerate(hits) if hit.get("result_id")}
        for hit in _direct_parameter_fact_hits(connection, rewritten, limit):
            result_id = str(hit.get("result_id") or "")
            if not result_id:
                continue
            existing_index = hit_index.get(result_id)
            if existing_index is None:
                seen.add(result_id)
                hit_index[result_id] = len(hits)
                hits.append(hit)
                continue
            if float(hit.get("score") or 0.0) > float(hits[existing_index].get("score") or 0.0):
                hits[existing_index] = hit
    if rewritten.query_type in {"lifecycle_lookup", "timing_lookup"}:
        hits = _augment_process_code_siblings(connection, hits, limit)
    hits.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    if rewritten.query_type == "lifecycle_lookup":
        hits = _diversify_bp_hits(hits, rewritten)
    return hits[:limit]


def _diversify_bp_hits(hits: list[dict[str, object]], rewritten: RewrittenQuery | None = None) -> list[dict[str, object]]:
    ordered_codes: list[str] = []
    best_by_code: dict[str, tuple[float, dict[str, object]]] = {}
    selected_ids: set[str] = set()
    for hit in hits:
        result_id = str(hit.get("result_id") or "")
        snippet = str(hit.get("snippet") or "")
        bp_code = _first_bp_code(snippet)
        if not result_id or not bp_code:
            continue
        if bp_code not in best_by_code:
            ordered_codes.append(bp_code)
        preference = float(hit.get("score") or 0.0) + _bp_candidate_preference(rewritten, snippet)
        current = best_by_code.get(bp_code)
        if current is None or preference > current[0]:
            best_by_code[bp_code] = (preference, hit)
    selected: list[dict[str, object]] = []
    for code in ordered_codes:
        hit = best_by_code[code][1]
        selected.append(hit)
        selected_ids.add(str(hit.get("result_id") or ""))
    selected.extend(hit for hit in hits if str(hit.get("result_id") or "") not in selected_ids)
    return selected


def _first_bp_code(text: str) -> str | None:
    match = re.search(r"\b((?:SYS|SWE|SUP|MAN|HWE|VAL|REU|PIM)\.\d+\.BP\d+)\b", text, re.I)
    return match.group(1).upper() if match else None


def _bp_candidate_preference(rewritten: RewrittenQuery | None, snippet: str) -> float:
    if rewritten is None:
        return 0.0
    query_text = " ".join(
        str(item or "")
        for item in [
            rewritten.original_query,
            rewritten.normalized_query,
            rewritten.target_topic,
            *rewritten.must_terms,
            *rewritten.should_terms,
        ]
    )
    preference = 0.0
    if re.search(r"[\u4e00-\u9fff]", query_text) and re.search(r"[\u4e00-\u9fff]", snippet):
        preference += 0.45
    query_norm = _normalize_document_blob(query_text)
    snippet_norm = _normalize_document_blob(snippet)
    for token in _process_focus_tokens(query_norm):
        if token in snippet_norm:
            preference += 0.35
    return preference


def _process_focus_tokens(query_norm: str) -> list[str]:
    tokens: list[str] = []
    for token in ("分析软件架构", "软件架构分析", "定义软件架构", "软件架构设计", "系统集成", "集成验证"):
        if token in query_norm:
            tokens.append(token)
    return tokens


def _direct_parameter_fact_hits(connection, rewritten: RewrittenQuery, limit: int) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
               object_value, confidence
        FROM facts
        WHERE fact_type = 'parameter_value'
          AND (fact_status IS NULL OR fact_status != 'quarantined_orphan')
        ORDER BY confidence DESC, fact_id ASC
        """
    ).fetchall()
    hits: list[dict[str, object]] = []
    requested_tables = _requested_table_numbers(rewritten)
    query_text = _parameter_query_text(rewritten)
    query_norm = _normalize_document_blob(query_text)
    query_upper = query_text.upper()
    for row in rows:
        payload = _safe_json_object(str(row["object_value"] or ""))
        if not payload:
            continue
        score = _structured_parameter_score(
            payload,
            query_norm=query_norm,
            query_upper=query_upper,
            requested_tables=requested_tables,
            confidence=float(row["confidence"] or 0),
        )
        if score <= 0:
            continue
        hits.append(
            {
                "result_type": "fact",
                "result_id": row["fact_id"],
                "doc_id": row["source_doc_id"],
                "page_no": row["page_no"],
                "score": round(score, 6),
                "snippet": f"knowledge_unit_fact {row['object_value']}",
            }
        )
    hits.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    parameter_hits = hits[: max(limit, 12)]

    # Also search requirement/threshold facts for parameter queries that may not
    # have a direct parameter_value (e.g., "效率要求" is a requirement, not a parameter row)
    search_frags = list(set(
        frag
        for term in rewritten.must_terms
        for frag in re.findall(r"[一-鿿]{2}", term)
    ))
    if search_frags and len(parameter_hits) < 3:
        seen_ids = {str(h.get("result_id")) for h in parameter_hits}
        for frag in search_frags[:4]:
            req_rows = connection.execute(
                """
                SELECT fact_id, fact_type, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                       object_value, confidence
                FROM facts
                WHERE fact_type IN ('requirement', 'threshold')
                  AND (fact_status IS NULL OR fact_status != 'quarantined_orphan')
                  AND object_value LIKE ?
                ORDER BY confidence DESC, fact_id ASC
                LIMIT ?
                """,
                (f"%{frag}%", limit),
            ).fetchall()
            for row in req_rows:
                if row["fact_id"] in seen_ids:
                    continue
                seen_ids.add(row["fact_id"])
                parameter_hits.append(
                    {
                        "result_type": "fact",
                        "result_id": row["fact_id"],
                        "doc_id": row["source_doc_id"],
                        "page_no": row["page_no"],
                        "score": round(float(row["confidence"] or 0) * 0.8, 6),
                        "snippet": f"knowledge_unit_fact {row['object_value']}",
                    }
                )
    return parameter_hits


def _structured_parameter_score(
    payload: dict[str, object],
    *,
    query_norm: str,
    query_upper: str,
    requested_tables: set[str],
    confidence: float,
) -> float:
    table_title = str(payload.get("table_title") or payload.get("source_caption") or "")
    payload_tables = _table_numbers(table_title)
    table_match = bool(requested_tables and payload_tables and requested_tables & payload_tables)
    table_mismatch = bool(requested_tables and payload_tables and not requested_tables & payload_tables)
    parameter_match = _query_contains_field(query_norm, _clean_parameter_field(payload.get("parameter")))
    symbol_match = _query_contains_symbol(query_upper, _clean_parameter_field(payload.get("symbol")))
    object_match = _query_contains_field(query_norm, _clean_parameter_field(payload.get("object")))
    row_focus_match = _query_contains_any_tag(query_norm, query_upper, payload.get("row_focus_tags") or payload.get("focus_tags") or [])
    table_focus_match = _query_contains_any_tag(query_norm, query_upper, payload.get("table_focus_tags") or [])
    resistance_intent = _query_has_resistance_intent(query_norm, query_upper)
    resistance_payload = _parameter_payload_matches_resistance(payload)
    has_row_anchor = parameter_match or symbol_match or row_focus_match
    has_context_anchor = table_match or object_match or table_focus_match
    if requested_tables and table_mismatch and not has_row_anchor:
        return 0.0
    if not requested_tables and not (has_row_anchor or object_match):
        return 0.0
    if resistance_intent and not resistance_payload:
        return 0.0

    score = max(0.85, confidence) + 0.55
    if table_match:
        score += 1.2
    if table_mismatch:
        score -= 1.0
    if parameter_match:
        score += 1.25
    if symbol_match:
        score += 1.1
    if row_focus_match:
        score += 0.55
    if object_match:
        score += 0.45
    if table_focus_match:
        score += 0.15
    if resistance_intent and resistance_payload:
        score += 0.75
    if has_context_anchor and not has_row_anchor:
        score -= 0.25
    return score if score >= 1.0 else 0.0


def _query_has_resistance_intent(query_norm: str, query_upper: str) -> bool:
    return bool(
        re.search(r"(电阻|阻值|等效电阻|欧姆|Ω|OHM|RESISTANCE)", query_norm, re.I)
        or re.search(r"(OHM|RESISTANCE)", query_upper, re.I)
    )


def _parameter_payload_matches_resistance(payload: dict[str, object]) -> bool:
    values = [
        payload.get("parameter"),
        payload.get("symbol"),
        payload.get("unit"),
        payload.get("source_caption"),
        payload.get("table_title"),
    ]
    text = " ".join(str(value or "") for value in values)
    return bool(re.search(r"(电阻|阻值|等效电阻|Ω|\\\\Omega|欧姆|resistance|^R\d|'?等效电阻)", text, re.I))


def _parameter_query_text(rewritten: RewrittenQuery) -> str:
    return " ".join(
        str(item or "")
        for item in [
            rewritten.original_query,
            rewritten.normalized_query,
            rewritten.target_topic,
            *rewritten.must_terms,
            *rewritten.protected_anchor_terms,
        ]
    )


def _requested_table_numbers(rewritten: RewrittenQuery) -> set[str]:
    return _table_numbers(
        " ".join(
            str(item or "")
            for item in [
                rewritten.original_query,
                rewritten.normalized_query,
                rewritten.target_topic,
                *rewritten.must_terms,
                *rewritten.should_terms,
                *rewritten.aliases,
            ]
        )
    )


def _table_numbers(value: str) -> set[str]:
    return {
        f"{match.group(1).upper()}.{match.group(2)}"
        for match in re.finditer(r"表\s*([A-Z])\s*[.．]\s*(\d+)", str(value or ""), re.I)
    }


def _safe_json_object(value: str) -> dict[str, object] | None:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _clean_parameter_field(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\^[A-Za-z0-9]+", "", text)
    text = re.sub(r"[（(][^)）]*[)）]", "", text)
    return text.strip(" *:：;；,，")


def _query_contains_field(query_norm: str, value: str) -> bool:
    if not value:
        return False
    normalized = _normalize_document_blob(value)
    if normalized in {"参数", "定义", "是什么", "什么意思", "控制导引", "控制导引电路", "电路", "表", "table"}:
        return False
    if re.fullmatch(r"[a-z0-9+\-/'_.]{1,2}", normalized, re.I):
        return False
    return normalized in query_norm


def _query_contains_symbol(query_upper: str, symbol: str) -> bool:
    if len(symbol) < 2:
        return False
    return bool(re.search(rf"(?<![A-Z0-9]){re.escape(symbol.upper())}(?![A-Z0-9])", query_upper))


def _query_contains_any_tag(query_norm: str, query_upper: str, tags: list[object]) -> bool:
    for tag in tags:
        text = _clean_parameter_field(tag)
        if not text:
            continue
        upper = text.upper()
        if upper in {"CP", "CC", "PE", "PWM"} and re.search(rf"(?<![A-Z0-9]){re.escape(upper)}(?![A-Z0-9])", query_upper):
            return True
        if re.fullmatch(r"CC\d", upper) and re.search(r"(?<![A-Z0-9])CC(?![A-Z0-9])", query_upper):
            return True
        normalized = _normalize_document_blob(text)
        if len(normalized) > 1 and normalized not in {"控制导引", "控制导引电路", "电路"} and normalized in query_norm:
            return True
    return False


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
            SELECT fact_id, fact_type, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                   object_value, confidence
            FROM facts
            WHERE fact_type IN ('process_fact', 'table_requirement')
              AND (fact_status IS NULL OR fact_status != 'quarantined_orphan')
              AND object_value LIKE ?
            ORDER BY fact_id ASC
            LIMIT ?
            """,
            (f"%{code}.BP%", max(limit * 2, 12)),
        ).fetchall()
        for row in rows:
            fact_id = str(row["fact_id"])
            fact_type = str(row["fact_type"] or "")
            score = max(0.85, float(row["confidence"] or 0.0)) + (1.45 if fact_type == "process_fact" else 1.36)
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
