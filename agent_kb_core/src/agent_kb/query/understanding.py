from __future__ import annotations

import re
from dataclasses import dataclass

from agent_kb.domains.schema import AnswerContractSpec, DomainPack
from agent_kb.query.query_frame import QueryAmbiguity, QueryFrame, TargetObject


@dataclass(frozen=True)
class UnderstandingOptions:
    """Runtime switches for deterministic query understanding.

    MVP-1 deliberately avoids calling an LLM. The output is schema-compatible
    with future LLM-assisted understanding, but the baseline must remain stable
    and testable.
    """

    require_project_for_constraints: bool = True
    require_condition_for_constraints: bool = True
    use_llm: bool = False  # 规则匹配不确定时用 LLM 语义分解（方案 D）


_INTENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("test_method", ("怎么测", "如何测", "怎样测", "怎么测试", "如何测试", "试验方法", "测试方法", "检测方法", "确认", "验证")),
    ("constraint_lookup", ("要求", "限值", "限制", "不大于", "不小于", "最大", "最小", "应满足", "应符合", "limit", "max", "min")),
    ("comparison", ("区别", "差异", "比较", "相比", "不同")),
    ("definition", ("是什么", "什么是", "定义", "含义", "是什么意思", "如何理解", "怎么理解")),
    ("procedure", ("流程", "步骤", "怎么做", "如何做", "过程")),
    ("evidence_lookup", ("依据", "来源", "证据", "哪一页", "哪个文档", "出自")),
)

_INTENT_TO_EVIDENCE_SHAPES: dict[str, list[str]] = {
    "definition": ["term_definition", "parameter_definition", "wiki_chunk"],
    "constraint_lookup": ["parameter_constraint", "requirement_constraint", "table_row"],
    "test_method": ["test_method", "test_condition", "procedure"],
    "comparison": ["comparison", "two_topic_objects", "relation_evidence"],
    "procedure": ["procedure", "process_step"],
    "evidence_lookup": ["evidence", "source_unit", "document"],
    "general_search": ["wiki_chunk", "evidence", "fact"],
}

_INTENT_TO_CHANNELS: dict[str, list[str]] = {
    "definition": ["object_card", "fact", "wiki_chunk", "evidence"],
    "constraint_lookup": ["object_card", "fact", "table", "graph", "evidence"],
    "test_method": ["object_card", "fact", "graph", "wiki_chunk", "evidence"],
    "comparison": ["object_card", "graph", "fact", "wiki_chunk"],
    "procedure": ["object_card", "fact", "wiki_chunk", "evidence"],
    "evidence_lookup": ["object_card", "evidence", "source_unit", "document"],
    "general_search": ["object_card", "keyword", "semantic", "wiki_chunk", "evidence"],
}


def understand_query(
    query: str,
    domain_pack: DomainPack | None = None,
    *,
    options: UnderstandingOptions | None = None,
) -> QueryFrame:
    """Build a deterministic QueryFrame from user query and optional domain pack.

    This is the first concrete bridge from query rewrite to domain-aware query
    understanding. It links aliases to domain objects, selects answer contracts,
    derives retrieval channels, and surfaces missing slots before retrieval.
    """

    opts = options or UnderstandingOptions()
    original = query.strip()
    normalized = _normalize(original)
    intent, intent_confidence = _detect_intent(original)
    target_objects = _link_target_objects(original, domain_pack)
    used_llm = False
    if opts.use_llm and domain_pack is not None:
        from agent_kb.query.llm_understanding import llm_judged_no_target, llm_link_targets, rule_match_is_uncertain
        if rule_match_is_uncertain(original, target_objects):
            llm_targets = llm_link_targets(original, domain_pack)
            if llm_targets:
                # LLM 结果优先（规则结果作为兜底补充）
                target_objects = llm_targets + [
                    t for t in target_objects
                    if t.object_id not in {x.object_id for x in llm_targets}
                ][:3]
                used_llm = True
            elif llm_judged_no_target(original, domain_pack):
                # LLM 明确判定无目标（如"股票投资策略"）→ 清空规则结果，
                # 避免泛词匹配（策略/ISO/CAN）在检索时被误加成
                target_objects = []
                used_llm = True
    target_topic = target_objects[0].canonical_name if target_objects else normalized
    aliases = _aliases_for_targets(target_objects, domain_pack)
    contract = _select_answer_contract(intent, domain_pack, target_objects)
    missing_slots = _missing_slots(intent, original, target_objects, opts)
    ambiguity = _detect_domain_ambiguity(original, target_objects, domain_pack)
    answer_strategy = _answer_strategy(intent, target_objects, missing_slots, ambiguity)
    preferred_fact_types = _preferred_fact_types(intent, contract)

    return QueryFrame(
        original_query=original,
        domain=domain_pack.domain_id if domain_pack else None,
        intent=intent,
        intent_confidence=intent_confidence,
        normalized_query=normalized,
        target_topic=target_topic,
        target_objects=target_objects,
        slots=_extract_slots(original),
        missing_slots=missing_slots,
        aliases=aliases,
        must_terms=_must_terms(original, target_objects),
        should_terms=_should_terms(original, aliases, target_objects),
        negative_terms=[],
        preferred_fact_types=preferred_fact_types,
        required_evidence_shapes=list(_INTENT_TO_EVIDENCE_SHAPES.get(intent, _INTENT_TO_EVIDENCE_SHAPES["general_search"])),
        retrieval_channels=list(_INTENT_TO_CHANNELS.get(intent, _INTENT_TO_CHANNELS["general_search"])),
        ambiguity=ambiguity,
        answer_contract=contract.name if contract else None,
        answer_strategy=answer_strategy,
        used_llm=used_llm,
        quality_flags=_quality_flags(original, target_objects, missing_slots, ambiguity),
    )


