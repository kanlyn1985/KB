"""Parameter intent answer generation, fact selection, and supplementation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import AppPaths
from .db import connect
from .answer_subgraph import _prioritize_subgraph_facts
from .answer_query_parsing import _normalize_query_phrase


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


def _supplement_parameter_facts(
    query: str,
    fact_items: list[dict[str, object]],
    workspace_root: Path,
) -> None:
    """Supplement parameter answer facts with requirement/threshold facts when missing.

    When a parameter query returns only parameter_value facts but the topic also has
    requirement/threshold facts (e.g., "效率" has requirement "不小于85%" but no
    parameter_value entry), this function queries the DB for matching facts and
    appends them in-place to fact_items.
    """
    if not fact_items:
        return

    has_requirement = any(
        item.get("fact_type") in {"requirement", "threshold"}
        for item in fact_items
    )
    if has_requirement:
        return

    query_text = _normalize_query_phrase(query)
    if not query_text:
        return

    cjk_frags: list[str] = []
    chars = re.findall(r"[一-鿿]", query_text)
    for i in range(len(chars) - 1):
        frag = chars[i] + chars[i + 1]
        if frag not in cjk_frags:
            cjk_frags.append(frag)
    search_terms = [query_text] + cjk_frags[:4]

    existing_ids = {item.get("fact_id") for item in fact_items if item.get("fact_id")}
    existing_blobs = " ".join(
        str(item.get("object") or "") for item in fact_items
    )

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        for term in search_terms[:3]:
            rows = connection.execute(
                """
                SELECT fact_id, fact_type, predicate, object_value, confidence,
                       source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
                FROM facts
                WHERE fact_type IN ('requirement', 'threshold')
                  AND object_value LIKE ?
                ORDER BY confidence DESC, fact_id ASC
                LIMIT 6
                """,
                (f"%{term}%",),
            ).fetchall()
            for row in rows:
                if row["fact_id"] in existing_ids:
                    continue
                blob = str(row["object_value"] or "")
                if any(frag in blob for frag in cjk_frags[:2] if frag) or term in blob:
                    if any(frag in existing_blobs for frag in cjk_frags[:2] if frag):
                        fact_item = {
                            "fact_id": row["fact_id"],
                            "fact_type": row["fact_type"],
                            "predicate": row["predicate"],
                            "object": row["object_value"],
                            "confidence": row["confidence"],
                            "doc_id": row["source_doc_id"],
                            "page_no": None,
                        }
                        qualifiers = row["qualifiers_json"]
                        if isinstance(qualifiers, dict):
                            fact_item["page_no"] = qualifiers.get("page_no")
                        fact_items.append(fact_item)
                        existing_ids.add(row["fact_id"])
    finally:
        connection.close()


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
