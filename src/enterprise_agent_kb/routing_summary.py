from __future__ import annotations

import json
import re
from pathlib import Path

from .config import AppPaths
from .db import connect


def direct_routing_hits(
    workspace_root: Path,
    query: str,
    expansion: dict[str, object] | None = None,
    limit: int = 12,
    connection=None,
) -> list[dict[str, object]]:
    own_connection = connection is None
    paths = AppPaths.from_root(workspace_root)
    if own_connection:
        connection = connect(paths.db_file)
    try:
        terms = _routing_terms(query, expansion or {})
        if not terms:
            return []
        hits = [
            *_table_fact_hits(connection, terms, limit=max(limit * 2, 20)),
            *_wiki_title_hits(connection, terms, limit=limit),
            *_document_summary_hits(connection, terms, limit=limit),
        ]
        deduped: dict[tuple[str, str], dict[str, object]] = {}
        for hit in hits:
            key = (str(hit.get("result_type")), str(hit.get("result_id")))
            existing = deduped.get(key)
            if existing is None or float(hit.get("score") or 0) > float(existing.get("score") or 0):
                deduped[key] = hit
        result = list(deduped.values())
        result.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return result[:limit]
    finally:
        if own_connection:
            connection.close()


def _routing_terms(query: str, expansion: dict[str, object]) -> list[str]:
    terms: list[str] = []
    signal_state_context = _signal_state_requested(query)

    def add(value: str) -> None:
        text = str(value or "").strip()
        if text and text not in terms:
            terms.append(text)

    add(query)
    for value in _explicit_query_terms(query):
        add(value)
    for key in ("preserved_anchors", "expanded_terms", "must_not_change"):
        for value in expansion.get(key) or []:
            add(str(value))
    for item in expansion.get("expanded_queries") or []:
        if isinstance(item, dict):
            add(str(item.get("query") or ""))

    if re.search(r"\bCP\b|控制导引", query, re.I):
        add("控制导引")
        if signal_state_context or re.search(r"检测点\s*1", query, re.I):
            add("检测点 1")
            add("检测点1")
    if _is_timing_query(query):
        add("控制时序")
        add("控制时序表")
        add("状态转换")
        add("表 A.7")
        add("交流充电控制时序表")
    if re.search(r"PWM", query, re.I):
        add("PWM")
        add("是否输出 PWM")
    voltage = re.search(r"([+-]?\d+(?:\.\d+)?)\s*V", query, re.I)
    if voltage:
        add(voltage.group(1))
        add(f"{voltage.group(1)}V")
        add(f"{voltage.group(1)} V")
    if re.search(r"PWM", query, re.I) and voltage and re.search(r"\bCP\b|控制导引", query, re.I):
        add("表 A.4")
        add("电压状态")
        add("充电过程状态")
    return terms[:32]


def _explicit_query_terms(query: str) -> list[str]:
    text = str(query or "")
    terms: list[str] = []
    for match in re.finditer(r"表\s*[A-Z]\s*[.．]\s*\d+|表\s*\d+", text, re.I):
        _append_query_term(terms, match.group(0))
    if "参数" not in text:
        return terms
    cleaned = re.sub(r"表\s*[A-Z]\s*[.．]\s*\d+|表\s*\d+", " ", text, flags=re.I)
    cleaned = re.sub(
        r"(有哪些定义|定义有哪些|参数有哪些|参数是什么|哪些参数|参数值|是什么意思|是什么|代表什么|表示什么|指什么|含义|如何理解|怎么理解|[？?])",
        " ",
        cleaned,
    )
    cleaned = cleaned.replace("的参数", " ").replace("参数", " ")
    for chunk in re.split(r"[\s,，;；:：/|]+", cleaned):
        chunk = chunk.strip()
        if not chunk or not re.search(r"[\u4e00-\u9fff]", chunk):
            continue
        for part in re.split(r"的|和|与", chunk):
            part = part.strip()
            if not part:
                continue
            _append_query_term(terms, part)
            if len(part) > 2:
                for size in range(2, min(6, len(part)) + 1):
                    _append_query_term(terms, part[-size:])
    return terms[:16]


def _append_query_term(terms: list[str], term: str) -> None:
    cleaned = str(term or "").strip()
    if not cleaned or cleaned in terms:
        return
    if _is_generic_query_term(cleaned):
        return
    terms.append(cleaned)


def _is_generic_query_term(term: str) -> bool:
    normalized = _normalize(term)
    return normalized in {"参数", "定义", "是什么", "什么意思", "控制导引", "控制导引电路", "电路", "表", "table"}


