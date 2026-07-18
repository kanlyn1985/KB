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
    "procedure": ["fact", "wiki_chunk", "evidence"],
    "evidence_lookup": ["evidence", "source_unit", "document"],
    "general_search": ["keyword", "semantic", "wiki_chunk", "evidence"],
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
        used_llm=False,
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


def _link_target_objects(query: str, domain_pack: DomainPack | None) -> list[TargetObject]:
    if not domain_pack:
        return []
    lowered = query.lower()
    matches: list[TargetObject] = []
    for canonical_id, aliases in domain_pack.terminology.items():
        candidates = [canonical_id, *aliases]
        best_match = ""
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text and text.lower() in lowered:
                if len(text) > len(best_match):
                    best_match = text
        if not best_match:
            continue
        matches.append(
            TargetObject(
                object_id=canonical_id,
                object_type=_infer_object_type(canonical_id, domain_pack),
                canonical_name=_canonical_display_name(canonical_id, aliases),
                matched_text=best_match,
                confidence=_match_confidence(best_match, canonical_id),
            )
        )
    matches.sort(key=lambda item: (item.confidence, len(item.matched_text)), reverse=True)
    return matches[:5]


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
    for target in targets:
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
    terms = [target.object_id for target in targets]
    for anchor in re.findall(r"(?:GB/T|GBT|GB|ISO|IEC|QC/T|QC)\s*[A-Z]?\s*[\d.]+(?:[—-]\d{2,4})?|[A-Z]{2,8}\d*", query, flags=re.I):
        cleaned = re.sub(r"\s+", "", anchor)
        if cleaned and cleaned not in terms:
            terms.append(cleaned)
    return terms[:12]


def _should_terms(query: str, aliases: list[str], targets: list[TargetObject]) -> list[str]:
    terms: list[str] = []
    for value in [query, *aliases, *(target.canonical_name for target in targets)]:
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
