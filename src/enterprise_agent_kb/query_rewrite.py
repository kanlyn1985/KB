from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .query_semantic_parser import SemanticQuery, parse_semantic_query
from .synonyms import expand_with_synonyms


@dataclass(frozen=True)
class RewrittenQuery:
    original_query: str
    normalized_query: str
    query_type: str
    target_topic: str
    aliases: list[str]
    must_terms: list[str]
    should_terms: list[str]
    negative_terms: list[str]
    protected_anchor_terms: list[str]
    rewrite_override_applied: bool
    semantic_quality_flags: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def rewrite_query(query: str) -> RewrittenQuery:
    original = query.strip()
    rule_normalized = _normalize_query(original)
    rule_query_type = _detect_query_type(original, rule_normalized)
    semantic = _semantic_for_rewrite(original, rule_query_type)
    semantic_normalized = semantic.normalized_query.strip() if semantic.used_llm else ""
    seed_normalized = semantic_normalized if semantic_normalized and not _should_ignore_semantic_anchor(semantic) else rule_normalized
    normalized = seed_normalized or rule_normalized or original

    rule_query_type = _detect_query_type(original, normalized)
    query_type, rewrite_override_applied = _select_final_query_type(semantic, rule_query_type)
    protected_anchor_terms = _extract_protected_anchor_terms(original, query_type)

    normalized = _rebuild_normalized_query(
        original_query=original,
        query_type=query_type,
        semantic=semantic,
        rule_normalized=rule_normalized,
        protected_anchor_terms=protected_anchor_terms,
    )
    target_topic = _rebuild_target_topic(
        original_query=original,
        query_type=query_type,
        semantic=semantic,
        normalized_query=normalized,
        protected_anchor_terms=protected_anchor_terms,
    )

    must_terms = _must_terms(original, normalized, query_type)
    for term in protected_anchor_terms:
        if term not in must_terms:
            must_terms.append(term)
    for term in semantic.must_terms:
        cleaned = str(term or "").strip()
        if cleaned and cleaned not in must_terms and cleaned.lower() not in {"undefined", "unknown", "未知主题", "未知实体"}:
            must_terms.append(cleaned)
    if target_topic and target_topic not in must_terms and len(target_topic) <= 32:
        must_terms.append(target_topic)
    negative_terms = _negative_terms(original)
    aliases = _aliases(original, normalized, must_terms)
    for alias in semantic.aliases:
        if (
            alias
            and alias not in aliases
            and alias != original
            and alias != normalized
            and not _is_disallowed_semantic_term(original, target_topic, alias)
        ):
            aliases.append(alias)
    should_terms = _should_terms(normalized, aliases, must_terms, negative_terms)
    for term in semantic.should_terms:
        cleaned = str(term).strip()
        if (
            cleaned
            and cleaned not in should_terms
            and cleaned not in negative_terms
            and not _is_disallowed_semantic_term(original, target_topic, cleaned)
        ):
            should_terms.append(cleaned)

    return RewrittenQuery(
        original_query=original,
        normalized_query=normalized,
        query_type=query_type,
        target_topic=target_topic,
        aliases=aliases,
        must_terms=must_terms,
        should_terms=should_terms,
        negative_terms=negative_terms,
        protected_anchor_terms=protected_anchor_terms,
        rewrite_override_applied=rewrite_override_applied,
        semantic_quality_flags=list(getattr(semantic, "quality_flags", [])),
    )


def _semantic_for_rewrite(query: str, rule_query_type: str) -> SemanticQuery:
    if _should_skip_semantic_parser(query, rule_query_type):
        return SemanticQuery(
            query_type=rule_query_type,
            normalized_query=_normalize_query(query),
            target_topic=_normalize_query(query),
            answer_shape=_answer_shape_for_rule_type(rule_query_type),
            aliases=[],
            must_terms=[],
            should_terms=[],
            confidence=0.0,
            used_llm=False,
            quality_flags=["rule_first_semantic_skip"],
            raw_response=None,
        )
    return parse_semantic_query(query)


