from __future__ import annotations

import re

from dataclasses import dataclass

from agent_kb.context.context_pack import AgentContextPack, AnswerContract, ContextEvidence, ContextFact
from agent_kb.domains.schema import DomainPack
from agent_kb.projection.models import ObjectProjection, ObjectRelation
from agent_kb.query.query_frame import QueryFrame
from agent_kb.context.evidence_judge import required_shape_groups
from agent_kb.retrieval.cards import RetrievalCard


def build_context_pack(
    *,
    query_frame: QueryFrame,
    domain_pack: DomainPack | None = None,
    objects: list[ObjectProjection] | None = None,
    relations: list[ObjectRelation] | None = None,
    retrieval_cards: list[RetrievalCard] | None = None,
    facts: list[ContextFact] | None = None,
    evidence: list[ContextEvidence] | None = None,
) -> AgentContextPack:
    """Assemble the structured context supplied to an agent.

    This is not a final answer generator. It selects relevant objects, cards,
    evidence, hidden context, warnings, and knowledge gaps so a downstream agent
    can answer with domain-aware evidence constraints.
    """

    all_objects = list(objects or [])
    all_relations = list(relations or [])
    all_cards = list(retrieval_cards or [])
    all_facts = list(facts or [])
    all_evidence = list(evidence or [])

    target_object_ids = {target.object_id for target in query_frame.target_objects}
    selected_objects = _select_objects(all_objects, target_object_ids)
    selected_cards = _select_cards(all_cards, target_object_ids, query_frame)
    selected_relations = _select_relations(all_relations, target_object_ids)
    selected_facts = _select_facts(all_facts, target_object_ids, query_frame)
    selected_evidence = _select_evidence(all_evidence, selected_cards, selected_facts)
    hidden_context = _hidden_context(domain_pack, target_object_ids)
    answer_contract = _answer_contract(domain_pack, query_frame.answer_contract)
    warnings = _warnings(query_frame, selected_objects, selected_cards, selected_evidence)
    knowledge_gaps = _knowledge_gaps(query_frame, selected_objects, selected_evidence)

    return AgentContextPack(
        query_frame=query_frame,
        answer_contract=answer_contract,
        target_objects=selected_objects,
        object_relations=selected_relations,
        retrieval_cards=selected_cards,
        facts=selected_facts,
        evidence=selected_evidence,
        hidden_context=hidden_context,
        warnings=warnings,
        knowledge_gaps=knowledge_gaps,
        recommended_answer_strategy=query_frame.answer_strategy,
    )


def _select_objects(objects: list[ObjectProjection], target_object_ids: set[str]) -> list[ObjectProjection]:
    if not target_object_ids:
        return objects[:8]
    return [obj for obj in objects if obj.object_id in target_object_ids][:8]


def _select_cards(cards: list[RetrievalCard], target_object_ids: set[str], frame: QueryFrame) -> list[RetrievalCard]:
    selected: list[RetrievalCard] = []
    for card in cards:
        if target_object_ids and card.object_id in target_object_ids:
            selected.append(card)
            continue
        if frame.intent in card.answer_shapes:
            selected.append(card)
            continue
        if any(term and term in card.search_text for term in frame.must_terms):
            selected.append(card)
    return _dedupe_cards(selected)[:8]


def _select_relations(relations: list[ObjectRelation], target_object_ids: set[str]) -> list[ObjectRelation]:
    if not target_object_ids:
        return relations[:12]
    return [
        relation
        for relation in relations
        if relation.source_object_id in target_object_ids or relation.target_object_id in target_object_ids
    ][:12]


_CJK_STOP_GRAMS = {"怎么说", "么做", "怎么"}


_RELEVANCE_STRONG = 2


def _fact_query_relevance(fact: ContextFact, tokens: set[str], phrases: list[str]) -> int:
    """中文友好的轻量相关性强度：整短语包含记强命中(2)，逐词元计数。

    用于约束"对象兜底/形态补槽"放行的非主体事实——形态偏好只该让相关内容
    受益；要求 >=2 的强度门槛才能进来，防止单个弱词元把不相关邻域节点的
    同名类型影子事实抬进上下文造成假充分判定。
    """
    blob = " ".join([
        str(fact.subject or ""),
        str(fact.object_value or ""),
        *(f"{key} {value}" for key, value in fact.qualifiers.items()),
    ]).lower()
    if any(phrase and phrase in blob for phrase in phrases):
        return _RELEVANCE_STRONG
    return sum(1 for tok in tokens if tok and tok in blob)


def _fact_query_relevant(fact: ContextFact, tokens: set[str], phrases: list[str]) -> bool:
    return _fact_query_relevance(fact, tokens, phrases) >= _RELEVANCE_STRONG