def _normalize(query: str) -> str:
    text = query.strip().rstrip("？?")
    text = re.sub(r"\s+", " ", text)
    for pattern in (
        r"^什么是\s*(.+)$",
        r"^(.+?)\s*(是什么|是什么意思|如何理解|怎么理解|定义是什么)$",
        r"^(.+?)\s*(要求是多少|要求是什么|限值是多少|怎么测|如何测|怎么测试|如何测试|怎么确认)$",
    ):
        match = re.match(pattern, text, flags=re.I)
        if match:
            text = match.group(1).strip()
            break
    return text


def _detect_intent(query: str) -> tuple[str, float]:
    lower = query.lower()
    for intent, markers in _INTENT_PATTERNS:
        if any(marker.lower() in lower for marker in markers):
            return intent, 0.82
    return "general_search", 0.45


_SHORT_WORD_DF_CACHE: dict[tuple[str, str], int] = {}


def _short_word_df(word: str, domain_pack) -> int:
    """词在术语表中的文档频率（出现在几个节点）——子串统计：别名拆分词包含该词即计数。

    "控制" 出现在 控制板/功率控制/电路拓扑…控制 等多个节点 → DF≥2 降权；
    "环路" 只出现在 L-PWRCTRL → DF=1 保持高置信。
    """
    cache_key = (word, getattr(domain_pack, "domain_id", ""))
    if cache_key in _SHORT_WORD_DF_CACHE:
        return _SHORT_WORD_DF_CACHE[cache_key]
    df = 0
    for nid, term in domain_pack.terminology.items():
        aliases = term if isinstance(term, list) else term.get("aliases", [])
        hit = False
        for alias in aliases:
            for part in _expand_alias_parts(alias):
                if word.lower() in part.lower():
                    hit = True
                    break
            if hit:
                break
        if hit:
            df += 1
    _SHORT_WORD_DF_CACHE[cache_key] = df
    return df


def _expand_alias_parts(text: str) -> list[str]:
    """把别名拆成候选词：括号内外都按 /、空白 拆分。

    "失效分析（失效/断裂/开裂/破损）" → 失效分析, 失效, 断裂, 开裂, 破损
    """
    out: list[str] = []
    text = str(text or "").strip()
    if not text:
        return out
    inner = re.findall(r"[（(]([^（）()]*)[）)]", text)
    outer = re.sub(r"[（(][^（）()]*[）)]", " ", text)
    # 保留完整短语（去括号、保留空格）：多词别名如 "DCDC 保护功能" 应可整词匹配，
    # 而不是只拆成 "DCDC"/"保护功能" 两个泛词
    full = re.sub(r"[（(][^（）()]*[）)]", "", text).strip()
    if full and full not in out:
        out.append(full)
    for part in [outer, *inner]:
        for seg in re.split(r"[,，/、\s]+", part):
            seg = seg.strip()
            if len(seg) >= 2 and seg not in out:
                out.append(seg)
    return out


