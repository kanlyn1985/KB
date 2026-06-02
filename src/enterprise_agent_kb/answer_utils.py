from __future__ import annotations

"""Utility helpers for answer generation — data formatting, truncation, rendering cleanup."""

import html
import json
import re


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


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


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def _clean_render_artifacts(text: str) -> str:
    if not text:
        return text
    text = html.unescape(str(text))
    text = text.replace("\xa0", " ")
    text = re.sub(r"\*\*([^*]{1,200})\*\*", r"\1", text)
    text = re.sub(r"\$([^$]{1,200})\$", r"\1", text)
    text = re.sub(r"\\%", "%", text)
    text = re.sub(r"\\sim", "~", text)
    text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"&nbsp;|&#160;|&ensp;|&emsp;", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:p|div|span|table|tr|td|th)\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"；；|;;", "；", text)
    text = re.sub(r"。。", "。", text)
    text = re.sub(r"([一-鿿])\s*\n\s*([一-鿿])", r"\1\2", text)
    return text


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


_INTENT_FACT_TYPES: dict[str, set[str]] = {
    "definition": {"term_definition", "concept_definition", "document_abstract"},
    "parameter": {"parameter_value", "table_requirement", "threshold", "requirement", "process_fact", "transition_fact"},
    "constraint": {"requirement", "threshold", "parameter_value", "table_requirement"},
    "process": {"process_fact", "transition_fact", "table_requirement"},
    "standard": {"document_standard", "document_lifecycle", "document_versioning"},
    "comparison": {"comparison_relation", "term_definition", "concept_definition"},
}