def _should_skip_semantic_parser(query: str, rule_query_type: str) -> bool:
    if rule_query_type in {"standard_lookup", "lifecycle_lookup", "timing_lookup", "test_method_lookup"}:
        return True
    if rule_query_type == "parameter_lookup":
        return bool(re.search(r"(阻值|电阻|电压|电流|频率|检测点|占空比|PWM|[+-]?\d+(?:\.\d+)?\s*(?:V|A|Ω|kΩ|Hz|%))", query, re.I))
    return False


def _answer_shape_for_rule_type(query_type: str) -> str:
    if query_type == "timing_lookup":
        return "process"
    if query_type == "test_method_lookup":
        return "process"
    if query_type == "parameter_lookup":
        return "value"
    if query_type in {"standard_lookup", "lifecycle_lookup"}:
        return "list"
    return "freeform"


def _should_ignore_semantic_anchor(semantic) -> bool:
    target = str(getattr(semantic, "target_topic", "") or "").strip()
    normalized = str(getattr(semantic, "normalized_query", "") or "").strip()
    quality_flags = set(getattr(semantic, "quality_flags", []))
    if not target or target.lower() in {"undefined", "unknown", "未知主题", "未知实体"}:
        return True
    if {"placeholder_target_topic", "high_confidence_low_quality"} & quality_flags:
        return True
    return not normalized


def _is_disallowed_semantic_term(original_query: str, target_topic: str, term: str) -> bool:
    target = str(target_topic or "").strip().upper()
    if target == "CC" and _looks_like_short_acronym_definition_query(original_query):
        normalized = re.sub(r"\s+", "", str(term or "")).upper()
        return any(token in normalized for token in ("CONSTANTCURRENT", "恒流", "电流限制", "POWERMANAGEMENT", "BMS"))
    return False


def _looks_like_short_acronym_definition_query(query: str) -> bool:
    return bool(
        re.search(r"(?<![A-Za-z0-9])([A-Z]{2,6})(?![A-Za-z0-9]).*(是什么意思|是什么|定义|含义)", query, re.I)
        or re.search(r"(是什么意思|是什么|定义|含义).*(?<![A-Za-z0-9])([A-Z]{2,6})(?![A-Za-z0-9])", query, re.I)
    )


def _select_final_query_type(semantic, rule_query_type: str) -> tuple[str, bool]:
    semantic_query_type = str(getattr(semantic, "query_type", "") or "").strip()
    semantic_confidence = float(getattr(semantic, "confidence", 0.0) or 0.0)
    quality_flags = set(getattr(semantic, "quality_flags", []))
    rewrite_override_applied = False
    if rule_query_type in {"standard_lookup", "lifecycle_lookup", "timing_lookup"}:
        return rule_query_type, semantic_query_type not in {"", rule_query_type}
    if rule_query_type == "parameter_lookup" and semantic_query_type in {"definition", "comparison", "general_search"}:
        return rule_query_type, True
    if semantic_query_type and semantic_confidence >= 0.45 and "meaningful_query_marked_no_answer" not in quality_flags:
        query_type = semantic_query_type
    else:
        query_type = rule_query_type
    if query_type == "no_answer_candidate" and rule_query_type != "no_answer_candidate":
        query_type = rule_query_type
        rewrite_override_applied = True
    if query_type == "general_search" and rule_query_type != "general_search":
        query_type = rule_query_type
        rewrite_override_applied = True
    return query_type, rewrite_override_applied


def _extract_protected_anchor_terms(original_query: str, query_type: str) -> list[str]:
    if query_type in {"standard_lookup", "lifecycle_lookup", "section_lookup", "scope"}:
        return []
    anchor_text = re.sub(r"(?:GB|GBT|GB/T|ISO|IEC|QC|QC/T)[/—\-\s]*\d+(?:\.\d+)?(?:—\d{4})?\s*中\s*", "", original_query, flags=re.I)
    anchor_text = re.sub(r"\b(?:GB|GBT|GB/T|ISO|IEC|QC|QC/T)\b[/—\-\s]*\d+(?:\.\d+)?(?:—\d{4})?", "", anchor_text, flags=re.I)
    protected: list[str] = []
    patterns = [
        r"([A-Z]{1,5}\d*(?:[A-Z0-9'/-]{0,6})?(?:阻值|电阻|电压|电流|频率|占空比))",
        r"(检测点\s*\d+\s*(?:电压|电流|频率|占空比|阻值))",
        r"([RLCUVI][A-Za-z0-9'/-]{1,8})",
    ]
    if query_type in {"definition", "comparison", "general_search"}:
        patterns.append(r"([A-Z][A-Z0-9/-]{1,10})")
    for pattern in patterns:
        for match in re.finditer(pattern, anchor_text, re.I):
            value = _canonicalize_parameter_anchor(re.sub(r"\s+", "", match.group(1).strip()))
            if value and value not in protected:
                protected.append(value)
    return protected[:8]


