from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

from .config import AppPaths
from .db import connect


GENERIC_TOPIC_TERMS = {
    "活动",
    "阶段",
    "任务",
    "流程",
    "过程",
    "工作",
    "步骤",
    "定义",
    "要求",
    "过程域",
    "有哪些",
    "要做",
    "做什么",
}


@dataclass(frozen=True)
class TopicResolutionResult:
    query_type: str
    target_topic: str
    candidate_entity_ids: list[str]
    candidate_entities: list[dict[str, object]]
    candidate_wiki_pages: list[dict[str, object]]
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_topic_entities(
    workspace_root: Path,
    rewritten,
    preferred_doc_id: str | None = None,
    limit: int = 8,
) -> TopicResolutionResult:
    """Resolve the rewritten query's topic terms to concrete entities.

    Pulls topic-term candidates from the rewrite result, looks up matching
    entity rows, and ranks them by confidence and (when available) the
    preferred document. Returns a ``TopicResolutionResult`` with the
    target topic string and the ranked entity list.
    """
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        topic_terms = _topic_terms(rewritten)
        if not topic_terms:
            return TopicResolutionResult(
                query_type=rewritten.query_type,
                target_topic=str(getattr(rewritten, "target_topic", "") or ""),
                candidate_entity_ids=[],
                candidate_entities=[],
                candidate_wiki_pages=[],
                confidence=0.0,
            )

        core_terms = _core_topic_terms(topic_terms)
        entity_types = _entity_types_for_query_type(rewritten)
        standard_anchor = _standard_anchor(rewritten)
        scoring_terms = _merge_terms(topic_terms, core_terms)
        scored_entities: dict[str, tuple[float, dict[str, object]]] = {}
        for entity_type in entity_types:
            rows = connection.execute(
                """
                SELECT entity_id, canonical_name, entity_type, alias_json, description, source_confidence
                FROM entities
                WHERE entity_type = ?
                  AND entity_status = 'ready'
                ORDER BY canonical_name
                """,
                (entity_type,),
            ).fetchall()
            for row in rows:
                item = dict(row)
                name = str(item.get("canonical_name") or "").strip()
                aliases = _entity_aliases(item)
                searchable_names = [name, *aliases]
                if standard_anchor and not _matches_standard_anchor(item, standard_anchor):
                    continue
                if core_terms and not any(_matches_core_topic(candidate, core_terms) for candidate in searchable_names):
                    continue
                score = max(
                    _entity_match_score(candidate, scoring_terms, rewritten.query_type, entity_type)
                    for candidate in searchable_names
                    if candidate
                )
                if aliases and score > _entity_match_score(name, scoring_terms, rewritten.query_type, entity_type):
                    score += 0.6
                if score <= 0:
                    continue
                entity_id = str(item["entity_id"])
                existing = scored_entities.get(entity_id)
                if existing is None or score > existing[0]:
                    scored_entities[entity_id] = (score, item)

        ranked_pairs = sorted(
            scored_entities.values(),
            key=lambda pair: (-pair[0], str(pair[1].get("canonical_name") or "")),
        )
        ranked_entities = [item for _, item in ranked_pairs][:limit]
        entity_ids = [str(item["entity_id"]) for item in ranked_entities]

        wiki_pages: list[dict[str, object]] = []
        if entity_ids:
            entity_rank = {entity_id: index for index, entity_id in enumerate(entity_ids)}
            placeholders = ",".join("?" for _ in entity_ids)
            rows = connection.execute(
                f"""
                SELECT page_id, page_type, title, slug, entity_id, trust_status, file_path, source_fact_ids_json,
                       json_extract(source_doc_ids_json, '$[0]') AS doc_id
                FROM wiki_pages
                WHERE entity_id IN ({placeholders})
                ORDER BY title
                """,
                entity_ids,
            ).fetchall()
            for row in rows:
                item = dict(row)
                if preferred_doc_id and item.get("doc_id") not in {preferred_doc_id, None, ""}:
                    continue
                item.pop("doc_id", None)
                wiki_pages.append(item)
            wiki_pages.sort(
                key=lambda item: (
                    entity_rank.get(str(item.get("entity_id") or ""), 10_000),
                    0 if _is_parameter_like_query(rewritten) and str(item.get("page_type") or "") == "parameter" else
                    0 if _is_parameter_like_query(rewritten) and str(item.get("page_type") or "") == "term" else
                    0 if rewritten.query_type == "parameter_lookup" and str(item.get("page_type") or "") == "parameter" else
                    0 if rewritten.query_type == "comparison" and str(item.get("page_type") or "") == "comparison" else
                    0 if rewritten.query_type == "constraint" and str(item.get("page_type") or "") == "constraint" else
                    1,
                    str(item.get("title") or ""),
                )
            )

        confidence = _resolution_confidence(ranked_pairs[0][0] if ranked_pairs else 0.0, ranked_entities)
        return TopicResolutionResult(
            query_type=rewritten.query_type,
            target_topic=str(getattr(rewritten, "target_topic", "") or ""),
            candidate_entity_ids=entity_ids,
            candidate_entities=ranked_entities,
            candidate_wiki_pages=wiki_pages[:limit],
            confidence=confidence,
        )
    finally:
        connection.close()