def _link_target_objects(query: str, domain_pack: DomainPack | None) -> list[TargetObject]:
    if not domain_pack:
        return []
    lowered = query.lower()
    matches: list[TargetObject] = []
    # 查询中 2~4 字中文子串（滑动窗口，反向匹配用：查询词出现在别名中，
    # 如"环境" in "环境需求"；窗口保证"环境可靠性要求" 也覆盖 "环境"/"可靠性"）
    cjk_run = re.sub(r"[^\u4e00-\u9fff]", "", query)
    query_cjk = sorted(
        {cjk_run[i : i + n] for n in range(2, 5) for i in range(len(cjk_run) - n + 1)},
        key=len,
        reverse=True,
    )
    for canonical_id, aliases in domain_pack.terminology.items():
        expanded: list[str] = []
        for candidate in [canonical_id, *aliases]:
            expanded.extend(_expand_alias_parts(candidate))
        # 正向：别名词出现在查询中（最长优先）
        best_fwd = ""
        for text in expanded:
            if text.lower() in lowered and len(text) > len(best_fwd):
                best_fwd = text
        # 反向：查询子串是别名拆分词的"前缀或全词"（最长优先）。
        # 仅正向未命中时使用；且一律低置信（子串命中可能是泛词，
        # 如"分析" in "公差分析方法"）。前缀约束排除查询尾缀功能词
        # （"要求" in "功能安全要求"、"标准" in "标准条款"）的误匹配。
        best_bwd = ""
        if not best_fwd:
            for sub in query_cjk:
                if any(text.startswith(sub) for text in expanded) and len(sub) > len(best_bwd):
                    best_bwd = sub
        best_match = best_fwd or best_bwd
        if not best_match:
            continue
        is_bwd = bool(best_bwd) and not best_fwd
        # 短英文词（≤3）DF≥2 或 2~4 字中文词 DF≥3（OBC/CAN/控制/逻辑/失效）：
        # 是"提及"词而非"定义"词 → 降权（排在长匹配后），不剔除。
        # 中文阈值高于英文：领域词（效率/灌封胶/环路，DF≤2）应保持高置信
        is_short_en = bool(re.fullmatch(r"[A-Za-z]{1,3}", best_match))
        is_short_cjk = bool(re.fullmatch(r"[\u4e00-\u9fff]{2,4}", best_match))
        conf = _match_confidence(best_match, canonical_id)
        df = _short_word_df(best_match, domain_pack)
        if (is_short_en and df >= 2) or (is_short_cjk and df >= 3):
            conf = 0.5
        elif is_bwd:
            conf = 0.5
        matches.append(
            TargetObject(
                object_id=canonical_id,
                object_type=_infer_object_type(canonical_id, domain_pack),
                canonical_name=_canonical_display_name(canonical_id, aliases),
                matched_text=best_match,
                confidence=conf,
            )
        )
    matches.sort(key=lambda item: (item.confidence, len(item.matched_text)), reverse=True)
    return matches[:8]


def _infer_object_type(canonical_id: str, domain_pack: DomainPack) -> str:
    if "Parameter" in domain_pack.object_types:
        return "Parameter"
    if domain_pack.object_types:
        return next(iter(domain_pack.object_types))
    return "Concept"


def _canonical_display_name(canonical_id: str, aliases: list[str]) -> str:
    for alias in aliases:
        if re.search(r"[\u4e00-\u9fff]", alias):
            return alias
    return aliases[0] if aliases else canonical_id


def _match_confidence(matched_text: str, canonical_id: str) -> float:
    return 0.98 if matched_text == canonical_id else 0.88


def _aliases_for_targets(targets: list[TargetObject], domain_pack: DomainPack | None) -> list[str]:
    if not domain_pack:
        return []
    result: list[str] = []
    # 只取高置信目标的别名：低置信（0.5）是"提及词"命中（如"要求"/"标准"），
    # 展开其别名会把无关词（如 R-FSC 的 ISO 26262/HSR/TSR）塞进检索词造成霸榜
    for target in targets:
        if target.confidence < 0.6:
            continue
        for alias in domain_pack.terminology.get(target.object_id, []):
            if alias not in result:
                result.append(alias)
    return result[:16]


def _select_answer_contract(
    intent: str,
    domain_pack: DomainPack | None,
    targets: list[TargetObject],
) -> AnswerContractSpec | None:
    if not domain_pack:
        return None
    target_types = {target.object_type for target in targets}
    intent_matches = [contract for contract in domain_pack.answer_contracts.values() if contract.intent == intent]
    if not intent_matches:
        return None
    for contract in intent_matches:
        if not contract.preferred_object_types or target_types & set(contract.preferred_object_types):
            return contract
    return intent_matches[0]