def _rebuild_normalized_query(
    *,
    original_query: str,
    query_type: str,
    semantic,
    rule_normalized: str,
    protected_anchor_terms: list[str],
) -> str:
    semantic_normalized = str(getattr(semantic, "normalized_query", "") or "").strip()
    if query_type in {"standard_lookup", "lifecycle_lookup"}:
        return _normalize_standard_code(_extract_standard_code(original_query) or semantic_normalized or rule_normalized or original_query.strip())
    if protected_anchor_terms:
        return protected_anchor_terms[0]
    if query_type == "definition" and rule_normalized and _looks_cleaner_than_semantic(rule_normalized, semantic_normalized):
        return rule_normalized
    if query_type == "definition":
        for term in re.findall(r"[A-Z][A-Z0-9/-]{1,10}", original_query):
            if len(term) <= 16:
                return term
    if semantic_normalized and not _should_ignore_semantic_anchor(semantic):
        return semantic_normalized
    return rule_normalized or original_query.strip()


def _rebuild_target_topic(
    *,
    original_query: str,
    query_type: str,
    semantic,
    normalized_query: str,
    protected_anchor_terms: list[str],
) -> str:
    semantic_target = str(getattr(semantic, "target_topic", "") or "").strip()
    if query_type in {"standard_lookup", "lifecycle_lookup"}:
        return _normalize_standard_code(_extract_standard_code(original_query) or normalized_query or original_query.strip())
    if protected_anchor_terms:
        return protected_anchor_terms[0]
    if semantic_target and semantic_target.lower() not in {"undefined", "unknown", "未知主题", "未知实体"}:
        if query_type == "definition" and re.fullmatch(r"[A-Z][A-Z0-9/-]{1,10}", normalized_query):
            return normalized_query
        return semantic_target
    return normalized_query or original_query.strip()


def _looks_cleaner_than_semantic(rule_normalized: str, semantic_normalized: str) -> bool:
    if not rule_normalized:
        return False
    if not semantic_normalized:
        return True
    semantic_has_shell = bool(re.search(r"(是什么|是什么意思|代表什么意思|表示什么|指什么|含义是什么|如何理解|怎么理解|定义)$", semantic_normalized))
    return semantic_has_shell and len(rule_normalized) <= len(semantic_normalized)


def _normalize_query(query: str) -> str:
    text = query.strip()
    text = re.sub(r"^(?:GB|GBT|GB/T|ISO|IEC|QC|QC/T)[/—\-\s]*\d+(?:\.\d+)?(?:—\d{4})?\s*中\s*", "", text, flags=re.I)
    text = text.rstrip("？?")
    for pattern in (
        r"^\s*(.+?)\s*有哪些活动要做\s*$",
        r"^\s*(.+?)\s*有哪些活动\s*$",
        r"^\s*(.+?)\s*要做哪些活动\s*$",
        r"^\s*(.+?)\s*有哪些任务\s*$",
        r"^\s*(.+?)\s*有哪些步骤\s*$",
        r"^\s*(.+?)\s*怎么测\s*$",
        r"^\s*(.+?)\s*如何测\s*$",
        r"^\s*(.+?)\s*怎么测试\s*$",
        r"^\s*(.+?)\s*如何测试\s*$",
        r"^\s*(.+?)\s*试验方法是什么\s*$",
        r"^\s*(.+?)\s*测试方法是什么\s*$",
        r"^\s*(.+?)\s*检测方法是什么\s*$",
        r"^\s*(.+?过程域)\s*是什么\s*$",
        r"^\s*(.+?过程域)\s*是什么意思\s*$",
        r"^\s*(.+?)\s*是怎么定义的\s*$",
        r"^\s*(.+?)\s*怎么定义\s*$",
        r"^\s*(.+?)\s*如何定义\s*$",
        r"^\s*(.+?)\s*是什么\s*$",
        r"^\s*(.+?)\s*是什么意思\s*$",
        r"^\s*(.+?)\s*代表什么意思\s*$",
        r"^\s*(.+?)\s*表示什么\s*$",
        r"^\s*(.+?)\s*指什么\s*$",
        r"^\s*(.+?)\s*含义是什么\s*$",
        r"^\s*(.+?)\s*有什么要求\s*$",
        r"^\s*(.+?)\s*要求是什么\s*$",
        r"^\s*(.+?)\s*应满足什么\s*$",
        r"^\s*(.+?)\s*应符合什么\s*$",
        r"^\s*什么是\s*(.+?)\s*$",
        r"^\s*(.+?)\s*如何理解\s*$",
        r"^\s*(.+?)\s*怎么理解\s*$",
    ):
        match = re.match(pattern, text)
        if match:
            text = next(group for group in match.groups() if group)
            break
    text = text.replace("？", " ").replace("?", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"的(?:定义|含义|意思)$", "", text).strip()
    text = _canonicalize_parameter_anchor(text)
    return text