def _entity_types_for_query_type(rewritten) -> list[str]:
    query_type = str(getattr(rewritten, "query_type", "") or "")
    original = str(getattr(rewritten, "original_query", "") or "")
    if query_type in {"standard_lookup", "lifecycle_lookup"} and _standard_anchor(rewritten):
        return ["standard", "document"]
    mapping = {
        "definition": ["term", "parameter_topic"],
        "comparison": ["comparison_topic", *(["process"] if re.search(r"(活动|任务|步骤|流程|过程|要做|做什么)", original) else []), "term"],
        "constraint": ["constraint_topic", "process", "term"],
        "timing_lookup": ["process"],
        "lifecycle_lookup": ["process"],
        "parameter_lookup": ["parameter_topic", "term", "parameter_group"],
    }
    if _is_parameter_like_query(rewritten):
        return ["parameter_topic", "term", "parameter_group"]
    return mapping.get(query_type, ["term", "parameter_topic", "process", "parameter_group"])


def _topic_terms(rewritten) -> list[str]:
    values = [
        str(getattr(rewritten, "target_topic", "") or "").strip(),
        str(getattr(rewritten, "normalized_query", "") or "").strip(),
        *[str(item).strip() for item in getattr(rewritten, "must_terms", [])],
        *[str(item).strip() for item in getattr(rewritten, "aliases", [])],
        *[str(item).strip() for item in getattr(rewritten, "should_terms", [])],
        *[str(item).strip() for item in getattr(rewritten, "protected_anchor_terms", [])],
    ]
    terms: list[str] = []
    for value in values:
        if not value:
            continue
        cleaned = re.sub(r"(有什么要求|要求是什么|应满足什么|应符合什么)$", "", value).strip()
        cleaned = cleaned.replace("的要求", "").replace("功能要求", "").replace("功能", "").strip()
        if cleaned in GENERIC_TOPIC_TERMS:
            continue
        if cleaned and cleaned not in terms:
            terms.append(cleaned)
    return terms[:12]


def _core_topic_terms(topic_terms: list[str]) -> list[str]:
    core: list[str] = []
    for term in topic_terms:
        cleaned = _strip_generic_suffix(term)
        for variant in _topic_variants(cleaned):
            if variant and variant not in GENERIC_TOPIC_TERMS and variant not in core:
                core.append(variant)
    return sorted(core, key=len, reverse=True)[:4]


def _merge_terms(primary: list[str], secondary: list[str]) -> list[str]:
    terms: list[str] = []
    for term in [*primary, *secondary]:
        if term and term not in terms:
            terms.append(term)
    return terms


def _strip_generic_suffix(value: str) -> str:
    text = str(value or "").strip()
    for suffix in ("有哪些活动要做", "有哪些活动", "的活动", "活动", "任务", "阶段", "流程", "过程域", "过程", "工作", "步骤", "定义", "要求"):
        if text.endswith(suffix) and len(text) > len(suffix) + 1:
            text = text[: -len(suffix)].strip()
            break
    return text


