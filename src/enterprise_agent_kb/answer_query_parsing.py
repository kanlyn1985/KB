from __future__ import annotations

"""Query text analysis, normalization, and term extraction for answer generation."""

import json
import re

from .query_rewrite import RewrittenQuery


def _normalize_query_phrase(query: str) -> str:
    text = query
    matched_pattern = False
    for pattern in (
        r"^\s*(.+?)\s*是怎么定义的\s*$",
        r"^\s*(.+?)\s*怎么定义\s*$",
        r"^\s*(.+?)\s*如何定义\s*$",
        r"^\s*(.+?)\s*是什么\s*$",
        r"^\s*(.+?)\s*要求是什么\s*$",
        r"^\s*(.+?)\s*有什么要求\s*$",
        r"^\s*(.+?)\s*有哪些字段\s*$",
        r"^\s*(.+?)\s*包括哪些字段\s*$",
        r"^\s*什么是\s*(.+?)\s*$",
        r"^\s*(.+?)\s*如何理解\s*$",
        r"^\s*(.+?)\s*怎么理解\s*$",
    ):
        match = re.match(pattern, text)
        if match:
            captured = next(group for group in match.groups() if group)
            text = captured
            matched_pattern = True
            break
    if not matched_pattern:
        text = re.sub(r"(什么是|是什么|是怎么定义的|怎么定义|如何定义|如何理解|定义|要求是什么|有什么要求|有哪些字段|包括哪些字段)", " ", text)
    text = text.replace("？", " ").replace("?", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_constraint_keywords(query: str) -> list[str]:
    """Extract substantive keywords from a constraint-type query, stripping generic wrappers.

    Returns both the full normalized query and individual short keywords for matching.
    """
    text = _normalize_query_phrase(query)
    # Remove common query wrappers that don't carry semantic meaning
    text = re.sub(r"(有哪些|包括哪些|有什么|是什么样的|是怎么|分别为|分别是|都有哪些)", "", text)
    # The full normalized text is the primary keyword (used for LIKE/contains matching)
    full = text.strip()
    # Also extract short meaningful chunks for finer matching
    generic = {"逆变器", "功能", "要求", "规定", "标准", "什么", "怎么", "如何", "是否", "的", "了", "和", "与", "及", "或", "在", "是", "有", "不", "为", "对", "按", "根据", "应"}
    tokens = re.findall(r"[一-鿿]{2}|[一-鿿]{3}|[一-鿿]{4}|[a-zA-Z0-9]+", text)
    short = [t for t in tokens if t not in generic and len(t) >= 2]
    result = [full] if full else []
    result.extend(short)
    return list(dict.fromkeys(result))  # deduplicate preserving order


def _normalize_standard_code(value: str) -> str:
    text = value.upper().replace("GBT", "GB/T").replace("GB T", "GB/T").replace("QC T", "QC/T")
    text = text.replace("-", "—")
    text = re.sub(r"\s+", "", text)
    return text


def _extract_standard_from_query(query: str) -> str:
    match = re.search(r"(?:GB/T|GBT|GB|ISO/IEC|ISO|IEC|QC/T|QC)\s*[\d.]+(?:[.\-—:]\d+)*", query, re.I)
    return match.group(0) if match else query


def _extract_exact_terms(query: str) -> list[str]:
    terms = re.findall(r"[A-Z][A-Z0-9/-]{1,}", query)
    normalized: list[str] = []
    for term in terms:
        if term not in normalized and term not in {"GB", "GBT", "ISO", "IEC", "QC"}:
            normalized.append(term)
    return normalized


def _context_matches_exact_terms(
    context: dict[str, object],
    exact_terms: list[str],
    rewritten_payload: dict[str, object] | None = None,
) -> bool:
    if not exact_terms:
        return True
    corpus_parts: list[str] = []
    for collection_name in ("hits", "evidence", "facts", "wiki_pages", "documents"):
        for item in context.get(collection_name, []):
            corpus_parts.append(json.dumps(item, ensure_ascii=False))
    corpus = "\n".join(corpus_parts).upper()
    if any(term.upper() in corpus for term in exact_terms):
        return True
    return any(
        _context_matches_protected_anchor_alias(corpus, term, rewritten_payload or {})
        for term in exact_terms
    )


def _context_matches_protected_anchor_alias(
    corpus_upper: str,
    exact_term: str,
    rewritten_payload: dict[str, object],
) -> bool:
    term = str(exact_term or "").strip().upper()
    if not term:
        return False
    known_aliases = {
        "OBC": ["车载充电机", "电动汽车用传导式车载充电机", "ON-BOARD CHARGER", "ONBOARD CHARGER"],
    }
    if any(alias.upper() in corpus_upper for alias in known_aliases.get(term, [])):
        return True
    protected = {str(item or "").strip().upper() for item in rewritten_payload.get("protected_anchor_terms") or []}
    if term not in protected:
        return False
    alias_fields = (
        rewritten_payload.get("aliases") or [],
        rewritten_payload.get("must_terms") or [],
        rewritten_payload.get("should_terms") or [],
    )
    candidates: list[str] = []
    target_topic = str(rewritten_payload.get("target_topic") or "").strip()
    if target_topic:
        candidates.append(target_topic)
    for values in alias_fields:
        if isinstance(values, list):
            candidates.extend(str(value or "").strip() for value in values)
    for candidate in candidates:
        if not candidate:
            continue
        normalized = candidate.upper()
        if normalized == term or len(normalized) <= len(term):
            continue
        if normalized in corpus_upper:
            return True
    return False


def _context_has_exact_definition_signal(context: dict[str, object], exact_terms: list[str]) -> bool:
    if not exact_terms:
        return True
    corpus_parts: list[str] = []
    for collection_name in ("hits", "evidence", "facts", "wiki_pages"):
        for item in context.get(collection_name, []):
            corpus_parts.append(json.dumps(item, ensure_ascii=False))
    corpus = "\n".join(corpus_parts).upper()
    for term in exact_terms:
        target = term.upper()
        if target in corpus and any(token in corpus for token in ("TYPE", "V2X", "V2G", "V2V", "VEHICLE TO", "车辆", "电网", "负荷")):
            return True
    return False


def _intent_from_query_type(query_type: str) -> str:
    if query_type in {"definition"}:
        return "definition"
    if query_type in {"standard_lookup"}:
        return "standard"
    if query_type in {"lifecycle_lookup", "timing_lookup", "test_method_lookup"}:
        return "process"
    if query_type in {"parameter_lookup"}:
        return "parameter"
    if query_type in {"constraint"}:
        return "constraint"
    if query_type in {"comparison"}:
        return "comparison"
    return "general"


def _detect_intent(query: str) -> str:
    if re.search(r"\b(?:GB|GBT|GB/T|ISO|IEC|QC|QC/T)\b", query, re.I):
        return "standard"
    if re.search(r"(什么是|是什么|定义|怎么定义|如何定义|是怎么定义的|如何理解|怎么理解)", query):
        return "definition"
    return "general"


def _extract_table_no_from_query(query: str) -> str | None:
    match = re.search(r"表\s*(\d+)", query)
    return match.group(1) if match else None


def _is_timing_query(query: str) -> bool:
    return bool(re.search(r"(时序|流程|状态转换|控制时序|握手|预充|启动|停止|停机)", str(query or "")))


def _is_activity_process_query(query: str) -> bool:
    return bool(re.search(r"(活动|任务|步骤|实践|要做|做什么|工作内容|过程域|基本实践)", str(query or "")))


def _special_appendix_c_requested(query: str) -> bool:
    text = str(query or "")
    return bool(re.search(r"(GB/T\s*20234\.4|GBT\s*20234\.4|检测点\s*3|附录\s*C|直流)", text, re.I))


def _rewritten_from_context(query: str, context: dict[str, object]) -> RewrittenQuery | None:
    payload = context.get("rewrite")
    if not isinstance(payload, dict):
        return None
    try:
        return RewrittenQuery(
            original_query=str(payload.get("original_query") or query).strip(),
            normalized_query=str(payload.get("normalized_query") or query).strip(),
            query_type=str(payload.get("query_type") or "general_search").strip(),
            target_topic=str(payload.get("target_topic") or "").strip(),
            aliases=_string_list(payload.get("aliases")),
            must_terms=_string_list(payload.get("must_terms")),
            should_terms=_string_list(payload.get("should_terms")),
            negative_terms=_string_list(payload.get("negative_terms")),
            protected_anchor_terms=_string_list(payload.get("protected_anchor_terms")),
            rewrite_override_applied=bool(payload.get("rewrite_override_applied")),
            semantic_quality_flags=_string_list(payload.get("semantic_quality_flags")),
        )
    except (TypeError, ValueError, AttributeError):
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result