def _detect_query_type(original_query: str, normalized_query: str) -> str:
    if not normalized_query:
        return "no_answer_candidate"
    has_standard_ref = bool(re.search(r"\b(?:GB|GBT|GB/T|ISO|IEC|QC|QC/T)\b", original_query, re.I))
    has_definition_intent = bool(re.search(r"(?:的定义是什么|的定义|什么是|是什么|定义是什么|怎么定义|如何定义|含义是什么|是什么意思|代表什么意思|表示什么|指什么)", original_query))
    if has_standard_ref:
        if any(token in original_query for token in ("发布日期", "实施日期", "生效日期", "发布", "实施")):
            return "lifecycle_lookup"
        if has_definition_intent:
            stripped = re.sub(r"\b(?:GB|GBT|GB/T|ISO|IEC|QC|QC/T)[/—\-\s]*\d+(?:\.\d+)?(?:—\d{4})?\b", "", original_query, flags=re.I)
            if re.search(r"(什么是|是什么|定义|怎么定义|如何定义|含义|意思|表示什么|指什么)", stripped):
                return "definition"
        return "standard_lookup"
    if re.search(r"(有哪些类型|包括哪些类型|有哪些种类|包括哪些种类|包含哪些类型|分为哪些类型|类型有哪些|种类有哪些|分类有哪些)", original_query):
        return "comparison"
    if re.search(r"(有哪些活动|要做哪些活动|活动要做|有哪些任务|有哪些步骤|步骤有哪些|任务有哪些)", original_query):
        return "lifecycle_lookup"
    if re.search(r"(怎么测|如何测|怎样测|怎么测试|如何测试|怎样测试|试验方法|测试方法|检测方法|测量方法)", original_query):
        return "test_method_lookup"
    if re.search(r"过程域.*(是什么|是什么意思|定义|含义)|(?:什么是|定义|含义).*过程域", original_query):
        return "lifecycle_lookup"
    if re.search(r"(时序|流程|阶段|启动|结束|停机|握手|预充|能量传输|状态\s*\d|状态迁移)", original_query):
        return "timing_lookup"
    if re.search(r"(有哪些定义|定义有哪些)", original_query) and _has_explicit_parameter_lookup_intent(original_query):
        return "parameter_lookup"
    if _has_explicit_parameter_lookup_intent(original_query):
        return "parameter_lookup"
    if _looks_like_definition_intent(original_query):
        return "definition"
    if re.search(r"(是什么意思|代表什么意思|表示什么|指什么|含义是什么)", original_query):
        return "definition"
    if re.search(r"(有什么要求|要求是什么|应满足什么|应符合什么|不应超过什么|不小于什么)", original_query):
        return "constraint"
    if re.search(r"(什么是|是什么|定义|怎么定义|如何定义|是怎么定义的|如何理解|怎么理解)", original_query):
        return "definition"
    if re.search(r"(表\s*\d+|表\d+|字段|参数|指标|效率|功率因数|允差)", original_query):
        return "section_lookup"
    if any(token in original_query for token in ("范围", "适用于", "适用范围")):
        return "scope"
    if any(token in original_query for token in ("参数", "表格", "表1", "表 1", "表2", "表 2", "输出特性", "功率因数", "效率")):
        return "section_lookup"
    if any(token in original_query for token in ("要求", "限制", "约束", "不得", "不应", "必须")):
        return "constraint"
    if any(token in original_query for token in ("比较", "区别", "差异", "相比")):
        return "comparison"
    if any(token in original_query for token in ("章节", "第几章", "哪一章", "目录")):
        return "section_lookup"
    return "general_search"