def _select_facts(facts: list[ContextFact], target_object_ids: set[str], frame: QueryFrame) -> list[ContextFact]:
    selected: list[ContextFact] = []
    object_matches: list[ContextFact] = []
    relevant_fallbacks: list[ContextFact] = []
    preferred = set(frame.preferred_fact_types)

    term_values = [
        frame.normalized_query, frame.target_topic,
        *frame.must_terms, *frame.should_terms, *frame.aliases,
        *(t.canonical_name for t in frame.target_objects if t.confidence >= 0.6),
        *(t.matched_text for t in frame.target_objects if t.confidence >= 0.6),
    ]
    lowered = [re.sub(r"\s+", " ", str(v or "")).lower() for v in term_values]
    tokens: set[str] = set()
    for text, low in zip(term_values, lowered):
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9_/-]{1,31}|\d+(?:\.\d+)?(?:mVpp|mV|V|A|W|kW|%|ms|s)?", text):
            if len(tok) >= 2:
                tokens.add(tok.lower())
        cjk = "".join(ch for ch in str(text or "") if "\u4e00" <= ch <= "\u9fff")
        for i in range(len(cjk) - 1):
            gram = cjk[i:i + 2]
            if gram not in _CJK_STOP_GRAMS:
                tokens.add(gram)
    phrases = [v for v in lowered if len(v) >= 4]

    for fact in facts:
        object_match = not target_object_ids or fact.subject in target_object_ids or str(fact.object_value) in target_object_ids
        if object_match:
            object_matches.append(fact)
        type_match = not preferred or fact.fact_type in preferred
        if object_match and type_match:
            selected.append(fact)
        elif type_match and fact.fact_type != "term_definition":
            # 非主体命中的形态类兜底（图邻域等来源）需要最低查询相关性，
            # 防止不相关邻域节点的影子事实借 shape 覆盖造出假充分判定。
            if _fact_query_relevant(fact, tokens, phrases):
                relevant_fallbacks.append(fact)
    if not selected and object_matches:
        # Evidence-shape preferences guide ranking; they must not erase the only
        # evidence linked to the correctly identified object.
        selected = object_matches
    if not selected and preferred:
        # 遗留兜底：preferred 类型全空时按类型捞回。同样要过相关性门槛，
        # 否则被守门拒绝的邻域影子事实会从这里重新混入（假充分泄漏点）。
        selected = [
            fact for fact in facts
            if fact.fact_type in preferred
            and (fact.subject in target_object_ids
                 or _fact_query_relevant(fact, tokens, phrases))
        ]
    out: list[ContextFact] = []
    seen_fact_ids: set[str] = set()
    for fact in [*selected, *relevant_fallbacks]:
        if len(out) >= 16:
            break
        fid = str(fact.fact_id or "")
        if fid in seen_fact_ids:
            continue
        seen_fact_ids.add(fid)
        out.append(fact)
    return out


def _select_evidence(
    evidence: list[ContextEvidence],
    cards: list[RetrievalCard],
    facts: list[ContextFact],
) -> list[ContextEvidence]:
    wanted = set()
    for card in cards:
        wanted.update(card.evidence_ids)
    for fact in facts:
        wanted.update(fact.evidence_ids)
    if not wanted:
        return evidence[:8]
    return [item for item in evidence if item.evidence_id in wanted][:12]


def _hidden_context(domain_pack: DomainPack | None, target_object_ids: set[str]) -> list[str]:
    if not domain_pack:
        return []
    result: list[str] = []
    for rule in domain_pack.hidden_context_rules:
        trigger_object_id = str(rule.trigger.get("object_id") or "")
        if trigger_object_id and trigger_object_id in target_object_ids:
            for line in rule.inject:
                if line not in result:
                    result.append(line)
    return result[:12]


def _answer_contract(domain_pack: DomainPack | None, contract_name: str | None) -> AnswerContract | None:
    if not domain_pack or not contract_name:
        return None
    spec = domain_pack.answer_contracts.get(contract_name)
    if not spec:
        return None
    return AnswerContract(
        contract_id=spec.name,
        intent=spec.intent,
        required_sections=list(spec.required_sections),
        optional_sections=list(spec.optional_sections),
        output_policy="evidence_grounded",
    )


def _warnings(
    frame: QueryFrame,
    objects: list[ObjectProjection],
    cards: list[RetrievalCard],
    evidence: list[ContextEvidence],
) -> list[str]:
    warnings: list[str] = []
    if frame.ambiguity:
        warnings.append("query has domain ambiguity; clarification may be required")
    if frame.missing_slots:
        warnings.append("query is missing slots: " + ", ".join(frame.missing_slots))
    if frame.target_objects and not objects:
        warnings.append("target objects were linked but no object projection was available")
    if frame.target_objects and not cards:
        warnings.append("target objects were linked but no retrieval card was available")
    if frame.intent != "general_search" and not evidence:
        warnings.append("no supporting evidence selected for non-general intent")
    return warnings