def _topic_variants(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    variants = [text]
    replacements = [
        ("测试", "验证"),
        ("验证", "测试"),
        ("集成测试", "集成"),
        ("集成验证", "集成"),
    ]
    for source, target in replacements:
        if source in text:
            variants.append(text.replace(source, target))
    compact = text.replace("过程域", "").replace("过程", "").strip()
    if compact and compact != text:
        variants.extend(_topic_variants(compact))
    verb_tail = re.match(r"^(.+?)(分析|定义|选择|执行|集成|总结|沟通|确保|建立)$", text)
    if verb_tail:
        obj = verb_tail.group(1).strip()
        verb = verb_tail.group(2)
        if obj:
            variants.append(f"{verb}{obj}")
    deduped: list[str] = []
    for item in variants:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _entity_aliases(item: dict[str, object]) -> list[str]:
    value = item.get("alias_json")
    if not value:
        return []
    try:
        loaded = value if isinstance(value, list) else __import__("json").loads(str(value))
    except (TypeError, ValueError):
        return []
    if not isinstance(loaded, list):
        return []
    return [str(alias).strip() for alias in loaded if str(alias).strip()]


def _matches_core_topic(name: str, core_terms: list[str]) -> bool:
    compact_name = _compact_topic_text(name)
    for term in core_terms:
        compact_term = _compact_topic_text(term)
        if compact_term and compact_term in compact_name:
            return True
    return False


def _resolution_confidence(top_score: float, ranked_entities: list[dict[str, object]]) -> float:
    if not ranked_entities or top_score <= 0:
        return 0.0
    if top_score >= 9.0:
        return 0.95
    if top_score >= 6.0:
        return 0.82
    if top_score >= 3.0:
        return 0.55
    return 0.35


def _entity_match_score(name: str, topic_terms: list[str], query_type: str, entity_type: str) -> float:
    lexical_score = 0.0
    upper_name = name.upper()
    compact_name = _compact_topic_text(name)
    has_compound_anchor = any(_is_compound_anchor(term) for term in topic_terms)
    protected_acronyms = [str(term).upper() for term in topic_terms if re.fullmatch(r"[A-Z]{1,6}\d*", str(term).upper())]
    full_compound_match = any(_is_compound_anchor(term) and term.upper() in upper_name for term in topic_terms)
    has_short_acronym_query = any(_is_short_acronym(term) for term in topic_terms)
    for term in topic_terms:
        if not term:
            continue
        upper_term = term.upper()
        compact_term = _compact_topic_text(term)
        if name == term:
            lexical_score += 6.0
        elif compact_term and compact_name == compact_term:
            lexical_score += 6.0
            if _is_compound_anchor(term):
                lexical_score += 4.0
        elif term in name:
            lexical_score += 3.0
        elif compact_term and compact_term in compact_name:
            lexical_score += 2.5
        elif upper_term == upper_name:
            lexical_score += 6.0
        elif upper_term in upper_name:
            lexical_score += 3.0
        elif re.fullmatch(r"[A-Z]{1,4}\d*", upper_term) and upper_term == upper_name:
            lexical_score += 8.0
        if _is_compound_anchor(term) and upper_term in upper_name:
            lexical_score += 5.0
        if _is_short_acronym(term) and _term_has_suffix_acronym(name, upper_term):
            lexical_score += 9.0

    if lexical_score <= 0:
        return 0.0

    score = lexical_score

    if query_type == "parameter_lookup" and entity_type == "parameter_topic":
        score += 4.5
    elif query_type in {"standard_lookup", "lifecycle_lookup"} and entity_type == "standard":
        score += 5.0
    elif query_type in {"standard_lookup", "lifecycle_lookup"} and entity_type == "document":
        score += 4.0
    elif query_type == "parameter_lookup" and entity_type == "parameter_group":
        score -= 2.0
    elif query_type == "constraint" and entity_type == "constraint_topic":
        score += 3.0
    elif query_type == "comparison" and entity_type == "comparison_topic":
        score += 3.0
    elif query_type in {"timing_lookup", "lifecycle_lookup"} and entity_type == "process":
        score += 2.0
    elif query_type == "definition" and entity_type == "term":
        score += 1.2
    elif query_type == "definition" and entity_type == "parameter_topic":
        score += 1.0
    if query_type == "definition" and entity_type == "parameter_topic" and has_compound_anchor:
        score += 4.0
    elif query_type == "definition" and entity_type == "parameter_group" and has_compound_anchor:
        score -= 5.0
    if entity_type == "parameter_topic" and has_compound_anchor:
        score += 3.0
    if entity_type == "parameter_group" and has_compound_anchor and not full_compound_match:
        score -= 8.0
    if entity_type == "parameter_group" and has_compound_anchor and len(name) >= 30:
        score -= 3.0
    if has_short_acronym_query:
        if entity_type in {"process", "parameter_group", "constraint_topic"} and len(name) >= 80:
            score -= 12.0
        if entity_type == "parameter_topic" and upper_name in protected_acronyms:
            score += 7.0
        if entity_type == "term" and any(_term_has_suffix_acronym(name, acronym) for acronym in protected_acronyms):
            score += 7.0
    if entity_type == "term" and has_compound_anchor:
        score -= 1.5 if len(name) >= 18 else 0.0
    if entity_type == "term" and any(acronym in upper_name for acronym in protected_acronyms):
        score += 2.5
    return score


def _is_parameter_like_query(rewritten) -> bool:
    query_type = str(getattr(rewritten, "query_type", "") or "")
    query = str(getattr(rewritten, "original_query", "") or "")
    if query_type == "parameter_lookup":
        return True
    values = [
        str(getattr(rewritten, "target_topic", "") or ""),
        str(getattr(rewritten, "normalized_query", "") or ""),
        *[str(item) for item in getattr(rewritten, "must_terms", [])],
        *[str(item) for item in getattr(rewritten, "protected_anchor_terms", [])],
    ]
    if any(re.search(r"(阻值|电阻|电压|电流|频率|占空比|检测点|PWM|脉宽)", value, re.I) for value in values if value):
        return True
    return bool(
        re.search(r"\b(?:CP|CC)\b|PWM", query, re.I)
        and re.search(r"(?:[+-]?\d+(?:\.\d+)?)\s*V|电压|占空比|频率|检测点", query, re.I)
    )


def _is_compound_anchor(term: str) -> bool:
    return bool(re.search(r"(阻值|电阻|电压|电流|频率|占空比|检测点|PWM|脉宽|[+-]?\d+(?:\.\d+)?\s*V)", str(term or ""), re.I))


def _is_short_acronym(term: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{1,6}\d*", str(term or "").upper()))


def _term_has_suffix_acronym(name: str, acronym: str) -> bool:
    if not acronym:
        return False
    upper_name = str(name or "").upper()
    escaped = re.escape(acronym.upper())
    return bool(re.search(rf"(?:;|；|\(|（|\s){escaped}(?:\)|）|\s|$)", upper_name))


def _compact_topic_text(value: str) -> str:
    return re.sub(r"[\s\-_+/·:：;；,，.。()（）]+", "", str(value or "")).upper()


def _standard_anchor(rewritten) -> str | None:
    values = [
        str(getattr(rewritten, "original_query", "") or ""),
        str(getattr(rewritten, "target_topic", "") or ""),
        str(getattr(rewritten, "normalized_query", "") or ""),
        *[str(item) for item in getattr(rewritten, "must_terms", [])],
        *[str(item) for item in getattr(rewritten, "protected_anchor_terms", [])],
    ]
    for value in values:
        match = re.search(r"(?:GB/T|GBT|GB|ISO|IEC)\s*[\d.]+(?:[-—]\d{2,4})?", value, re.I)
        if match:
            return _normalize_standard_anchor(match.group(0))
    return None


def _matches_standard_anchor(item: dict[str, object], anchor: str) -> bool:
    aliases = _entity_aliases(item)
    values = [
        str(item.get("canonical_name") or ""),
        str(item.get("description") or ""),
        *aliases,
    ]
    return any(anchor and anchor in _normalize_standard_anchor(value) for value in values)


def _normalize_standard_anchor(value: str) -> str:
    text = str(value or "").upper()
    text = text.replace("GB T", "GB/T").replace("GBT", "GB/T")
    text = text.replace("QC T", "QC/T")
    return re.sub(r"[^A-Z0-9]+", "", text)