def _looks_like_definition_intent(query: str) -> bool:
    return bool(
        re.search(r"(是什么意思|是什么|定义|含义|代表什么|表示什么|指什么|如何理解|怎么理解)", query)
    )


def _has_explicit_parameter_lookup_intent(query: str) -> bool:
    return bool(
        re.search(
            r"(阻值|电阻|参数值|参数有哪些|参数是什么|哪些参数|电压值|电流值|欧姆|Ω|检测点\s*\d|CC1|CC2|占空比|频率|PWM|(?<![A-Za-z0-9])[+-]?\d+(?:\.\d+)?\s*V(?![A-Za-z0-9]))",
            query,
            re.I,
        )
    )


def _must_terms(original_query: str, normalized_query: str, query_type: str) -> list[str]:
    terms: list[str] = []
    standard_code = _extract_standard_code(original_query)
    if standard_code:
        terms.append(_normalize_standard_code(standard_code))
    exact_terms = re.findall(r"[A-Z][A-Z0-9/-]{1,}", original_query)
    for term in exact_terms:
        if term not in terms:
            terms.append(term)
    if query_type == "definition" and normalized_query and normalized_query not in terms:
        terms.append(normalized_query)
    if query_type in {"constraint", "section_lookup", "parameter_lookup", "test_method_lookup"} and normalized_query:
        for token in _extract_domain_terms(original_query):
            if token not in terms:
                terms.append(token)
    for token in _extract_compound_terms(original_query):
        if token not in terms:
            terms.append(token)
    return terms


def _negative_terms(query: str) -> list[str]:
    negatives: list[str] = []
    if any(token in query for token in ("不是", "不包括", "无关", "排除")):
        negatives.extend([token for token in ("不是", "不包括", "无关", "排除") if token in query])
    return negatives


def _aliases(original_query: str, normalized_query: str, must_terms: list[str]) -> list[str]:
    alias_candidates: list[str] = []
    for seed in [original_query, normalized_query, *must_terms]:
        for alias in expand_with_synonyms(seed):
            if alias and alias not in alias_candidates and alias != original_query and alias != normalized_query:
                alias_candidates.append(alias)
    for match in re.finditer(r"(表\s*\d+)", original_query):
        raw = match.group(1)
        compact = re.sub(r"\s+", "", raw)
        spaced = raw[0] + " " + re.sub(r"\D+", "", raw)
        for variant in [compact, spaced]:
            if variant and variant not in alias_candidates:
                alias_candidates.append(variant)
    return alias_candidates[:12]


def _should_terms(
    normalized_query: str,
    aliases: list[str],
    must_terms: list[str],
    negative_terms: list[str],
) -> list[str]:
    terms: list[str] = []
    for item in [normalized_query, *aliases]:
        cleaned = item.strip()
        if (
            cleaned
            and cleaned not in terms
            and cleaned not in must_terms
            and cleaned not in negative_terms
        ):
            terms.append(cleaned)
    return terms[:12]


def _extract_standard_code(query: str) -> str | None:
    match = re.search(r"(?:GB/T|GBT|GB|ISO|IEC|QC/T|QC)\s*[A-Z]?\s*[\d.]+(?:[—-]\d{2,4})?", query, re.I)
    return match.group(0) if match else None


def _normalize_standard_code(value: str) -> str:
    text = value.upper().replace("GBT", "GB/T").replace("GB T", "GB/T").replace("QC T", "QC/T")
    text = text.replace("-", "—")
    text = re.sub(r"\s+", "", text)
    return text