def _missing_slots(
    intent: str,
    query: str,
    targets: list[TargetObject],
    options: UnderstandingOptions,
) -> list[str]:
    missing: list[str] = []
    if intent in {"constraint_lookup", "test_method"} and not targets:
        missing.append("target_object")
    if intent == "constraint_lookup":
        if options.require_project_for_constraints and not re.search(r"项目|project|p\d+|客户|customer", query, re.I):
            missing.append("project_or_customer")
        if options.require_condition_for_constraints and not re.search(r"工况|条件|负载|温度|vin|iout|额定", query, re.I):
            missing.append("operating_condition")
    return missing


def _extract_slots(query: str) -> dict[str, object]:
    slots: dict[str, object] = {}
    if re.search(r"额定负载", query):
        slots["load_condition"] = "rated_load"
    voltage = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(V|A|mV|mVpp|%)", query, re.I)
    if voltage:
        slots["numeric_anchor"] = f"{voltage.group(1)}{voltage.group(2)}"
    return slots


def _detect_domain_ambiguity(
    query: str,
    targets: list[TargetObject],
    domain_pack: DomainPack | None,
) -> list[QueryAmbiguity]:
    if not domain_pack:
        return []
    ambiguities: list[QueryAmbiguity] = []
    if "纹波" in query and not any(target.object_id == "DCDC_OUTPUT_RIPPLE" for target in targets):
        ambiguities.append(
            QueryAmbiguity(
                term="纹波",
                possible_objects=["DCDC_OUTPUT_RIPPLE", "INPUT_RIPPLE", "OUTPUT_NOISE"],
                reason="纹波可能指输出纹波、输入纹波或噪声，需要对象归一。",
                clarification="你说的纹波是 DCDC 低压输出纹波、输入纹波，还是输出噪声？",
            )
        )
    return ambiguities


def _answer_strategy(intent: str, targets: list[TargetObject], missing_slots: list[str], ambiguity: list[QueryAmbiguity]) -> str:
    if ambiguity:
        return "ask_clarification_with_candidate_interpretations"
    if missing_slots and intent in {"constraint_lookup", "test_method"}:
        return "provide_general_context_and_ask_clarification"
    if not targets and intent != "general_search":
        return "answer_with_caution_and_request_target_object"
    return "answer_with_evidence"


def _preferred_fact_types(intent: str, contract: AnswerContractSpec | None) -> list[str]:
    if contract and contract.preferred_fact_types:
        return list(contract.preferred_fact_types)
    return list(_INTENT_TO_EVIDENCE_SHAPES.get(intent, []))


def _must_terms(query: str, targets: list[TargetObject]) -> list[str]:
    # 低置信目标（短英文泛词匹配，conf=0.5）不进 must_terms，
    # 避免其 terms 在检索时被强加成（误匹配排前）
    terms = [target.object_id for target in targets if target.confidence >= 0.6]
    # 标准号锚点：必须含数字（GB/T 40432、ISO14229），避免 OBC/EMC/CAN 纯字母词被强加成
    for anchor in re.findall(
        r"(?:GB/T|GBT|GB|ISO|IEC|QC/T|QC)\s*[A-Z]?\s*[\d.]+(?:[—-]\d{2,4})?|[A-Z]{2,8}\d+",
        query,
        flags=re.I,
    ):
        cleaned = re.sub(r"\s+", "", anchor)
        if cleaned and cleaned not in terms:
            terms.append(cleaned)
    return terms[:12]


def _should_terms(query: str, aliases: list[str], targets: list[TargetObject]) -> list[str]:
    terms: list[str] = []
    # 只取高置信目标的名字：低置信目标（0.5 泛词命中）的 canonical_name 往往
    # 是长描述（如 R-FSC "功能安全需求（ISO 26262…HSR/SSR）"），拆词后会
    # 让无关大节点卡（内容含这些词）在检索时霸榜
    high_conf_names = [t.canonical_name for t in targets if t.confidence >= 0.6]
    for value in [query, *aliases, *high_conf_names]:
        text = str(value or "").strip()
        if text and text not in terms:
            terms.append(text)
    return terms[:24]


def _quality_flags(
    query: str,
    targets: list[TargetObject],
    missing_slots: list[str],
    ambiguity: list[QueryAmbiguity],
) -> list[str]:
    flags: list[str] = []
    if query and not targets:
        flags.append("no_domain_object_linked")
    if missing_slots:
        flags.append("missing_slots")
    if ambiguity:
        flags.append("domain_ambiguity")
    return flags