def _knowledge_gaps(frame: QueryFrame, objects: list[ObjectProjection], evidence: list[ContextEvidence]) -> list[str]:
    gaps: list[str] = []
    for slot in frame.missing_slots:
        gaps.append(f"missing_slot:{slot}")
    if not frame.target_objects and frame.intent != "general_search":
        gaps.append("target_object_not_identified")
    if frame.target_objects and not objects:
        gaps.append("object_projection_missing")
    if frame.intent != "general_search" and not evidence:
        gaps.append("supporting_evidence_missing")
    return gaps


def _dedupe_cards(cards: list[RetrievalCard]) -> list[RetrievalCard]:
    result: list[RetrievalCard] = []
    seen: set[str] = set()
    for card in cards:
        if card.card_id in seen:
            continue
        seen.add(card.card_id)
        result.append(card)
    return result


def _card_base_id(value: str) -> str:
    """卡片/对象的父对象 ID：去掉分块后缀（X#n -> X）。"""
    return str(value or "").split("#")[0]


def _is_chunk_card(card: "RetrievalCard") -> bool:
    payload = getattr(card, "structured_payload", None) or {}
    return bool(payload.get("chunk_of"))


def _prefers_as_representative(candidate: "RetrievalCard", incumbent: "RetrievalCard") -> bool:
    """父卡（非分块）优先做对象代表卡；其余保持索引稳定序。"""
    return _is_chunk_card(incumbent) and not _is_chunk_card(candidate)


def select_retrieval_cards(
    *,
    selected_card_ids,
    selected_object_ids,
    all_cards,
    max_per_object: int = 2,
):
    """为 ContextPack 挑选检索卡：排名序选取 + 对象兜底 + 每对象封顶。

    - 直接命中：selected_card_ids（来自重排结果，天然按名次排序）；
    - 对象兜底：fact/影子事实命中的节点也带出内容卡（否则 LLM 无内容可答），
      每个节点用聚合父卡优先的代表卡；
    - 封顶：同一父对象（含 #n 分块与持久池候选）最多 max_per_object 张。
      内存 fuse 的多样性封顶只作用于基线候选，持久池合并发生在其后、不受约束，
      因此在选择阶段统一重新执行；截断保住排名高者而非插入序靠前者。
    """
    by_id = {card.card_id: card for card in all_cards}

    representative: dict[str, RetrievalCard] = {}
    for card in all_cards:
        oid = str(card.object_id or "").strip()
        if not oid:
            continue
        current = representative.get(oid)
        if current is None or _prefers_as_representative(card, current):
            representative[oid] = card

    picked = []
    seen: set[str] = set()
    counts: dict[str, int] = {}
    covered_bases: set[str] = set()

    def _take(card):
        if card is None or card.card_id in seen:
            return False
        base = _card_base_id(card.object_id or card.card_id)
        if counts.get(base, 0) >= max_per_object:
            return False
        seen.add(card.card_id)
        counts[base] = counts.get(base, 0) + 1
        covered_bases.add(base)
        picked.append(card)
        return True

    # 1) 重排命中：按名次序取，超额截断
    for cid in selected_card_ids:
        _take(by_id.get(str(cid)))

    # 2) 对象兜底：该对象还完全没有卡入选时，补其代表卡
    for oid in selected_object_ids:
        key = str(oid or "").strip()
        if key and _card_base_id(key) not in covered_bases:
            _take(representative.get(key))

    return picked


_SHAPE_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "parameter_definition": ("definition",),
    "parameter_constraint": ("constraint",),
    "requirement_constraint": ("requirement",),
    "process_step": ("step",),
    "test_method": ("test",),
    "test_condition": ("condition", "test"),
    "relation_evidence": ("relation",),
}


def missing_group_order(groups: list[set[str]]) -> list[str]:
    ordered: list[str] = []
    for group in groups:
        for shape in sorted(group):
            if shape not in ordered:
                ordered.append(shape)
    return ordered