def _table_fact_hits(connection, terms: list[str], limit: int) -> list[dict[str, object]]:
    targeted_rows = []
    requested_voltage = _requested_voltage(terms)
    if _timing_requested(terms):
        targeted_rows.extend(
            connection.execute(
                """
                SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                       fact_type, object_value, confidence
                FROM facts
                WHERE fact_type IN ('table_requirement', 'process_fact', 'transition_fact')
                  AND (object_value LIKE '%表 A.7%' OR object_value LIKE '%控制时序%' OR object_value LIKE '%状态转换%')
                  AND object_value LIKE '%时序%'
                ORDER BY confidence DESC, fact_id ASC
                LIMIT 120
                """
            ).fetchall()
        )
    if requested_voltage:
        targeted_rows.extend(connection.execute(
            """
            SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                   fact_type, object_value, confidence
            FROM facts
            WHERE fact_type = 'table_requirement'
              AND object_value LIKE '%PWM%'
              AND object_value LIKE '%状态%'
              AND object_value LIKE '%电压%'
              AND object_value LIKE ?
            ORDER BY confidence DESC, fact_id ASC
            LIMIT 80
            """,
            (f"%{requested_voltage}%",),
        ).fetchall())
    rows = connection.execute(
        """
        SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
               fact_type, object_value, confidence
        FROM facts
        WHERE fact_type IN ('table_requirement', 'parameter_value', 'requirement', 'process_fact', 'transition_fact')
        ORDER BY confidence DESC, fact_id ASC
        LIMIT 600
        """
    ).fetchall()
    rows = [*targeted_rows, *rows]
    hits: list[dict[str, object]] = []
    for row in rows:
        payload = _safe_json(row["object_value"])
        blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
        if _is_preface_or_index_blob(blob):
            continue
        score = _summary_match_score(blob, terms)
        if score <= 0:
            continue
        explicit_table_mismatch = _explicit_table_mismatch(blob, terms)
        if row["fact_type"] == "table_requirement":
            score += 0.18
        table_score, table_priority = _explicit_table_adjustment(blob, terms)
        score += table_score
        if not explicit_table_mismatch and _looks_like_signal_state_table(blob, terms):
            score += 2.4
        if not explicit_table_mismatch and _looks_like_exact_voltage_pwm_state_row(blob, terms):
            score += 1.8
        if not explicit_table_mismatch and _looks_like_timing_table(blob, terms):
            score += 2.6
            if "表 A.7" in blob:
                score += 2.2
            elif "表 C.3" in blob and not _special_appendix_c_requested(terms):
                score -= 1.0
        if not explicit_table_mismatch and ("表 A.4" in blob or "检测点 1 的电压状态" in blob):
            score += 0.8
        if re.search(r"表 [GH]\.", blob):
            score -= 0.35
        routing_priority = _routing_priority(blob, terms) + table_priority
        hits.append(
            {
                "result_type": "fact",
                "result_id": row["fact_id"],
                "doc_id": row["source_doc_id"],
                "page_no": row["page_no"],
                "score": round(min(score, 3.0), 6),
                "snippet": f"routing_summary {blob[:1200]}",
                "channel": "routing_summary",
                "channels": ["routing_summary"],
                "routing_summary": _summary_text(payload),
                "routing_priority": routing_priority,
            }
        )
    hits.sort(key=lambda item: (float(item.get("score") or 0), float(item.get("routing_priority") or 0)), reverse=True)
    return hits[:limit]


def _wiki_title_hits(connection, terms: list[str], limit: int) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT page_id, json_extract(source_doc_ids_json, '$[0]') AS doc_id, title, slug
        FROM wiki_pages
        LIMIT 800
        """
    ).fetchall()
    hits: list[dict[str, object]] = []
    for row in rows:
        blob = f"{row['title']} {row['slug']}"
        score = _summary_match_score(blob, terms)
        if score <= 0:
            continue
        hits.append(
            {
                "result_type": "wiki",
                "result_id": row["page_id"],
                "doc_id": row["doc_id"],
                "page_no": None,
                "score": round(min(score * 0.75, 2.0), 6),
                "snippet": f"routing_summary {blob}",
                "channel": "routing_summary",
                "channels": ["routing_summary"],
                "routing_summary": str(row["title"] or ""),
            }
        )
    hits.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return hits[:limit]


def _document_summary_hits(connection, terms: list[str], limit: int) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT doc_id, source_filename, source_type, page_count, quality_status
        FROM documents
        ORDER BY ingest_time DESC
        """
    ).fetchall()
    hits: list[dict[str, object]] = []
    for row in rows:
        blob = json.dumps(dict(row), ensure_ascii=False)
        score = _summary_match_score(blob, terms)
        if score <= 0:
            continue
        hits.append(
            {
                "result_type": "document",
                "result_id": row["doc_id"],
                "doc_id": row["doc_id"],
                "page_no": 1,
                "score": round(min(score * 0.55, 1.5), 6),
                "snippet": f"routing_summary {row['source_filename']}",
                "channel": "routing_summary",
                "channels": ["routing_summary"],
                "routing_summary": str(row["source_filename"] or ""),
            }
        )
    hits.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return hits[:limit]


def _summary_match_score(blob: str, terms: list[str]) -> float:
    haystack = _normalize(blob)
    if not haystack:
        return 0.0
    score = 0.0
    for term in terms:
        needle = _normalize(term)
        if not needle:
            continue
        if needle in haystack:
            score += 0.28 if _is_hard_term(term) else 0.12
    return score


