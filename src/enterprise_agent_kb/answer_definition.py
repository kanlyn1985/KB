from __future__ import annotations

import json
import re
from pathlib import Path

from .config import AppPaths
from .db import connect
from .answer_utils import _safe_json
from .answer_subgraph import _prioritize_subgraph_facts
from .answer_query_parsing import _normalize_query_phrase


def _definition_term_has_anchor(target_topic: str, term: str) -> bool:
    target = str(target_topic or "").strip()
    term_text = str(term or "")
    if re.fullmatch(r"[A-Z][A-Z0-9/-]{1,10}", target):
        return bool(re.search(rf"(?<![A-Z0-9]){re.escape(target)}(?![A-Z0-9])", term_text))
    acronyms = [
        match.group(1).upper()
        for match in re.finditer(r"(?<![A-Za-z0-9])([A-Z]{2,6})(?![A-Za-z0-9])", target, re.I)
    ]
    context_terms = [
        match.group(0)
        for match in re.finditer(r"[一-鿿]{2,}", target)
        if match.group(0) not in {"什么", "意思", "定义", "含义"}
    ]
    if not acronyms or not context_terms:
        return False
    term_upper = term_text.upper()
    acronym_match = any(re.search(rf"(?<![A-Z0-9]){re.escape(acronym)}(?![A-Z0-9])", term_upper) for acronym in acronyms)
    context_match = any(context in term_text for context in context_terms)
    return acronym_match and context_match


def _definition_compare_key(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^[#>\-\s]+", "", text)
    return re.sub(r"\s+", " ", text.strip()).lower()


"""Definition intent answer generation, including wiki fallbacks, section-intro fallbacks, and fact selection."""


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
    # Require a meaningful match — single partial token overlap is not enough
    if candidates[0][0] < 4.0:
        return None
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
    target = _definition_compare_key(_normalize_query_phrase(target_topic))
    current = _definition_compare_key(_normalize_query_phrase(term))
    if not target or not current:
        return False
    if current == target:
        return True
    if current.startswith(target):
        return True
    if _definition_term_has_anchor(target_topic, term):
        return True
    stripped = re.sub(r"^[A-Z]?\d+(?:\.\d+){0,8}", "", term).strip()
    stripped = _definition_compare_key(_normalize_query_phrase(stripped))
    return stripped == target or stripped.startswith(target)


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


def _select_definition_answer_facts(
    facts: list[dict[str, object]],
    knowledge_subgraph: dict[str, object] | None,
    query: str,
    rewritten_payload: dict[str, object],
) -> list[dict[str, object]]:
    ranked = _prioritize_subgraph_facts(facts, knowledge_subgraph)
    target_terms = _definition_target_terms(query, rewritten_payload)
    normalized_targets = [
        _definition_compare_key(_normalize_query_phrase(target))
        for target in target_terms
        if _definition_compare_key(_normalize_query_phrase(target))
    ]

    def is_exact_definition(item: dict[str, object]) -> bool:
        if str(item.get("fact_type") or "") not in {"term_definition", "concept_definition"}:
            return False
        payload = item.get("object_value")
        payload_dict = payload if isinstance(payload, dict) else {}
        term = str(payload_dict.get("term") or payload_dict.get("title") or "").strip()
        normalized_term = _definition_compare_key(_normalize_query_phrase(term))
        return bool(normalized_term and normalized_term in normalized_targets)

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

        normalized_term = _definition_compare_key(_normalize_query_phrase(term))
        for target in target_terms:
            normalized_target = _definition_compare_key(_normalize_query_phrase(target))
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

    ordered = sorted(ranked, key=definition_score, reverse=True)
    exact_definitions = [item for item in ordered if is_exact_definition(item)]
    if exact_definitions:
        exact_ids = {str(item.get("fact_id") or "") for item in exact_definitions}
        return exact_definitions + [item for item in ordered if str(item.get("fact_id") or "") not in exact_ids]
    return ordered


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