@dataclass(frozen=True)
class ShapeFill:
    """required_evidence_shapes 引导的补槽结果（审计用）。"""

    filled_shapes: tuple[str, ...]
    fact_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def fill_missing_shapes(
    frame: QueryFrame,
    all_facts,
    all_evidence,
    *,
    selected_fact_ids=None,
    selected_evidence_ids=None,
    max_facts: int = 4,
    max_evidence: int = 3,
) -> ShapeFill:
    """意图要求的证据形态缺失时，主动从全量面补捞对应类型的事实/证据。

    背景：required_evidence_shapes 此前只喂给事后充分性判定——召回散文卡时判定打回
    partial，库里明明有对应表格行/流程步骤却没进前 K。此函数把同样的需求前移到选择：
    只对缺失形态操作、绑定证据、不超预算，纯加法不改已有选择。
    """
    have_ids = set(selected_fact_ids) if selected_fact_ids is not None else set()
    eve_ids = set(selected_evidence_ids) if selected_evidence_ids is not None else set()

    # 与充分性判定同源：按意图取形态组，已被现有事实覆盖的组不再补，
    # 其余组的成员类型并集即补捞目标（组内任一满足即视为覆盖该组）。
    have_types = {fact.fact_type for fact in all_facts if fact.fact_id in have_ids}
    missing_groups = [group for group in required_shape_groups(frame.intent)
                      if not (group & have_types)]
    wanted: list[str] = sorted({shape for group in missing_groups for shape in group})
    if not wanted:
        return ShapeFill((), (), ())

    want_set = set(wanted)
    type_rank = {shape: i for i, shape in enumerate(missing_group_order(missing_groups))}

    # 相关性过滤：补槽只捞与查询有关的事实——对象值命中查询词，
    # 或主体就是理解层链接的目标对象；同节点最多 2 条防单节点刷屏。

    def _norm(value: str) -> str:
        return " ".join(str(value or "").replace("\u3000", " ").replace("\xa0", " ").split()).lower()

    term_list = [
        _norm(v) for v in [
            frame.normalized_query, frame.target_topic,
            *frame.must_terms, *frame.should_terms, *frame.aliases,
            *(t.canonical_name for t in frame.target_objects if t.confidence >= 0.6),
            *(t.matched_text for t in frame.target_objects if t.confidence >= 0.6),
        ] if v
    ]
    tokens: set[str] = set()
    for text in term_list:
        lowered = text.lower()
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9_/-]{1,31}|\d+(?:\.\d+)?(?:mVpp|mV|V|A|W|kW|%|ms|s)?", text):
            if len(tok) >= 2:
                tokens.add(tok.lower())
        # 中文按二元/三元切分（无分词器依赖）；单字歧义太大不入词元。
        cjk = "".join(ch for ch in text if "\u4e00" <= ch <= "\u9fff")
        for size in (2, 3):
            for i in range(len(cjk) - size + 1):
                gram = cjk[i:i + size]
                if not gram.isdigit():
                    tokens.add(gram)
    phrases = [t for t in term_list if len(t) >= 4]
    target_subjects = {t.object_id for t in frame.target_objects}

    def _relevance(fact) -> int:
        # 与选择层同口径：短语包含=2；目标对象本身免检；
        # 其余要求 >=_RELEVANCE_STRONG 才有资格补入（见下方阈值检查）。
        blob = _norm(" ".join([str(fact.subject or ""), str(fact.object_value or ""),
                               *(f"{k} {v}" for k, v in fact.qualifiers.items())]))
        hits = _RELEVANCE_STRONG if any(ph and ph in blob for ph in phrases) else 0
        if hits < _RELEVANCE_STRONG:
            hits += sum(1 for tok in tokens if tok in blob)
        return hits

    per_subject: dict[str, int] = {}
    candidates = []
    for fact in all_facts:
        if fact.fact_type not in want_set or fact.fact_id in have_ids:
            continue
        rel = _relevance(fact)
        if rel < _RELEVANCE_STRONG and fact.subject not in target_subjects:
            continue
        if per_subject.get(fact.subject, 0) >= 2:
            continue
        candidates.append((-rel, type_rank[fact.fact_type], fact.subject, fact))
    candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3].fact_id))

    fact_fill = []
    for _, _, subject, fact in candidates:
        if len(fact_fill) >= max(0, max_facts):
            break
        if per_subject.get(subject, 0) >= 2:
            continue
        per_subject[subject] = per_subject.get(subject, 0) + 1
        fact_fill.append(fact)
    new_fact_ids = [f.fact_id for f in fact_fill]

    referenced_by_kept = {
        eid for fact in all_facts if fact.fact_id in have_ids for eid in fact.evidence_ids
    }
    bound_evidence = [
        eid for eid in dict.fromkeys(
            eid for f in fact_fill for eid in f.evidence_ids
        )
        if eid not in eve_ids and eid not in referenced_by_kept
    ][: max(0, max_evidence)]

    filled = list(dict.fromkeys(f.fact_type for f in fact_fill))
    return ShapeFill(tuple(filled), tuple(new_fact_ids), tuple(bound_evidence))