def _looks_like_signal_state_table(blob: str, terms: list[str]) -> bool:
    normalized = _normalize(blob)
    has_voltage = any(_normalize(term) in normalized for term in terms if re.fullmatch(r"[+-]?\d+(?:\.\d+)?\s*V?", term, re.I))
    return (
        has_voltage
        and "pwm" in normalized
        and "电压" in normalized
        and "状态" in normalized
        and ("检测点1" in normalized or "检测点 1" in blob)
    )


def _looks_like_exact_voltage_pwm_state_row(blob: str, terms: list[str]) -> bool:
    voltage = _requested_voltage(terms)
    if not voltage:
        return False
    payload = _safe_json(blob)
    if not isinstance(payload, dict):
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            return False
    for row in payload.get("rows") or []:
        if not isinstance(row, list) or len(row) < 5:
            continue
        values = [str(cell).strip() for cell in row]
        if voltage in values[:3] and values[3] in {"是", "是/否"} and "状态" in values[4]:
            return True
    return False


def _routing_priority(blob: str, terms: list[str]) -> float:
    if _explicit_table_mismatch(blob, terms):
        return -3.0
    priority = 0.0
    if _looks_like_timing_table(blob, terms):
        priority += 4.0
    if _looks_like_exact_voltage_pwm_state_row(blob, terms):
        priority += 4.0
    if "表 A.4" in blob or "检测点 1 的电压状态" in blob:
        priority += 3.0
    if "表 A.7" in blob:
        priority += 5.0
    elif "表 C.3" in blob and not _special_appendix_c_requested(terms):
        priority -= 1.0
    if re.search(r"表 [GH]\.", blob):
        priority -= 1.0
    return priority


def _explicit_table_adjustment(blob: str, terms: list[str]) -> tuple[float, float]:
    requested = _requested_table_numbers(terms)
    if not requested:
        return (0.0, 0.0)
    blob_tables = _table_numbers(blob)
    if not blob_tables:
        return (0.0, 0.0)
    if any(table in blob_tables for table in requested):
        return (1.35, 6.0)
    return (-1.2, -6.0)


def _explicit_table_mismatch(blob: str, terms: list[str]) -> bool:
    requested = _requested_table_numbers(terms)
    if not requested:
        return False
    blob_tables = _table_numbers(blob)
    return bool(blob_tables and not requested & blob_tables)


def _is_timing_query(query: str) -> bool:
    return bool(re.search(r"(时序|流程|状态转换|控制时序|握手|预充|启动|停止|停机)", str(query or "")))


def _signal_state_requested(query: str) -> bool:
    return bool(
        re.search(r"PWM|检测点\s*1|[+-]?\d+(?:\.\d+)?\s*V|电压状态|充电过程状态", str(query or ""), re.I)
    )


def _looks_like_timing_table(blob: str, terms: list[str]) -> bool:
    normalized = _normalize(blob)
    if not _timing_requested(terms):
        return False
    return (
        ("表a.7" in normalized or "控制时序" in normalized or "状态转换" in normalized)
        and ("时序" in normalized or "状态" in normalized)
    )


def _timing_requested(terms: list[str]) -> bool:
    return any(_normalize(term) in {"时序", "控制时序", "控制时序表", "状态转换", "表a.7", "交流充电控制时序表"} for term in terms)


def _special_appendix_c_requested(terms: list[str]) -> bool:
    blob = _normalize(" ".join(str(term or "") for term in terms))
    return any(token in blob for token in ("gb/t20234.4", "gbt20234.4", "检测点3", "附录c", "直流"))


def _is_preface_or_index_blob(blob: str) -> bool:
    normalized = _normalize(blob)
    return any(token in normalized for token in ("前言", "目次", "目录")) or '"scope_type":"preface"' in normalized


def _requested_voltage(terms: list[str]) -> str:
    for term in terms:
        match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*V?", str(term or ""), re.I)
        if match:
            return match.group(1)
    return ""


def _requested_table_numbers(terms: list[str]) -> set[str]:
    tables: set[str] = set()
    for term in terms:
        for match in re.finditer(r"表\s*([A-Z])\s*[.．]\s*(\d+)", str(term or ""), re.I):
            tables.add(f"{match.group(1).upper()}.{match.group(2)}")
    return tables


def _table_numbers(blob: str) -> set[str]:
    return {
        f"{match.group(1).upper()}.{match.group(2)}"
        for match in re.finditer(r"表\s*([A-Z])\s*[.．]\s*(\d+)", str(blob or ""), re.I)
    }


def _summary_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return str(payload or "")[:180]
    for key in ("table_title", "title", "topic", "subject", "parameter"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value[:180]
    return json.dumps(payload, ensure_ascii=False)[:180]


def _is_hard_term(value: str) -> bool:
    return bool(
        re.fullmatch(r"[A-Z]{1,6}\d*", str(value or ""), re.I)
        or re.fullmatch(r"[+-]?\d+(?:\.\d+)?\s*(?:V|A|Ω|kΩ|Hz|%)?", str(value or ""), re.I)
        or str(value).startswith("表 ")
        or "检测点" in str(value)
    )


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def _safe_json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