def _extract_domain_terms(query: str) -> list[str]:
    terms: list[str] = []
    query = _canonicalize_parameter_anchor(query)
    for pattern in [
        r"(表\s*[A-Z]\s*[.．]\s*\d+)",
        r"(表\s*\d+)",
        r"(输出特性参数允差)",
        r"(输入过压)",
        r"(输入过、欠压)",
        r"(过压保护)",
        r"(过压保护试验)",
        r"(试验方法)",
        r"(测试方法)",
        r"(检测方法)",
        r"(车载充电机)",
        r"(OBC)",
        r"(CP)",
        r"(额定输出效率)",
        r"(功率因数)",
        r"(材料)",
        r"(尺寸)",
        r"(插销拔出力)",
        r"(温升)",
        r"(绝缘电阻)",
        r"(电阻)",
        r"(阻值)",
        r"(CC1?)",
        r"(CC2)",
        r"(检测点\s*\d)",
        r"(占空比)",
        r"(频率)",
        r"([+-]?\d+(?:\.\d+)?\s*V)",
        r"(保护门)",
    ]:
        for match in re.finditer(pattern, query):
            term = match.group(1).strip()
            if term and term not in terms:
                terms.append(term)
    if "参数" in query:
        for term in _extract_parameter_query_terms(query):
            if term and term not in terms:
                terms.append(term)
    return terms


def _extract_parameter_query_terms(query: str) -> list[str]:
    text = _canonicalize_parameter_anchor(query)
    text = re.sub(r"(?:GB|GBT|GB/T|ISO|IEC|QC|QC/T)[/—\-\s]*\d+(?:\.\d+)?(?:—\d{4})?", " ", text, flags=re.I)
    text = re.sub(r"表\s*[A-Z]\s*[.．]\s*\d+|表\s*\d+", " ", text, flags=re.I)
    text = re.sub(
        r"(有哪些定义|定义有哪些|参数有哪些|参数是什么|哪些参数|参数值|是什么意思|是什么|代表什么|表示什么|指什么|含义|如何理解|怎么理解|[？?])",
        " ",
        text,
    )
    text = text.replace("的参数", " ").replace("参数", " ")
    chunks = [chunk.strip() for chunk in re.split(r"[\s,，;；:：/|]+", text) if chunk.strip()]
    terms: list[str] = []
    for chunk in chunks:
        for part in re.split(r"的|和|与", chunk):
            part = part.strip()
            if not part:
                continue
            _append_parameter_query_term(terms, part)
            if re.search(r"[\u4e00-\u9fff]", part) and len(part) > 2:
                for size in range(2, min(6, len(part)) + 1):
                    _append_parameter_query_term(terms, part[-size:])
    return terms[:12]


def _append_parameter_query_term(terms: list[str], term: str) -> None:
    cleaned = term.strip()
    if not cleaned or cleaned in terms or _is_generic_parameter_query_term(cleaned):
        return
    terms.append(cleaned)


def _is_generic_parameter_query_term(term: str) -> bool:
    normalized = re.sub(r"\s+", "", term.lower())
    return normalized in {
        "参数",
        "定义",
        "是什么",
        "什么意思",
        "控制导引",
        "控制导引电路",
        "电路",
        "表",
        "table",
    }


def _extract_compound_terms(query: str) -> list[str]:
    terms: list[str] = []
    patterns = [
        r"([A-Z]{1,5}\d*(?:[A-Z0-9'/-]{0,6})?(?:阻值|电阻|电压|电流|频率|占空比))",
        r"(检测点\s*\d+\s*(?:电压|电流|频率|占空比|阻值))",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, query, re.I):
            term = _canonicalize_parameter_anchor(re.sub(r"\s+", "", match.group(1).strip()))
            if term and term not in terms:
                terms.append(term)
    return terms


def _canonicalize_parameter_anchor(value: str) -> str:
    text = str(value or "").strip()
    # In this KB, user-facing "CC电阻" refers to the established CC resistance topic.
    # Preserve generic electrical terms such as "绝缘电阻"; only normalize acronym anchors.
    text = re.sub(r"(?<![A-Za-z0-9])((?:CC|CC1|CC2))电阻", r"\1阻值", text, flags=re.I)
    if re.fullmatch(r"[A-Za-z]{2,6}\d*", text):
        return text.upper()
    return text
